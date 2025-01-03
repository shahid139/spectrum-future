from odoo import api, fields, models, modules, _
from odoo.exceptions import UserError
from odoo.tools import format_amount, format_date, formatLang, groupby
from odoo.tools.float_utils import float_is_zero
from odoo.exceptions import UserError, ValidationError

PURCHASE_REQUISITION_STATES = [
    ('draft', 'Draft'),
    ('ongoing', 'Ongoing'),
    ('first_approval','First Approve'),
    ('second_approval','Second Approve'),
    ('in_progress', 'Confirmed'),
    ('open', 'Bid Selection'),
    ('done', 'Closed'),
    ('cancel', 'Cancelled')
]


class PurchaseRequisitionCreation(models.Model):
    _inherit = "purchase.requisition"

    business_unit = fields.Many2one('business.unit', string='Select BU',required=True)
    project_id = fields.Many2one('project.project',string="Select Project")
    account_id = fields.Many2one('account.analytic.account',string="Select Natural Account",required=True)
    budget_task = fields.Many2one('crossovered.budget',string="Select Budget Task",required=True)
    state = fields.Selection(PURCHASE_REQUISITION_STATES,
                             'Status', tracking=True, required=True,
                             copy=False, default='draft')
    state_blanket_order = fields.Selection(PURCHASE_REQUISITION_STATES, compute='_set_state')
    pr_type_check = fields.Boolean()
    is_po_need = fields.Boolean()


    def _prepare_invoice(self):
        """Prepare the dict of values to create the new invoice for a purchase order.
        """
        self.ensure_one()
        move_type = self._context.get('default_move_type', 'in_invoice')

        partner_invoice = self.env['res.partner'].browse(self.vendor_id.address_get(['invoice'])['invoice'])
        partner_bank_id = self.vendor_id.commercial_partner_id.bank_ids.filtered_domain(['|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)])[:1]

        invoice_vals = {
            'ref': '', # self.partner_ref or ''
            'move_type': move_type,
            'narration': '', #self.notes,
            'currency_id': self.currency_id.id,
            'partner_id': partner_invoice.id,
            'fiscal_position_id': '',#(self.fiscal_position_id or self.fiscal_position_id._get_fiscal_position(partner_invoice)).id,
            'payment_reference': '', # self.partner_ref or ''
            'partner_bank_id': partner_bank_id.id,
            'invoice_origin': self.name,
            # 'invoice_payment_term_id': self.type_id, #self.payment_term_id.id,
            'invoice_line_ids': [],
            'company_id': self.company_id.id,
        }
        return invoice_vals

    def _prepare_account_move_line(self, move=False):
        self.ensure_one()
        aml_currency = self.currency_id
        date = move and move.date or fields.Date.today()
        res = {
            'display_type': self.display_type or 'product',
            'name': '%s: %s' % (self.order_id.name, self.name),
            'product_id': self.product_id.id,
            'product_uom_id': self.product_uom.id,
            'quantity': self.qty_to_invoice,
            'discount': self.discount,
            'price_unit': self.currency_id._convert(self.price_unit, aml_currency, self.company_id, date, round=False),
            'tax_ids': [(6, 0, self.taxes_id.ids)],
            'purchase_line_id': self.id,
        }
        if self.analytic_distribution and not self.display_type:
            res['analytic_distribution'] = self.analytic_distribution
        return res

    def action_view_invoice(self, invoices=False):
        """This function returns an action that display existing vendor bills of
        given purchase order ids. When only one found, show the vendor bill
        immediately.
        """
        if not invoices:
            self.invalidate_model(['invoice_ids'])
            invoices = self.invoice_ids

        result = self.env['ir.actions.act_window']._for_xml_id('account.action_move_in_invoice_type')
        # choose the view_mode accordingly
        if len(invoices) > 1:
            result['domain'] = [('id', 'in', invoices.ids)]
        elif len(invoices) == 1:
            res = self.env.ref('account.view_move_form', False)
            form_view = [(res and res.id or False, 'form')]
            if 'views' in result:
                result['views'] = form_view + [(state, view) for state, view in result['views'] if view != 'form']
            else:
                result['views'] = form_view
            result['res_id'] = invoices.id
        else:
            result = {'type': 'ir.actions.act_window_close'}

        return result

    def action_create_invoice(self):

        """Create the invoice associated to the PO.
        """
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        # 1) Prepare invoice vals and clean-up the section lines
        invoice_vals_list = []
        sequence = 10
        for order in self:
            if order.state == 'open' and order.is_po_need:
                continue

            order = order.with_company(order.company_id)
            pending_section = None
            # Invoice values.
            invoice_vals = order._prepare_invoice()
            # Invoice line values (keep only necessary sections).
            for line in order.line_ids:
                pending_section = False
                # if line.display_type == 'line_section':
                #     pending_section = line
                #     continue
                if not float_is_zero(line.product_qty, precision_digits=precision):
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

        return self.action_view_invoice(moves)

    def check_budget(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("You cannot confirm agreement '%s' because there is no product line.", self.name))
        if self.budget_task:
            planned_amount = sum([v.planned_amount for v in self.budget_task.crossovered_budget_line])
            practical_amount = sum([v.practical_amount for v in self.budget_task.crossovered_budget_line])
            requisition_amount = sum([v.total for v in self.line_ids])
            available_amount = planned_amount - practical_amount
            if requisition_amount > available_amount:
                self.state = 'cancel'
                sticky_notify = {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Validation'),
                        'message': 'No Funds Available for PR creation.',
                        'sticky': False,
                        'next': {
                            'type': 'ir.actions.act_window_close'
                        },
                    }
                }
            else:
                sticky_notify = {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Validation'),
                        'message': 'Funds Available for PR creation.',
                        'sticky': False,
                        'next': {
                            'type': 'ir.actions.act_window_close'
                        },
                    }
                }

            return sticky_notify
    @api.model_create_multi
    def create(self, vals_list):
        # Ensure `company_id` is available in the input values
        for vals in vals_list:
            # Retrieve the company_id from the vals or set a default
            company_id = vals.get('company_id', self.env.company.id)
            # Get the sequence value
            vals['name'] = self.env['ir.sequence'].with_company(company_id).next_by_code('purchase.requisition.code')
        # Call the super method with updated vals_list
        return super(PurchaseRequisitionCreation, self).create(vals_list)

    @api.onchange('currency_id')
    def validate_currency(self):
        if self.currency_id:
            for rec in self.line_ids:
                rec.currency_id = self.currency_id.id


    @api.onchange('type_id')
    def validate_pr_type(self):
        if self.type_id:
            inventory_xml_id = self.env.ref("spectrum_purchase_requisition.pr_type_1")
            expense_xml_id = self.env.ref("spectrum_purchase_requisition.pr_type_2")
            asset_xml_id = self.env.ref("spectrum_purchase_requisition.pr_type_3")
            petty_cash_xml_id = self.env.ref("spectrum_purchase_requisition.pr_type_4")
            service_xml_id = self.env.ref("spectrum_purchase_requisition.pr_type_5")
            if self.type_id == petty_cash_xml_id:
                self.is_po_need = True
            else:
                self.is_po_need = False


    @api.depends('state')
    def _set_state(self):
        for requisition in self:
            requisition.state_blanket_order = requisition.state

    def first_approval(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("You cannot confirm agreement '%s' because there is no product line.", self.name))
        if self.budget_task:
            planned_amount = sum([v.planned_amount for v in self.budget_task.crossovered_budget_line])
            practical_amount = sum([v.practical_amount for v in self.budget_task.crossovered_budget_line])
            requisition_amount = sum([v.total for v in self.line_ids])
            available_amount = planned_amount - practical_amount
            if requisition_amount > available_amount:
                self.state = 'cancel'
                sticky_notify = {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Validation'),
                        'message': 'No Fund Available for PR creation.',
                        'sticky': False,
                        'next': {
                            'type': 'ir.actions.act_window_close'
                        },
                    }
                }

                return sticky_notify
        self.write({
            'state_blanket_order': 'first_approval',
            'state':'first_approval'
        })

    def second_approval(self):
        self.write({
            'state':'second_approval',
            'state_blanket_order':'second_approval'
        })


    def action_in_progress(self):
        if self.type_id.quantity_copy == 'none' and self.vendor_id:
            for requisition_line in self.line_ids:
                if requisition_line.price_unit <= 0.0:
                    raise UserError(_('You cannot confirm the blanket order without price.'))
                if requisition_line.product_qty <= 0.0:
                    raise UserError(_('You cannot confirm the blanket order without quantity.'))
                requisition_line.create_supplier_info()
            self.write({'state': 'ongoing'})
        else:
            self.write({'state': 'in_progress'})


class PurchaseRequisitionLineInherited(models.Model):
    _inherit = "purchase.requisition.line"

    total = fields.Monetary(string="Total",store=True)
    currency_id = fields.Many2one('res.currency', 'Currency', required=True, related='company_id.currency_id')

    @api.onchange('price_unit','product_qty')
    def validate_total(self):
        if self.price_unit:
            self.total= self.product_qty * self.price_unit


    def _prepare_account_move_line(self, move=False):
        self.ensure_one()
        aml_currency = move and move.currency_id or self.currency_id
        date = move and move.date or fields.Date.today()
        res = {
            'display_type': 'product',
            'name': '%s: %s' % (self.requisition_id.name, self.product_description_variants),
            'product_id': self.product_id.id,
            'product_uom_id': self.product_uom_category_id.id,
            'quantity': self.product_qty,
            # 'discount': self.discount,
            'price_unit': self.currency_id._convert(self.price_unit, aml_currency, self.company_id, date, round=False),
            # 'tax_ids': [(6, 0, self.taxes_id.ids)],
            'purchase_line_id': self.id,
        }
        if self.analytic_distribution:
            res['analytic_distribution'] = self.analytic_distribution
        return res

    # @api.depends('product_qty', 'price_unit')
    # def _compute_amount(self):
    #     for line in self:
    #         tax_results = self.env['account.tax']._compute_taxes([line._convert_to_tax_base_line_dict()])
    #         # totals = next(iter(tax_results['totals'].values()))
    #         # amount_untaxed = totals['amount_untaxed']
    #         # amount_tax = totals['amount_tax']
    #         #
    #         # line.update({
    #         #     'total': amount_untaxed,
    #         #     'price_tax': amount_tax,
    #         #     'price_total': amount_untaxed + amount_tax,
    #         # })
    #
    #
    #
    # def _convert_to_tax_base_line_dict(self):
    #     """ Convert the current record to a dictionary in order to use the generic taxes computation method
    #     defined on account.tax.
    #
    #     :return: A python dictionary.
    #     """
    #     self.ensure_one()
    #     return self.env['account.tax']._convert_to_tax_base_line_dict(
    #         self,
    #         currency=self.requisition_id.currency_id,
    #         product=self.product_id,
    #         price_unit=self.price_unit,
    #         quantity=self.product_qty,
    #         total=self.total,
    #     )