from email.policy import default

from odoo import api, fields, models, modules, _
from odoo.exceptions import UserError


class PurchaseOrderInherited(models.Model):
    _inherit = "purchase.order"

    pr_type = fields.Many2one('purchase.requisition.type',string="Select PR Type",related="requisition_id.pr_type",store=True)
    vat_applicability = fields.Float(string='VAT Applicability')

class PurchaseOrderLinesInherited(models.Model):
    _inherit = 'purchase.order.line'

    tolerance = fields.Float(string='Tolerance',default=0.0)
    vat_applicability = fields.Float(string='VAT Applicability')


