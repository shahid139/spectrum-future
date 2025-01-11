from odoo import api, fields, models, modules, _
from odoo.exceptions import UserError


class CompanyInherited(models.Model):
    _inherit = 'res.company'

    vat_number = fields.Char(string="VAT No.")
    cr_number = fields.Char(string="CR No.")