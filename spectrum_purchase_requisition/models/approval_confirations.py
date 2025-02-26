from odoo import api, fields, models, modules, _


class ApprovalConfiguration(models.Model):
    _name = "approval.configuration"
    _rec_name = 'approval_type'

    approval_type = fields.Selection([('pr_approval','Purchase Requisition'),
                                      ('po_approval','Purchase Order'),
                                      ('so_approval','Sale Order'),
                                      ('invoice','Invoice')
                                      ],string="Approval Type",required=True)
    pr_approval_levels = fields.Selection([('level_1','Approval 1'),('level_2','Approval 2')],string="Approval Levels",default='level_1')
    po_approval_levels = fields.Selection([('level_1','Approval 1'),('level_2','Approval 2'),('level_3','Approval 3')],string="Approval Levels",default='level_1')
    so_approval_levels = fields.Selection([('level_1','Approval 1'),('level_2','Approval 2'),('level_3','Approval 3'),('level_4','Approval 4')],string="Approval Levels",default='level_1')
    invoice_approval_levels = fields.Selection([('level_1','Approval 1'),('level_2','Approval 2'),('level_3','Approval 3')],string="Approval Levels",default='level_1')
    approved_user = fields.Many2many('res.users','approval_config_rel',string="Approved Users",required=True)
    is_active = fields.Boolean(string="Active",default=True)
    project_id = fields.Many2many('project.project','approval_project_rel',string='Projects')
