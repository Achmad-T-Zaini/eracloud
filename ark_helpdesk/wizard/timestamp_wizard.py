# -*- coding: utf-8 -*-
from odoo import models, fields
from datetime import datetime

class HelpdeskTimestampWizard(models.TransientModel):
    _name = 'helpdesk.timestamp.wizard'
    _description = 'Helpdesk Timestamp Wizard'

    helpdesk_id = fields.Many2one('helpdesk.ticket', string='helpdesk')
    reason = fields.Char('Reason')

    def action_pause(self):
        self.helpdesk_id.timestamp_line.create({
            'name': self.reason,
            'timestamp': datetime.now(),
            'timestamp_type': 'in',
            'helpdesk_id': self.helpdesk_id.id
        })