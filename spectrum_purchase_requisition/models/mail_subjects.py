
from odoo import api, fields, models, modules, _

class CRMMailSubjects(models.Model):
    _name = 'mail.subject'

    name = fields.Char(string="Key",required=True)
    value = fields.Many2many('subject.subject','mail_subject_rel',required=True)


class Subjects(models.Model):
    _name = "subject.subject"

    name = fields.Char()