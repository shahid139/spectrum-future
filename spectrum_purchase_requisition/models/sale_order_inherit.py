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
    sequence = fields.Char(default=lambda self: _('New'))


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'company_id' in vals:
                self = self.with_company(vals['company_id'])

            # If the custom sequence field is missing, create a sequence
            if vals.get('sequence', _("New")) == _("New"):
                # Use 'date_order' to generate sequence based on the correct date
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['date_order'])
                ) if 'date_order' in vals else None

                # Replace 'name' with the 'sequence' field to generate sequence number
                vals['sequence'] = self.env['ir.sequence'].next_by_code(
                    'sale.order.1', sequence_date=seq_date
                ) or _("New")
                vals['name'] = "Sales Quotation"
        return super(SaleOrderInherited, self).create(vals_list)

    def action_confirm(self):
        """ Confirm the given quotation(s) and set their confirmation date.

        If the corresponding setting is enabled, also locks the Sale Order.

        :return: True
        :rtype: bool
        :raise: UserError if trying to confirm cancelled SO's
        """
        seq_date = fields.Datetime.context_timestamp(
            self, fields.Datetime.to_datetime(self.date_order)
        ) if self.date_order else None
        self.name = self.env['ir.sequence'].next_by_code(
            'sale.order', sequence_date=seq_date) or _("New")
        if not all(order._can_be_confirmed() for order in self):
            raise UserError(_(
                "The following orders are not in a state requiring confirmation: %s",
                ", ".join(self.mapped('display_name')),
            ))

        self.order_line._validate_analytic_distribution()

        for order in self:
            order.validate_taxes_on_sales_order()
            if order.partner_id in order.message_partner_ids:
                continue
            order.message_subscribe([order.partner_id.id])

        self.write(self._prepare_confirmation_values())

        # Context key 'default_name' is sometimes propagated up to here.
        # We don't need it and it creates issues in the creation of linked records.
        context = self._context.copy()
        context.pop('default_name', None)

        self.with_context(context)._action_confirm()

        self.filtered(lambda so: so._should_be_locked()).action_lock()

        if self.env.context.get('send_email'):
            self._send_order_confirmation_mail()

        return True



    def first_approval(self):
        if not self.order_line:
            raise UserError("No products found in the order. Please add products before proceeding.")
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
