from email.policy import default

from odoo import api, fields, models, modules, _
from odoo.exceptions import UserError
from odoo.tools import format_amount, format_date, formatLang, groupby
from odoo.tools.float_utils import float_is_zero
from odoo.tools.float_utils import float_compare, float_round
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, get_lang
from datetime import datetime



class PurchaseOrderInherited(models.Model):
    _inherit = "purchase.order"

    pr_type = fields.Many2one('purchase.requisition.type',string="Select Payment Term",related="requisition_id.type_id",store=True)
    vat_applicability = fields.Float(string='VAT Applicability')
    discount_applicable = fields.Float(string='Enter Discount If Applicable')
    type_of_discount = fields.Selection([('percentage','Percentage'),('lumpsum','Lumps um')],default='percentage')
    discount_value = fields.Float(string='Enter Discount')
    discount_lumpsum = fields.Integer(string="Enter Lumps um")
    vat_applicability = fields.Float(string='VAT Applicability',compute='_validate_vat_applicability')
    state = fields.Selection([
        ('draft', 'RFQ'),
        ('sent', 'RFQ Sent'),
        ('first_approval', 'First Approve'),
        ('second_approval', 'Second Approve'),
        ('to approve', 'To Approve'),
        ('purchase', 'Purchase Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled')
    ], string='Status', readonly=True, index=True, copy=False, default='draft', tracking=True)
    delivery_details = fields.Text(string="Delivery Details")
    remarks = fields.Text(string="Remarks")
    pr_type_text = fields.Text()
    first_approved_by = fields.Many2one('res.users',string="First Approved BY")
    last_approved_by = fields.Many2one('res.users', string="Last Approved By")
    final_approval_date = fields.Datetime(string="Final Approval date")
    first_approval_date = fields.Datetime(string="First Approval date")

    street = fields.Char()
    street2 = fields.Char()
    zip = fields.Char(change_default=True)
    city = fields.Char()
    state_id = fields.Many2one("res.country.state", string='State', ondelete='restrict',
                               domain="[('country_id', '=?', country_id)]")
    country_id = fields.Many2one('res.country', string='Country', ondelete='restrict')
    country_code = fields.Char(related='country_id.code', string="Country Code")
    vat = fields.Char(string='Tax ID', index=True, help="The Tax Identification Number. Values here will be validated based on the country format. You can use '/' to indicate that the partner is not subject to tax.")
    cr_number = fields.Char(string="CR Number")
    customer_currency = fields.Many2one("res.currency", string='Currency', tracking=True)
    customer_tax = fields.Many2one('account.tax',string="Customer Tax")
    sequence = fields.Char(default=lambda self: _('New'))

    @api.model_create_multi
    def create(self, vals_list):
        orders = self.browse()
        partner_vals_list = []
        for vals in vals_list:
            company_id = vals.get('company_id', self.default_get(['company_id'])['company_id'])
            # Ensures default picking type and currency are taken from the right company.
            self_comp = self.with_company(company_id)
            if vals.get('sequence', 'New') == 'New':
                seq_date = None
                if 'date_order' in vals:
                    seq_date = fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(vals['date_order']))
                vals['sequence'] = self_comp.env['ir.sequence'].next_by_code('purchase.order.1',
                                                                         sequence_date=seq_date) or '/'
            vals, partner_vals = self._write_partner_values(vals)
            partner_vals_list.append(partner_vals)
            orders |= super(PurchaseOrderInherited, self_comp).create(vals)
        for order, partner_vals in zip(orders, partner_vals_list):
            if partner_vals:
                order.sudo().write(partner_vals)  # Because the purchase user doesn't have write on `res.partner`
        return orders




    @api.onchange('partner_id')
    def get_vendor_details(self):
        if self.partner_id:
            vals = {
                'street':self.partner_id.street,
                'street2':self.partner_id.street2,
                'zip':self.partner_id.zip,
                'city':self.partner_id.city,
                'state_id':self.partner_id.state_id.id,
                'country_id':self.partner_id.country_id.id,
                'cr_number': self.partner_id.cr_number,
                'customer_currency': self.partner_id.customer_currency.id,
                'customer_tax': self.partner_id.customer_tax.id
                    }
            self.write(vals)

    @api.depends('vat_applicability')
    def _validate_vat_applicability(self):
        total = sum([line.vat_applicability for line in self.order_line])
        self.vat_applicability = total


    def action_create_invoice(self):
        """Create the invoice associated to the PO.
        """
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        # 1) Prepare invoice vals and clean-up the section lines
        invoice_vals_list = []
        sequence = 10
        for order in self:
            if order.pr_type.name != "Service":
                if order.invoice_status != 'to invoice':
                    continue

            order = order.with_company(order.company_id)
            pending_section = None
            # Invoice values.
            invoice_vals = order._prepare_invoice()
            # Invoice line values (keep only necessary sections).
            for line in order.order_line:
                if order.pr_type.name != "Service":
                    if line.display_type == 'line_section':
                        pending_section = line
                        continue
                    if not float_is_zero(line.qty_to_invoice, precision_digits=precision):
                        if pending_section:
                            line_vals = pending_section._prepare_account_move_line()
                            line_vals.update({'sequence': sequence})
                            invoice_vals['invoice_line_ids'].append((0, 0, line_vals))
                            sequence += 1
                            pending_section = None
                        line_vals = line._prepare_account_move_line()
                        line_vals.update({'sequence': sequence})
                        invoice_vals['invoice_line_ids'].append((0, 0, line_vals))
                        sequence += 1
                else:
                    if not float_is_zero(line.product_qty, precision_digits=precision):
                        line_vals = line._prepare_account_move_line_service_po()
                        line_vals.update({'sequence': sequence})
                        invoice_vals['invoice_line_ids'].append((0, 0, line_vals))
                        sequence += 1

            invoice_vals_list.append(invoice_vals)

        if not invoice_vals_list:
            raise UserError(_('There is no invoiceable line. If a product has a control policy based on received quantity, please make sure that a quantity has been received.'))

        # 2) group by (company_id, partner_id, currency_id) for batch creation
        new_invoice_vals_list = []
        for grouping_keys, invoices in groupby(invoice_vals_list, key=lambda x: (x.get('company_id'), x.get('partner_id'), x.get('currency_id'))):
            origins = set()
            payment_refs = set()
            refs = set()
            ref_invoice_vals = None
            for invoice_vals in invoices:
                if not ref_invoice_vals:
                    ref_invoice_vals = invoice_vals
                else:
                    ref_invoice_vals['invoice_line_ids'] += invoice_vals['invoice_line_ids']
                origins.add(invoice_vals['invoice_origin'])
                payment_refs.add(invoice_vals['payment_reference'])
                refs.add(invoice_vals['ref'])
            ref_invoice_vals.update({
                'ref': ', '.join(refs)[:2000],
                'invoice_origin': ', '.join(origins),
                'payment_reference': len(payment_refs) == 1 and payment_refs.pop() or False,
                'project_id':self.requisition_id.project_id.id
            })
            new_invoice_vals_list.append(ref_invoice_vals)
        invoice_vals_list = new_invoice_vals_list

        # 3) Create invoices.
        moves = self.env['account.move']
        AccountMove = self.env['account.move'].with_context(default_move_type='in_invoice')
        for vals in invoice_vals_list:
            moves |= AccountMove.with_company(vals['company_id']).create(vals)

        # 4) Some moves might actually be refunds: convert them if the total amount is negative
        # We do this after the moves have been created since we need taxes, etc. to know if the total
        # is actually negative or not
        moves.filtered(lambda m: m.currency_id.round(m.amount_total) < 0).action_switch_move_type()
        self.partner_id.vendor_account = self.env['ir.sequence'].next_by_code('vendor.sequence')

        return self.action_view_invoice(moves)



    @api.onchange('type_of_discount')
    def _validate_type_of_discount(self):
        self.write({'discount_value':False,'discount_lumpsum':False})

    @api.onchange('discount_value', 'discount_lumpsum')
    def _validate_the_discount(self):
        if not self.order_line:
            return  # Exit early if there are no order lines to avoid division by zero

        if self.type_of_discount == 'percentage':
            percentage = self.discount_value
            final_percentage = percentage / len(self.order_line)
            for rec in self.order_line:
                rec.lumps_um = False
                rec.discount = final_percentage

        if self.type_of_discount == 'lumpsum':
            percentage = self.discount_lumpsum
            final_percentage = percentage / len(self.order_line)
            for rec in self.order_line:
                rec.lumps_um = final_percentage

    def first_approval(self):
        login_user = self.env.user
        approval_config = self.env['approval.configuration'].search(
            [('project_id','in',self.requisition_id.project_id.id),('approval_type', '=', 'po_approval'), ('po_approval_levels', '=', 'level_1'),
             ('approved_user', 'in', login_user.id), ('is_active', '=', True)], limit=1)
        approve_users = [v.name for v in approval_config.approved_user]
        if not approval_config:
            raise UserError(
                f"You do not have permission to approve this Purchase Order at the first approval level.\n"
                f"Authorized users for the first approval: {', '.join(approve_users)}"
            )
        self.write({
            'state': 'first_approval',
            'first_approved_by':self.env.user.id,
            'first_approval_date':datetime.now()
        })

    def second_approval(self):
        login_user = self.env.user
        approval_config = self.env['approval.configuration'].search(
            [('project_id','in',self.requisition_id.project_id.id),('approval_type', '=', 'po_approval'), ('po_approval_levels', '=', 'level_2'),
             ('approved_user', 'in', login_user.id), ('is_active', '=', True)], limit=1)
        approve_users = [v.name for v in approval_config.approved_user]
        if not approval_config:
            raise UserError(
                f"You do not have permission to approve this Purchase Order at the second approval level.\n"
                f"Authorized users for the first approval: {', '.join(approve_users)}"
            )
        self.write({
            'state': 'second_approval',
            'last_approved_by':self.env.user.id,
            'final_approval_date': datetime.now()

        })

    def button_confirm(self):
        for order in self:
            if order.state not in ['draft', 'sent','second_approval']:
                continue
            order.order_line._validate_analytic_distribution()
            order._add_supplier_to_product()
            # Deal with double validation process
            if order._approval_allowed():
                order.button_approve()
            else:
                order.write({'state': 'to approve'})
            if order.partner_id not in order.message_partner_ids:
                order.message_subscribe([order.partner_id.id])
        return True

class PurchaseOrderLinesInherited(models.Model):
    _inherit = 'purchase.order.line'

    tolerance = fields.Float(string='Tolerance',default=0.0)
    vat_applicability = fields.Float(string='VAT Applicability')
    lumps_um = fields.Float('Lumps Um')
    last_buying_price = fields.Float(string='Last Purchase price', compute='_compute_last_price_unit',
                                      store=True)  # Added store=True

    @api.depends('product_id')  # Important: Add dependency on product_id
    def _compute_last_price_unit(self):
        for line in self:
            if line.product_id:
                line.taxes_id = line.order_id.customer_tax.ids
                last_purchase_price = self.env['purchase.order.line'].search([
                    ('product_id', '=', line.product_id.id),
                    ('state', 'in', ['purchase', 'done']),  # Consider only confirmed or done sales
                ], order='id desc', limit=1)

                if last_purchase_price:
                    line.last_buying_price = last_purchase_price.price_unit  # Use price_unit, not unit_price
                else:
                    line.last_buying_price = 0.0  # Default to 0 if no prior sale
            else:
                line.last_buying_price = 0.0  # Default to 0 if no product





    @api.depends('product_qty', 'price_unit', 'taxes_id', 'discount','lumps_um')
    def _compute_amount(self):
        for line in self:
            tax_results = self.env['account.tax']._compute_taxes([line._convert_to_tax_base_line_dict()])
            totals = next(iter(tax_results['totals'].values()))
            amount_untaxed = totals['amount_untaxed']
            amount_tax = totals['amount_tax']
            price_subtotal = amount_untaxed
            price_total = amount_untaxed + amount_tax
            if line.order_id.type_of_discount == 'lumpsum':
                price_subtotal = price_subtotal-line.lumps_um
                price_total = price_total-line.lumps_um
            line.update({
                'price_subtotal': price_subtotal,
                'price_tax': amount_tax,
                'price_total': price_total,
            })

    def _prepare_account_move_line_service_po(self, move=False):
        self.ensure_one()
        aml_currency = move and move.currency_id or self.currency_id
        date = move and move.date or fields.Date.today()
        res = {
            'display_type': self.display_type or 'product',
            'name': '%s: %s' % (self.order_id.name, self.name),
            'product_id': self.product_id.id,
            'product_uom_id': self.product_uom.id,
            'quantity': self.product_qty,
            'discount': self.discount,
            'price_unit': self.currency_id._convert(self.price_unit, aml_currency, self.company_id, date, round=False),
            'tax_ids': [(6, 0, self.taxes_id.ids)],
            'purchase_line_id': self.id,
        }
        if self.analytic_distribution and not self.display_type:
            res['analytic_distribution'] = self.analytic_distribution
        return res







