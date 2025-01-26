from odoo import api, fields, models, modules, _
from odoo.exceptions import UserError
from deep_translator import GoogleTranslator

class AccountInherited(models.Model):
    _inherit = 'account.move'

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('first_approval','First Approval'),
            ('second_approval','Second Approval'),
            ('third_approval','Third Approval'),
            ('posted', 'Posted'),
            ('cancel', 'Cancelled'),
        ],
        string='Status',
        required=True,
        readonly=True,
        copy=False,
        tracking=True,
        default='draft',
    )

    @api.depends('date', 'auto_post')
    def _compute_hide_post_button(self):
        for record in self:
            record.hide_post_button = record.state != 'third_approval' \
                                      and record.auto_post != 'no' and record.date > fields.Date.context_today(record)

    def validate_first_approval(self):
        if not self.invoice_date:
            raise UserError('The Bill/Refund date is required to validate this document.')
        self.write({'state':'first_approval'})
    def validate_second_approval(self):
        self.write({'state':'second_approval'})
    def validate_third_approval(self):
        self.write({'state':'third_approval'})

    def translate_to_arabic(self, text):
        translated_text = GoogleTranslator(source='en', target='ar').translate(text)
        return translated_text

    def get_delivery_number(self,po_number):
        if po_number:
            stock_picking_id = self.env['stock.picking'].search([('origin','=',po_number)],limit=1)
            return stock_picking_id.name
    def get_purchase_order_date(self,po_number):
        if po_number:
            purchase_order = self.env['purchase.order'].search([('name','=',po_number)],limit=1)
            return purchase_order.create_date

