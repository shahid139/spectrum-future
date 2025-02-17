from odoo import api, fields, models, modules, _


# Add fields in the project model
class ProjectBudget(models.Model):
    _inherit = 'project.project'

    total_budget = fields.Float(string="Total Budget", required=True, help="Initial budget allocated for the project")
    spent_amount = fields.Float(string="Spent Amount", compute="_compute_spent_amount", store=True)
    available_budget = fields.Float(string="Available Budget", compute="_compute_available_budget", store=True)
    account_invoice_ids = fields.One2many('account.move', 'project_id', string="Invoices")

    @api.depends('account_invoice_ids.amount_total')
    def _compute_spent_amount(self):
        """ Calculate the total spent amount for the project. """
        for project in self:
            invoices = self.env['account.move'].search([('project_id', '=', project.id), ('state', '=', 'posted')])
            project.spent_amount = sum(invoice.amount_total for invoice in invoices)

    @api.depends('total_budget', 'spent_amount')
    def _compute_available_budget(self):
        """ Calculate the available budget. """
        for project in self:
            project.available_budget = project.total_budget - project.spent_amount


