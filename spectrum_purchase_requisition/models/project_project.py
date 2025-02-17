from odoo import api, fields, models, modules, _


# Add fields in the project model
class ProjectBudget(models.Model):
    _inherit = 'project.project'

    total_budget = fields.Float(string="Total Budget", required=True, tracking=True,help="Initial budget allocated for the project")
    spent_amount = fields.Float(string="Spent Amount", compute="_compute_spent_amount", store=True)
    available_budget = fields.Float(string="Available Budget", compute="_compute_available_budget", store=True)
    account_invoice_ids = fields.One2many('account.move', 'project_id', string="Invoices")
    budget_history = fields.One2many('budget.history','budget_project_id')

    def write(self, vals):
        if 'total_budget' in vals:
            # Capture the old and new values
            old_value = self.total_budget
            new_value = vals.get('total_budget')

            # Create a new record in budget_history
            history_entry = {
                'old_value': old_value,
                'new_value': new_value,
                'write_date': fields.Datetime.now(),  # Optional field for timestamp
                'write_uid': self.env.user.id  # Optional field for tracking user
            }

            # Append the new entry to budget_history
            self.budget_history = [(0, 0, history_entry)]

        return super(ProjectBudget, self).write(vals)

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

class BudgetHistory(models.Model):
    _name = 'budget.history'

    old_value = fields.Float(string="Old Value")
    new_value = fields.Float(string="New Value")
    budget_project_id = fields.Many2one('project.project')





