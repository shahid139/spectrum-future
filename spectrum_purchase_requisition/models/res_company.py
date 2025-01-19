from odoo import api, fields, models, modules, _
from odoo.exceptions import UserError
from deep_translator import GoogleTranslator

class CompanyInherited(models.Model):
    _inherit = 'res.company'

    vat_number = fields.Char(string="VAT No.")
    cr_number = fields.Char(string="CR No.")

    trans_comapany_name = fields.Char()
    trans_street = fields.Char()
    trans_street2 = fields.Char()
    trans_city = fields.Char()
    trans_state_id = fields.Char()
    trans_country_id = fields.Char()

    @api.onchange('name','street','street2','city','state_id','zip','country_id')
    def _validate_translator(self):
        if self.name:
            translated_text = GoogleTranslator(source='en', target='ar').translate(str(self.name))
            self.trans_comapany_name = translated_text
        if self.street:
            street_translated_text = GoogleTranslator(source='en', target='ar').translate(str(self.street))
            self.trans_street = street_translated_text
        if self.street2:
            street2_translated_text = GoogleTranslator(source='en', target='ar').translate(str(self.street2))
            self.trans_street2 = street2_translated_text
        if self.city:
            city_translated_text = GoogleTranslator(source='en', target='ar').translate(str(self.city))
            self.trans_city = city_translated_text
        if self.state_id:
            state_translated_text = GoogleTranslator(source='en', target='ar').translate(str(self.state_id.name))
            self.trans_state_id = state_translated_text
        if self.country_id:
            country_translated_text = GoogleTranslator(source='en', target='ar').translate(str(self.country_id.name))
            self.trans_country_id = country_translated_text




