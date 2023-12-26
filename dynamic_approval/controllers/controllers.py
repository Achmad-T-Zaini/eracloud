# -*- coding: utf-8 -*-
# from odoo import http


# class DynamicApproval(http.Controller):
#     @http.route('/dynamic_approval/dynamic_approval/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/dynamic_approval/dynamic_approval/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('dynamic_approval.listing', {
#             'root': '/dynamic_approval/dynamic_approval',
#             'objects': http.request.env['dynamic_approval.dynamic_approval'].search([]),
#         })

#     @http.route('/dynamic_approval/dynamic_approval/objects/<model("dynamic_approval.dynamic_approval"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('dynamic_approval.object', {
#             'object': obj
#         })
