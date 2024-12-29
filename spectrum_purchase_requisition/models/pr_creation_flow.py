from odoo import api, fields, models, modules, _
from odoo.exceptions import UserError


class PurchaseRequisitionCreation(models.Model):
    _inherit = "purchase.requisition"

    business_unit = fields.Many2one('business.unit', string='Select BU',required=True)
    project_id = fields.Many2one('project.project',string="Select Project")
    pr_type = fields.Many2one('purchase.requisition.type',string="Select PR Type",required=True)
    account_id = fields.Many2one('account.analytic.account',string="Select Natural Account",required=True)
    budget_task = fields.Many2one('crossovered.budget',string="Select Budget Task",required=True)

    def action_in_progress(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("You cannot confirm agreement '%s' because there is no product line.", self.name))
        if self.budget_task:
            planned_amount = sum([v.planned_amount for v in self.budget_task.crossovered_budget_line])
            practical_amount = sum([v.practical_amount for v in self.budget_task.crossovered_budget_line])
            requisition_amount = sum([v.total for v in self.line_ids])
            available_amount = planned_amount-practical_amount
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

    total = fields.Float(string="Total")

    @api.onchange('price_unit')
    def validate_total(self):
        if self.price_unit:
            self.total= self.product_qty * self.price_unit


