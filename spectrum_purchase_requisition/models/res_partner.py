from email.policy import default

from odoo import api, fields, models, modules, _
from odoo.exceptions import UserError

class ResPartnerInherited(models.Model):
    _inherit = "res.partner"

    vendor_account = fields.Char(string="Vendor Account")
    cr_number  = fields.Char(string="CR Number")
    customer_currency = fields.Many2one("res.currency", string='Currency', tracking=True)
    customer_tax = fields.Float(string="Customer Tax")
    customer_status = fields.Selection([('block','Blocked'),('unblock','Un Blocked')],default="unblock")
    credit_limit = fields.Float(
        string='Credit Limit', help='Credit limit specific to this partner.',
        company_dependent=True, copy=False, readonly=False)


    def block_customer(self):
        self.customer_status = 'block'
    def unblock_block_customer(self):
        self.customer_status = 'unblock'




