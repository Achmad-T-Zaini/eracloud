# Copyright 2023 Achmad T. Zaini - achmadtz@gmail.com
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import ast
import datetime

from dateutil import relativedelta
from collections import defaultdict
from pytz import timezone
from odoo import api, Command, fields, models, _
from odoo.exceptions import ValidationError
from odoo.osv import expression
from odoo.tools import float_round
from odoo.addons.helpdesk.models.helpdesk_ticket import TICKET_PRIORITY
from odoo.addons.rating.models.rating_data import RATING_LIMIT_MIN
from odoo.addons.web.controllers.utils import clean_action


class HelpdeskTeam(models.Model):
    _inherit = "helpdesk.team"


class HelpdeskTicketType(models.Model):
    _inherit = 'helpdesk.ticket.type'

    is_change_service = fields.Boolean(string='Change Service', default=False, copy=False, store=True)


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
    
    open_case = fields.Datetime('Open Case',related="create_date") 
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
            ('order_id', '=', sale_order_id),
            ('product_id.detailed_type','=','product'),]""",
        )
    product_tmpl_id = fields.Many2one('product.template', string='Product',)
    bom_id = fields.Many2one('mrp.bom', 'Bill of Materials',)
    bom_line_ids = fields.One2many('mrp.bom.line', 'bom_id', 'Component', copy=False, related="bom_id.bom_line_ids")
    is_change_service = fields.Boolean(string='Change Service', related="ticket_type_id.is_change_service")

    @api.onchange('order_id')
    def _onchange_order_id_era(self):
        self.sale_order_line_id = False

    @api.onchange('sale_order_line_id')
    def _onchange_order_line_id_era(self):
        self.product_tmpl_id = False
        self.bom_id = False
        if self.sale_order_line_id:
            self.product_tmpl_id = self.sale_order_line_id.product_id.product_tmpl_id
            self.bom_id = self.product_tmpl_id.bom_ids[0].id if self.product_tmpl_id.bom_ids else False


class HelpdeskSla(models.Model):
    _inherit = 'helpdesk.sla'

    response_time = fields.Float('Response Time')
    next_team_id = fields.Many2one('helpdesk.team', string='Next Team')
