# -*- coding: utf-8 -*-
# from odoo import http


# class CustomPurchaseOrderReport(http.Controller):
#     @http.route('/custom_purchase_order_report/custom_purchase_order_report', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/custom_purchase_order_report/custom_purchase_order_report/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('custom_purchase_order_report.listing', {
#             'root': '/custom_purchase_order_report/custom_purchase_order_report',
#             'objects': http.request.env['custom_purchase_order_report.custom_purchase_order_report'].search([]),
#         })

#     @http.route('/custom_purchase_order_report/custom_purchase_order_report/objects/<model("custom_purchase_order_report.custom_purchase_order_report"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('custom_purchase_order_report.object', {
#             'object': obj
#         })

