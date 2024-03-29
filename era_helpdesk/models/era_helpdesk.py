# Copyright 2023 Achmad T. Zaini - achmadtz@gmail.com
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import ast
import datetime

from dateutil import relativedelta
from collections import defaultdict
from pytz import timezone
from odoo import api, Command, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError
from odoo.osv import expression
from odoo.tools import float_round
from odoo.addons.helpdesk.models.helpdesk_ticket import TICKET_PRIORITY
from odoo.addons.rating.models.rating_data import RATING_LIMIT_MIN
from odoo.addons.web.controllers.utils import clean_action


class HelpdeskTeam(models.Model):
    _inherit = "helpdesk.team"

class HelpdeskStage(models.Model):
    _inherit = "helpdesk.stage"

    is_solved = fields.Boolean(string='Solved', default=False, copy=False, store=True)
    is_closed = fields.Boolean(string='Closed', default=False, copy=False, store=True)

class HelpdeskTicketType(models.Model):
    _inherit = 'helpdesk.ticket.type'

    is_change_service = fields.Boolean(string='Change Service', default=False, copy=False, store=True)
    scope_type = fields.Selection([
        ('all', 'All'),
        ('cust', 'Customer'),
        ('non', 'Non Customer'),
    ], default='cust')

class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'
    _order = "date"

class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    def _default_domain_member_ids_era(self):
        if self.team_id:
            domain = [('share', '=', False), ('id', 'in', self.team_id.member_ids.ids)]
        else:
            domain = [('share', '=', False), ('active', '=', True)]
        return domain

    def _default_domain_partner_ids(self):
        return [('sale_order_count', '>', 0)]

    user_id = fields.Many2one(
        'res.users', string='Assigned to', compute='_compute_user_and_stage_ids', store=True,
        readonly=False, tracking=True,
#        domain=lambda self: [('groups_id', 'in', self.env.ref('helpdesk.group_helpdesk_user').id)]
        domain=lambda self: self._default_domain_member_ids_era(),
        )

    partner_id = fields.Many2one('res.partner', string='Customer', tracking=True,
        domain=lambda self: self._default_domain_partner_ids(),
                                 )

    @api.onchange('team_id')
    def _onchange_team_id(self):
        domain = {'domain': {'user_id': [('share', '=', False), ('id', 'in', self.team_id.member_ids.ids)]}}
        return domain      
    
    open_case = fields.Datetime('Open Case') 
    resolution_date = fields.Datetime('Resolution Date', copy=False, readonly=True, store=True)
    resolution_time = fields.Float('Resolution Time', copy=False, related='total_hours_spent', store=True)
    response_date = fields.Datetime('Response Date', copy=False, store=True, readonly=True)

    order_id = fields.Many2one('sale.order', string='Ref. Sales Order',
        domain="""[
            ('partner_id', 'child_of', partner_id),
            ('state','in',['sale','done']),
            ('company_id', '=', company_id)]""",
        )
    sale_order_line_id = fields.Many2one('sale.order.line', string='Services', 
        domain="""[
            ('order_partner_id', 'child_of', partner_id),
            ('state','in',['sale']),
            ('product_id.detailed_type','=','product'),]""",
        )
    product_tmpl_id = fields.Many2one('product.template', string='Product',)
    bom_id = fields.Many2one('mrp.bom', 'Bill of Materials',)
    bom_line_ids = fields.One2many('mrp.bom.line', 'bom_id', 'Component', copy=False, related="bom_id.bom_line_ids")
    is_change_service = fields.Boolean(string='Change Service', related="ticket_type_id.is_change_service")
    is_solved = fields.Boolean(string='Solved', store=True)
    is_closed = fields.Boolean(string='Closed', store=True)
    instalation_notes = fields.Html(sanitize_attributes=False, readonly=False, related="sale_order_line_id.manufacture_id.instalation_notes")

    @api.onchange('stage_id')
    def _onchange_stage_id_era(self):
        if not self.user_id:
            raise UserError(_("There's No assignment yet!!!"))
        employee_id = self.env['hr.employee'].search([('user_id','=', self.env.user.id)])
        if not employee_id:
            raise UserError(_("Assigned user is not an Employee..."))
        if self.is_closed:
            raise UserError(_('Closed Ticket, can not be changed!'))
        elif self.is_solved and not self.stage_id.is_closed:
            raise UserError(_('Solved Ticket or Closed Ticket, can not be changed!'))
        elif self.stage_id.is_closed:
            self.is_closed = True
        elif self.stage_id.is_solved:
            self.is_solved = True
            self.resolution_date = fields.Datetime.now()
            self.timesheet_ids = [(0,0,{'date': self.resolution_date, 
                                        'user_id': self.env.user.id,
                                        'employee_id': employee_id.id,
                                        'name': 'Solved by ' + self.env.user.name})]


    @api.onchange('partner_id')
    def _onchange_partner_era(self):
        self.sale_order_line_id = False
        self.order_id = False
        domain = {'domain': {'sale_order_line_id': [('state', '=','sale' ),('product_id.detailed_type','=','product'),]}}
        if self.partner_id:
            order_line = self.env['sale.order.line'].search([('order_partner_id','=',self.partner_id.id),('state','in',['sale'])])
            domain = {'domain': {'sale_order_line_id': [('id', 'in', order_line.ids),('product_id.detailed_type','=','product'),]}}
        return domain


    @api.onchange('sale_order_line_id')
    def _onchange_order_line_id_era(self):
        self.product_tmpl_id = False
        self.bom_id = False
        if self.sale_order_line_id:
            self.product_tmpl_id = self.sale_order_line_id.product_id.product_tmpl_id
            self.bom_id = self.product_tmpl_id.bom_ids[0].id if self.product_tmpl_id.bom_ids else False
            self.order_id = self.sale_order_line_id.order_id.id

    def action_submit(self):
        self.update({'open_case': fields.Datetime.now(), })
        self.send_notif('Ticket %s need your Immediate Response'% self.name,"New Ticket",self.user_id)
        self.stage_id = self.env['helpdesk.stage'].search([('sequence','=',self.stage_id.sequence+1)])

    def action_confirm_era(self):
        self.update({'response_date' : fields.Datetime.now(), })
        self.action_timer_start()
        employee_id = self.env['hr.employee'].search([('user_id','=', self.env.user.id)])
        self.timesheet_ids = [(0,0,{'date': self.response_date, 
                                    'user_id': self.env.user.id,
                                    'employee_id': employee_id.id,
                                    'name': 'First Respons'})]


    def send_notif(self,message_body,message_subject,partner):
        if partner.notification_type=='inbox':
            if partner:
                self.env['mail.message'].create({'message_type':"notification",
                    "subtype_id": self.env.ref("mail.mt_activities").id, # subject type
                    'body': message_body,
                    'subject': message_subject,
                    'partner_ids': [(4, partner.partner_id.id)],   # partner to whom you send notification
                    'notification_ids': [
                                        (0, 0, {
                                            'res_partner_id': partner.partner_id.id,
                                            'notification_type': 'inbox'
                                        }),
                                    ],
                    'model': self._name,
                    'res_id': self.id,
                    })
        elif partner.notification_type=='email':
            # search the email template based on external id
            template = self.env.ref('era_helpdesk.new_ticket_submit_assign_email_template', raise_if_not_found=False)
            if template:
                self.with_context(is_reminder=True).message_post_with_template(template.id, composition_mode='comment')

    def _compute_partner_ticket_count(self):

        def _get_email_to_search(email):
            domain = tools.email_domain_extract(email)
            return ("@" + domain) if domain else email

        for ticket in self:
            domain = []
            partner_ticket = ticket
            if ticket.partner_email:
                email_search = _get_email_to_search(ticket.partner_email)
                domain = expression.OR([domain, [('partner_email', 'ilike', email_search)]])
            if ticket.partner_phone:
                domain = expression.OR([domain, [('partner_phone', 'ilike', ticket.partner_phone)]])
            if ticket.partner_id:
                domain = expression.OR([domain, [("partner_id", "child_of", ticket.partner_id.commercial_partner_id.id)]])
            if domain:
                partner_ticket = self.search(domain)
            ticket.partner_ticket_ids = partner_ticket
            partner_ticket = partner_ticket - ticket._origin
            ticket.partner_ticket_count = len(partner_ticket) if partner_ticket else 0
            open_ticket = partner_ticket.filtered(lambda t: t.is_solved==False and t.is_closed==False)
            ticket.partner_open_ticket_count = len(open_ticket)

class HelpdeskSla(models.Model):
    _inherit = 'helpdesk.sla'

    response_time = fields.Float('Response Time')
    next_team_id = fields.Many2one('helpdesk.team', string='Next Team')
