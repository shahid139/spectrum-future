from email.policy import default

from odoo import api, fields, models, modules, _
from odoo.exceptions import UserError


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

    @api.depends('vat_applicability')
    def _validate_vat_applicability(self):
        total = sum([line.vat_applicability for line in self.order_line])
        self.vat_applicability = total



    @api.onchange('type_of_discount')
    def _validate_type_of_discount(self):
        self.write({'discount_value':False,'discount_lumpsum':False})

    @api.onchange('discount_value','discount_lumpsum')
    def _validate_the_discount(self):
        if self.type_of_discount == 'percentage':
            percentage = self.discount_value
            final_percentage = percentage/len(self.order_line)
            for rec in self.order_line:
                rec.discount = final_percentage
        if self.type_of_discount == 'lumpsum':
            percentage = self.discount_lumpsum
            final_percentage = percentage / len(self.order_line)
            for rec in self.order_line:
                rec.lumps_um = final_percentage
    def first_approval(self):
        self.write({
            'state': 'first_approval'
        })

    def second_approval(self):
        self.write({
            'state': 'second_approval',

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





