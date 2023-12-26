# -*- coding: utf-8 -*-
from odoo import api, fields, models


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    dynamic_approval_id = fields.Many2one(comodel_name="dynamic.approval", string="Dynamic Approval Source",
                                          ondelete="cascade")
