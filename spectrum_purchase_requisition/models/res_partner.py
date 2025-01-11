from odoo import api, fields, models, modules, _
from odoo.exceptions import UserError

class ResPartnerInherited(models.Model):
    _inherit = "res.partner"

    vendor_account = fields.Char(string="Vendor Account")

