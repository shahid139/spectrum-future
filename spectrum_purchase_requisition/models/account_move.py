from odoo import api, fields, models, modules, _
from odoo.exceptions import UserError
from deep_translator import GoogleTranslator
import qrcode
import base64
from io import BytesIO

def generate_qr_code(value):
    qr = qrcode.QRCode(
             version=1,
             error_correction=qrcode.constants.ERROR_CORRECT_L,
             box_size=20,
             border=4)
    qr.add_data(value)
    qr.make(fit=True)
    img = qr.make_image()
    stream = BytesIO()
    img.save(stream, format="PNG")
    qr_img = base64.b64encode(stream.getvalue())
    return qr_img

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
    project_id = fields.Many2one('project.project', string="Project")
    qr_image = fields.Binary("QR Code", compute='_generate_qr_code')
    qr_in_report = fields.Boolean('Display QRCode in Report?')

    def _generate_qr_code(self, silent_errors=False):
        self.qr_image = None
        for order in self:
            supplier_name = self.partner_id.name
            vat = str(self.company_id.vat)
            vat_total = str(self.amount_tax)
            date = str(self.invoice_date)

            total = ''.join([self.currency_id.name, str(self.amount_total)])
            lf = '\t'
            invoice = lf.join(
                ['Customer:', supplier_name,  'Date:', date, 'Total with VAT:',
                 total, 'VAT total:', vat_total])
            qr_img = generate_qr_code(invoice)
            order.write({
                'qr_image': qr_img
            })

    def action_post(self):
        for invoice in self:
            if invoice.project_id:
                invoice.project_id._compute_spent_amount()
                invoice.project_id._compute_available_budget()
        return super(AccountInherited, self).action_post()

    @api.depends('date', 'auto_post')
    def _compute_hide_post_button(self):
        for record in self:
            record.hide_post_button = record.state != 'third_approval' \
                                      and record.auto_post != 'no' and record.date > fields.Date.context_today(record)

    def validate_first_approval(self):
        if not self.invoice_date:
            raise UserError('The Bill/Refund date is required to validate this document.')
        login_user = self.env.user

        domain = [('approval_type', '=', 'invoice'), ('invoice_approval_levels', '=', 'level_1'),
             ('approved_user', 'in', login_user.id), ('is_active', '=', True)]
        if self.project_id:
            domain.append(('project_id', 'in', self.project_id.id))
        approval_config = self.env['approval.configuration'].search(domain, limit=1)
        approve_users = [v.name for v in approval_config.approved_user]
        if not approval_config:
            raise UserError(
                f"You do not have permission to approve this Invoice at the first approval level.\n"
                f"Authorized users for the first approval: {', '.join(approve_users)}"
            )

        self.write({'state':'first_approval'})
    def validate_second_approval(self):
        login_user = self.env.user
        domain = [('approval_type', '=', 'invoice'), ('invoice_approval_levels', '=', 'level_2'),
                  ('approved_user', 'in', login_user.id), ('is_active', '=', True)]
        if self.project_id:
            domain.append(('project_id', 'in', self.project_id.id))
        approval_config = self.env['approval.configuration'].search(domain, limit=1)
        approve_users = [v.name for v in approval_config.approved_user]
        if not approval_config:
            raise UserError(
                f"You do not have permission to approve this Invoice at the first approval level.\n"
                f"Authorized users for the first approval: {', '.join(approve_users)}"
            )
        self.write({'state':'second_approval'})
    def validate_third_approval(self):
        login_user = self.env.user
        domain = [('approval_type', '=', 'invoice'), ('invoice_approval_levels', '=', 'level_2'),
                  ('approved_user', 'in', login_user.id), ('is_active', '=', True)]
        if self.project_id:
            domain.append(('project_id', 'in', self.project_id.id))
        approval_config = self.env['approval.configuration'].search(domain, limit=1)
        approve_users = [v.name for v in approval_config.approved_user]
        if not approval_config:
            raise UserError(
                f"You do not have permission to approve this Invoice at the first approval level.\n"
                f"Authorized users for the first approval: {', '.join(approve_users)}"
            )
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

