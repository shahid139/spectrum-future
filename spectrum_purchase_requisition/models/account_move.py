from odoo import api, fields, models, modules, _
from odoo.exceptions import UserError
from deep_translator import GoogleTranslator
import qrcode
import base64
from io import BytesIO
from datetime import datetime, timedelta

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
    first_approved_users = fields.Many2many('res.users', 'first_inv_approval_rel', string="First Approved BY")
    second_approved_users = fields.Many2many('res.users', 'second_inv_approval_rel', string="Second Approved BY")
    third_approved_users = fields.Many2many('res.users', 'third_inv_approval_rel', string="Third Approved BY")

    first_approved_by = fields.Many2one('res.users', string="First Approved BY")
    second_approved_by = fields.Many2one('res.users', string="Second Approved BY")
    third_approved_by = fields.Many2one('res.users', string="Third Approved BY")
    first_approval_date = fields.Datetime(string="First Approval date")
    second_approval_date = fields.Datetime(string="Second Approval date")
    third_approval_date = fields.Datetime(string="Third Approval date")

    @api.model_create_multi
    def create(self, vals_list):
        approval_config = self.env['approval.configuration'].search([
            ('approval_type', '=', 'invoice'),
            ('invoice_approval_levels', '=', 'level_1'),
            ('is_active', '=', True)
        ], limit=1)

        for vals in vals_list:
            if approval_config:
                vals['first_approved_users'] = [(6, 0, approval_config.approved_user.ids)]

        # Create actual records
        invoices = super(AccountInherited, self).create(vals_list)

        # Now schedule activities on created invoices
        if approval_config:
            for invoice in invoices:
                for user in approval_config.approved_user:
                    invoice.with_context(mail_activity_quick_update=True).sudo().activity_schedule(
                        'spectrum_purchase_requisition.account_invoice',
                        user_id=user.id,
                        note='Invoice approval required'
                    )

        return invoices

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
            if record.move_type == 'in_invoice':
                record.hide_post_button = record.state != 'third_approval' \
                                          and record.auto_post != 'no' and record.date > fields.Date.context_today(record)
            else:
                record.hide_post_button = record.state != 'draft' \
                                          or record.auto_post != 'no' and record.date > fields.Date.context_today(
                    record)

    def validate_first_approval(self):
        self.ensure_one()
        admin_access = self.env.user.has_group("base.group_system")
        if not self.invoice_date:
            raise UserError('The Bill/Refund date is required to validate this document.')

        login_user = self.env.user
        domain = [
            ('approval_type', '=', 'invoice'),
            ('invoice_approval_levels', '=', 'level_1'),
            ('approved_user', 'in', login_user.id),
            ('is_active', '=', True)
        ]
        if self.project_id:
            domain.append(('project_id', '=', self.project_id.id))

        approval_config = self.env['approval.configuration'].search(domain, limit=1)
        approve_users = [v.name for v in approval_config.approved_user] if approval_config else []

        if not approval_config and not admin_access:
            raise UserError(
                f"You do not have permission to approve this Invoice at the first approval level.\n"
                f"Authorized users: {', '.join(approve_users)}"
            )

        for user in self.second_approved_users:
            self.with_context(mail_activity_quick_update=True).sudo().activity_schedule(
                'spectrum_purchase_requisition.account_invoice',
                user_id=user.id
            )

        second_approval_config = self.env['approval.configuration'].search([
            ('approval_type', '=', 'invoice'),
            ('invoice_approval_levels', '=', 'level_2'),
            ('is_active', '=', True)
        ], limit=1)

        if not second_approval_config:
            raise UserError(
                "Second-level approval configuration is missing. Please configure the appropriate users for Level 2 Invoice approval."
            )

        self.write({
            'state': 'first_approval',
            'first_approved_by': login_user.id,
            'second_approved_users': [(6, 0, second_approval_config.approved_user.ids)],
            'first_approval_date': fields.Datetime.now()
        })

    def validate_second_approval(self):
        self.ensure_one()
        admin_access = self.env.user.has_group("base.group_system")
        login_user = self.env.user

        domain = [
            ('approval_type', '=', 'invoice'),
            ('invoice_approval_levels', '=', 'level_2'),
            ('approved_user', 'in', login_user.id),
            ('is_active', '=', True)
        ]
        if self.project_id:
            domain.append(('project_id', '=', self.project_id.id))

        approval_config = self.env['approval.configuration'].search(domain, limit=1)
        approve_users = [v.name for v in approval_config.approved_user] if approval_config else []

        if not approval_config and not admin_access:
            raise UserError(
                f"You do not have permission to approve this Invoice at the second approval level.\n"
                f"Authorized users: {', '.join(approve_users)}"
            )

        for user in self.third_approved_users:
            self.with_context(mail_activity_quick_update=True).sudo().activity_schedule(
                'spectrum_purchase_requisition.account_invoice',
                user_id=user.id
            )

        third_approval_config = self.env['approval.configuration'].search([
            ('approval_type', '=', 'invoice'),
            ('invoice_approval_levels', '=', 'level_3'),
            ('is_active', '=', True)
        ], limit=1)

        if not third_approval_config:
            raise UserError(
                "Third-level approval configuration is missing. Please configure Level 3 Invoice approvers.")

        self.write({
            'state': 'second_approval',
            'second_approved_by': login_user.id,
            'third_approved_users': [(6, 0, third_approval_config.approved_user.ids)],
            'second_approval_date': fields.Datetime.now()
        })

    def validate_third_approval(self):
        self.ensure_one()
        admin_access = self.env.user.has_group("base.group_system")
        login_user = self.env.user

        domain = [
            ('approval_type', '=', 'invoice'),
            ('invoice_approval_levels', '=', 'level_3'),
            ('approved_user', 'in', login_user.id),
            ('is_active', '=', True)
        ]
        if self.project_id:
            domain.append(('project_id', '=', self.project_id.id))

        approval_config = self.env['approval.configuration'].search(domain, limit=1)
        approve_users = [v.name for v in approval_config.approved_user] if approval_config else []

        if not approval_config and not admin_access:
            raise UserError(
                f"You do not have permission to approve this Invoice at the third approval level.\n"
                f"Authorized users: {', '.join(approve_users)}"
            )

        self.write({
            'state': 'third_approval',
            'third_approved_by': login_user.id,
            'third_approval_date': fields.Datetime.now()
        })

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

