# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime



class HelpdeskSla(models.Model):
    _inherit = 'helpdesk.sla'

    response_time = fields.Float('Response Time')
    next_team_id = fields.Many2one('helpdesk.team', string='Next Team')

class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    sla_id = fields.Many2one('helpdesk.sla', copy=False, string='SLA Policies') 
    open_case = fields.Datetime('Open Case',related="create_date") 
    response_date = fields.Datetime('Response', copy=False, compute='compute_from_state', store=True)
    response_time = fields.Float('Response Time', copy=False, compute='compute_from_state', store=True)
    resolution_date = fields.Datetime('Resolution', copy=False, compute='compute_from_state', store=True)
    resolution_time = fields.Float('Resolution Time', copy=False, compute='compute_from_state', store=True)
    response_time_display = fields.Char('Response Time' ,compute='_compute_time',store=True)
    resolution_time_display = fields.Char('Resolution Time',compute='_compute_time',store=True)
    timestamp_line = fields.One2many('helpdesk.timestamp', 'helpdesk_id', string='timestamp', copy=False)
    is_paused = fields.Boolean('Is Paused',default=False, copy=False)

    def button_pause(self):
        action = self.env["ir.actions.actions"]._for_xml_id("ark_helpdesk.action_pause")
        action['context'] = {'default_helpdesk_id': self.id}
        self.is_paused = True
        return action

    def button_unpause(self):
        pause = self.env['helpdesk.timestamp'].search([('helpdesk_id','=',self.id),('timestamp_type','=','in')],limit=1, order='timestamp desc')
        if pause and self.is_paused:
            self.timestamp_line.create({
                'helpdesk_id': self.id,
                'name': 'unpause',
                'timestamp': datetime.now(),
                'timestamp_type': 'out',
                'duration': (datetime.now() - pause.timestamp).days * 24 * 60 + (datetime.now() - pause.timestamp).seconds/60
            })
            self.is_paused = False

    @api.depends('stage_id')
    def compute_from_state(self):
        for rec in self:
            if rec.stage_id.sequence == 0:
                rec.response_date = False
                rec.response_time = 0
                rec.resolution_date = False
                rec.resolution_time = 0
                rec.resolution_time_display = False
                rec.response_time_display = False
            if rec.stage_id.sequence == 1:
                if not rec.response_date:
                    rec.response_date = datetime.now()
                    rec.response_time = (rec.response_date - rec.open_case).days*24*60 + (rec.response_date - rec.open_case).seconds/60 
                rec.resolution_date = False
                rec.resolution_time_display = False
                rec.resolution_time = 0
            if rec.stage_id.sequence == 3:
                if rec.response_date:
                    rec.resolution_date = datetime.now()
                    rec.resolution_time =(rec.resolution_date - rec.response_date).days*24*60 + (rec.resolution_date - rec.response_date).seconds/60 - sum(rec.timestamp_line.mapped('duration'))

    def convert_time_to_string(self,time):
        hours, seconds = divmod(time * 60, 3600)
        minutes, seconds = divmod(seconds, 60)
        return "{:02.0f}:{:02.0f}:{:02.0f}".format(hours, minutes, seconds)

    @api.depends('response_time','resolution_time')
    def _compute_time(self):
        for rec in self:
            if rec.response_time:
                rec.response_time_display = rec.convert_time_to_string(rec.response_time)
            if rec.resolution_time:
                rec.resolution_time_display = rec.convert_time_to_string(rec.resolution_time)

class HelpdeskTimestamp(models.Model):
    _name = 'helpdesk.timestamp'

    helpdesk_id = fields.Many2one('helpdesk.ticket', string='helpdesk')    
    timestamp = fields.Datetime('Timestamp')
    name = fields.Char('Reason')
    timestamp_type = fields.Selection([
        ('in', 'Break in'),
        ('out', 'Break out'),
    ], string='Type')
    duration = fields.Float('Duration')