from odoo import api, fields, models, modules, _
from odoo.exceptions import UserError
from odoo.tools import format_amount, format_date, formatLang, groupby
from odoo.tools.float_utils import float_is_zero
from odoo.exceptions import UserError, ValidationError

PURCHASE_REQUISITION_STATES = [
    ('draft', 'Draft'),
    ('ongoing', 'Ongoing'),
    ('first_approval','First Approve'),
    ('second_approval','Second Approve'),
    ('in_progress', 'Confirmed'),
    ('open', 'Bid Selection'),
    ('done', 'Closed'),
    ('cancel', 'Cancelled')
]


class PurchaseRequisitionCreation(models.Model):
    _inherit = "purchase.requisition"

    business_unit = fields.Many2one('business.unit', string='Select BU',required=True)
    project_id = fields.Many2one('project.project',string="Select Project")
    account_id = fields.Many2one('account.analytic.account',string="Select Natural Account",required=True)
    budget_task = fields.Many2one('crossovered.budget',string="Select Budget Task",required=True)
    state = fields.Selection(PURCHASE_REQUISITION_STATES,
                             'Status', tracking=True, required=True,
                             copy=False, default='draft')
    state_blanket_order = fields.Selection(PURCHASE_REQUISITION_STATES, compute='_set_state')
    pr_type_check = fields.Boolean()
    is_po_need = fields.Boolean()

    @api.onchange('currency_id')
    def validate_currency(self):
        if self.currency_id:
            for rec in self.line_ids:
                rec.currency_id = self.currency_id.id


    @api.onchange('type_id')
    def validate_pr_type(self):
        if self.type_id:
            inventory_xml_id = self.env.ref("spectrum_purchase_requisition.pr_type_1")
            expense_xml_id = self.env.ref("spectrum_purchase_requisition.pr_type_2")
            asset_xml_id = self.env.ref("spectrum_purchase_requisition.pr_type_3")
            petty_cash_xml_id = self.env.ref("spectrum_purchase_requisition.pr_type_4")
            service_xml_id = self.env.ref("spectrum_purchase_requisition.pr_type_5")
            if self.type_id == petty_cash_xml_id:
                self.is_po_need = True
            else:
                self.is_po_need = False


    @api.depends('state')
    def _set_state(self):
        for requisition in self:
            requisition.state_blanket_order = requisition.state

    def first_approval(self):
        if self.budget_task:
            planned_amount = sum([v.planned_amount for v in self.budget_task.crossovered_budget_line])
            practical_amount = sum([v.practical_amount for v in self.budget_task.crossovered_budget_line])
            requisition_amount = sum([v.total for v in self.line_ids])
            available_amount = planned_amount - practical_amount
            if requisition_amount > available_amount:
                self.state = 'cancel'
                sticky_notify = {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Validation'),
                        'message': 'No Fund Available for PR creation.',
                        'sticky': False,
                        'next': {
                            'type': 'ir.actions.act_window_close'
                        },
                    }
                }
                return sticky_notify
        self.write({
            'state_blanket_order': 'first_approval',
            'state':'first_approval'
        })

    def second_approval(self):
        self.write({
            'state':'second_approval',
            'state_blanket_order':'second_approval'
        })


    def action_in_progress(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("You cannot confirm agreement '%s' because there is no product line.", self.name))

        if self.type_id.quantity_copy == 'none' and self.vendor_id:
            for requisition_line in self.line_ids:
                if requisition_line.price_unit <= 0.0:
                    raise UserError(_('You cannot confirm the blanket order without price.'))
                if requisition_line.product_qty <= 0.0:
                    raise UserError(_('You cannot confirm the blanket order without quantity.'))
                requisition_line.create_supplier_info()
            self.write({'state': 'ongoing'})
        else:
            self.write({'state': 'in_progress'})
        # Set the sequence number regarding the requisition type
        if self.name == 'New':
            self.name = self.env['ir.sequence'].with_company(self.company_id).next_by_code('purchase.requisition.code')

class PurchaseRequisitionLineInherited(models.Model):
    _inherit = "purchase.requisition.line"

    total = fields.Monetary(string="Total",store=True)
    currency_id = fields.Many2one('res.currency', 'Currency', required=True, related='company_id.currency_id')

    @api.onchange('price_unit','product_qty')
    def validate_total(self):
        if self.price_unit:
            self.total= self.product_qty * self.price_unit

    # @api.depends('product_qty', 'price_unit')
    # def _compute_amount(self):
    #     for line in self:
    #         tax_results = self.env['account.tax']._compute_taxes([line._convert_to_tax_base_line_dict()])
    #         # totals = next(iter(tax_results['totals'].values()))
    #         # amount_untaxed = totals['amount_untaxed']
    #         # amount_tax = totals['amount_tax']
    #         #
    #         # line.update({
    #         #     'total': amount_untaxed,
    #         #     'price_tax': amount_tax,
    #         #     'price_total': amount_untaxed + amount_tax,
    #         # })
    #
    #
    #
    # def _convert_to_tax_base_line_dict(self):
    #     """ Convert the current record to a dictionary in order to use the generic taxes computation method
    #     defined on account.tax.
    #
    #     :return: A python dictionary.
    #     """
    #     self.ensure_one()
    #     return self.env['account.tax']._convert_to_tax_base_line_dict(
    #         self,
    #         currency=self.requisition_id.currency_id,
    #         product=self.product_id,
    #         price_unit=self.price_unit,
    #         quantity=self.product_qty,
    #         total=self.total,
    #     )


