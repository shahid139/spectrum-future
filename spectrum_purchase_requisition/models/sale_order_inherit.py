from odoo import api, fields, models, modules, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
from collections import defaultdict


class SaleOrderInherited(models.Model):
    _inherit = "sale.order"

    state = fields.Selection([
        ('draft', 'Quotation'),
        ('sent', 'Quotation Sent'),
        ('first_approval', 'First Approve'),
        ('second_approval', 'Second Approve'),
        ('third_approval', 'Third Approve'),
        ('fourth_approval', 'Fourth Approve'),
        ('sale', 'Sale Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled')
    ], string='Status', readonly=True, index=True, copy=False, default='draft', tracking=True)

    first_approved_by = fields.Many2one('res.users', string="First Approved BY")
    second_approved_by = fields.Many2one('res.users', string="Second Approved BY")
    third_approved_by = fields.Many2one('res.users', string="Third Approved BY")
    last_approved_by = fields.Many2one('res.users', string="Last Approved By")

    first_approval_date = fields.Datetime(string="First Approval date")
    second_approval_date = fields.Datetime(string="Second Approval date")
    third_approval_date = fields.Datetime(string="Third Approval date")
    final_approval_date = fields.Datetime(string="Final Approval date")

    def first_approval(self):
        login_user = self.env.user
        approval_config = self.env['approval.configuration'].search(
            [('approval_type', '=', 'so_approval'), ('so_approval_levels', '=', 'level_1'),
             ('approved_user', 'in', login_user.id), ('is_active', '=', True)], limit=1)
        approve_users = [v.name for v in approval_config.approved_user]
        if not approval_config:
            raise UserError(
                f"You do not have permission to approve this Sale Order at the first approval level.\n"
                f"Authorized users for the first approval: {', '.join(approve_users)}"
            )
        self.write({
            'state': 'first_approval',
            'first_approved_by':self.env.user.id,
            'first_approval_date':datetime.now()
        })

    def second_approval(self):
        login_user = self.env.user
        approval_config = self.env['approval.configuration'].search(
            [('approval_type', '=', 'so_approval'), ('so_approval_levels', '=', 'level_2'),
             ('approved_user', 'in', login_user.id), ('is_active', '=', True)], limit=1)
        approve_users = [v.name for v in approval_config.approved_user]
        if not approval_config:
            raise UserError(
                f"You do not have permission to approve this Sale Order at the second approval level.\n"
                f"Authorized users for the first approval: {', '.join(approve_users)}"
            )
        self.write({
            'state': 'second_approval',
            'second_approved_by':self.env.user.id,
            'second_approval_date': datetime.now()

        })

    def third_approval(self):
        login_user = self.env.user
        approval_config = self.env['approval.configuration'].search(
            [('approval_type', '=', 'so_approval'), ('so_approval_levels', '=', 'level_3'),
             ('approved_user', 'in', login_user.id), ('is_active', '=', True)], limit=1)
        approve_users = [v.name for v in approval_config.approved_user]
        if not approval_config:
            raise UserError(
                f"You do not have permission to approve this Sale Order at the Third approval level.\n"
                f"Authorized users for the first approval: {', '.join(approve_users)}"
            )
        self.write({
            'state': 'third_approval',
            'third_approved_by': self.env.user.id,
            'third_approval_date': datetime.now()
        })

    def fourth_approval(self):
        self.write({
            'state': 'fourth_approval',
            'last_approved_by': self.env.user.id,
            'final_approval_date': datetime.now()
        })

    def _can_be_confirmed(self):
        self.ensure_one()
        return self.state in {'draft', 'sent', 'fourth_approval'}

    def sale_order_auto_approval(self):
        first_approval_stage = self.env['sale.order'].search([('state' , '=', 'draft')])
        second_approval_stage = self.env['sale.order'].search([('state', '=', 'first_approval')])

        print(f"first_approval_stage >>>>>> :{first_approval_stage}")
        print(f"second_approval_stage >>>>>> :{second_approval_stage}")

        current_time = fields.Datetime.now()

        if first_approval_stage:
            for s_order in first_approval_stage:
                if s_order.create_date and (current_time - s_order.create_date) > timedelta(minutes=240):
                    print(f"Auto approving purchase order {s_order.name} created at {s_order.create_date} : {current_time}")
                    s_order.first_approval()  # Call first approval function

        if second_approval_stage:
            for s_order in second_approval_stage:
                if s_order.first_approval_date and (current_time - s_order.first_approval_date) > timedelta(minutes=240):
                    print(f"Auto approving purchase order {s_order.name} created at {s_order.first_approval_date} : {current_time}")
                    s_order.second_approval()


class SaleOrderLineInherit(models.Model):
    _inherit = "sale.order.line"


    last_selling_price = fields.Float(string='Last selling price', compute='_compute_last_price_unit',
                                   store=True)  # Added store=True

    @api.depends('product_id')  # Important: Add dependency on product_id
    def _compute_last_price_unit(self):
        for line in self:
            if line.product_id:
                last_selling_price = self.env['sale.order.line'].search([
                    ('product_id', '=', line.product_id.id),
                    ('state', 'in', ['sale', 'done']),  # Consider only confirmed or done sales
                ], order='id desc', limit=1)

                if last_selling_price:
                    line.last_selling_price = last_selling_price.price_unit  # Use price_unit, not unit_price
                else:
                    line.last_selling_price = 0.0  # Default to 0 if no prior sale
            else:
                line.last_selling_price = 0.0  # Default to 0 if no product

    # @api.depends('product_id', 'company_id')
    # def _compute_tax_id(self):
    #     lines_by_company = defaultdict(lambda: self.env['sale.order.line'])
    #     cached_taxes = {}
    #     for line in self:
    #         lines_by_company[line.company_id] += line
    #     for company, lines in lines_by_company.items():
    #         print(company,'-------------------->>>>')
    #         for line in lines.with_company(company):
    #             taxes = None
    #             if line.product_id:
    #                 taxes = line.product_id.taxes_id._filter_taxes_by_company(company)
    #             if not line.product_id or not taxes:
    #                 # Nothing to map
    #                 line.tax_id = False
    #                 continue
    #             fiscal_position = line.order_id.fiscal_position_id
    #             cache_key = (fiscal_position.id, company.id, tuple(taxes.ids))
    #             cache_key += line._get_custom_compute_tax_cache_key()
    #             if cache_key in cached_taxes:
    #                 result = cached_taxes[cache_key]
    #             else:
    #                 result = fiscal_position.map_tax(taxes)
    #                 cached_taxes[cache_key] = result
    #             # If company_id is set, always filter taxes by the company
    #             print(result,'====================')
    #             if result.company_id.currency_id.name == 'SAR':
    #                 line.tax_id = result
