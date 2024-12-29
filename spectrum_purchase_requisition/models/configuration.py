from odoo import api, fields, models, modules, _

class BusinessUnit(models.Model):
    _name = 'business.unit'
    _description = 'Business Unit'

    name = fields.Char(string="Name")


# class PurchaseRequisitionType(models.Model):
#     _name = "purchase.requisition.type"
#     _description = "Purchase Requisition Type"
#
#     name = fields.Char(string="Name")