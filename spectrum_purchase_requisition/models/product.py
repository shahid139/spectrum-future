from odoo import models, fields

class ProductProduct(models.Model):
    _inherit = 'product.template'

    part_number = fields.Char(string="Part Number")
