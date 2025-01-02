from email.policy import default

from odoo import api, fields, models, modules, _
from odoo.exceptions import UserError


class PurchaseOrderInherited(models.Model):
    _inherit = "purchase.order"

    pr_type = fields.Many2one('purchase.requisition.type',string="Select Payment Term",related="requisition_id.type_id",store=True)
    vat_applicability = fields.Float(string='VAT Applicability')
    discount_applicable = fields.Float(string='Enter Discount If Applicable')

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
    discount_applicable = fields.Float(string='Enter Discount If Applicable')


