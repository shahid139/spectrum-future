from odoo import api, fields, models, modules, _

class BusinessUnit(models.Model):
    _name = 'business.unit'
    _description = 'Business Unit'

    name = fields.Char(string="Name")

