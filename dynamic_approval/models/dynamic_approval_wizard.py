# -*- coding: utf-8 -*-
from odoo import api, fields, models


class DynamicApprovalWizard(models.TransientModel):
    _name = 'dynamic.approval.wizard'
    _description = 'Wizard Dynamic Approval'

    record_id = fields.Reference(selection='_select_target_model', string="Document")
    mode = fields.Selection(string="Approval Mode", selection=[
        ('approve', 'Approve'),
        ('resubmit', 'Resubmit'),
        ('reject', 'Reject')], default='approve')
    note = fields.Text(string="Note", required=False, )

    @api.model
    def _select_target_model(self):
        models = self.env['ir.model'].sudo().search([])
        return [(model.model, model.name) for model in models]

    def action_confirm(self):
        self.record_id.dynamic_do_approve(self.mode, self.note)
