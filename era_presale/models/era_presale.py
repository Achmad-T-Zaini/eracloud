# Copyright 2023 Achmad T. Zaini - achmadtz@gmail.com
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError

from datetime import date, datetime, time
from dateutil import relativedelta



class EraPresale(models.Model):
    _name = "era.presale"
    _description = "ERA Presale"

    def _get_domain(self):
        domain = [('parent_id','=',False)]
        if self.parent_id:
            domain = ['|',('id','=',self.parent_id.department_id.id),('parent_id','=',self.parent_id.department_id.id)]
        return domain

    name = fields.Char(string='Order Reference', required=True, copy=False, store=True)
    order_id = fields.Many2one('sale.order', string='Order ID')
    company_id = fields.Many2one(
        "res.company", "Company", default=lambda self: self.env.company
    )
    presale_type = fields.Selection(selection=[
            ('presale','Presale'),
            ('trial','Trial'),
            ('poc','POC'),
            ('preproduction','Pre Production'),
            ('production','Production'),
        ], string='Type', copy=False, tracking=True,
        default='presale')
    user_id = fields.Many2one('res.users', 'User')
    description = fields.Text(string='Descriptions')
    state = fields.Selection(selection=[
            ('draft', 'Request'),
            ('process', 'Processing'),
            ('running', 'Running'),
            ('terminating', 'Terminating'),
            ('done', 'Done'),
        ], string='Status', required=True, readonly=True, copy=False, tracking=True,
        default='draft')
    date_from = fields.Date(string='From', copy=False, store=True, required=True, readonly=True, states={'draft': [('readonly', False)]})
    date_to = fields.Date(string='To', copy=False, store=True, required=True, readonly=True, states={'draft': [('readonly', False)]})
    product_id = fields.Many2one(
        comodel_name='product.product',
        string="Product",
        change_default=True, ondelete='restrict', check_company=True, index='btree_not_null',
        domain="[('bom_ids','!=',False),('sale_ok', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    sales_id = fields.Many2one(
        comodel_name='res.users',
        string="Salesperson",)
    team_id = fields.Many2one(
        comodel_name='crm.team',
        string="Sales Team",)
    partner_id = fields.Many2one('res.partner', string='Partner')
    request_line_ids = fields.One2many('era.presale.bom.line', 'presale_id', 'BoM Components')


class EraPresaleBomLine(models.Model):
    _name = "era.presale.bom.line"
    _description = "ERA Presale Bill of Material Components"
    _inherit = ['mrp.bom.line']


    presale_id = fields.Many2one('era.presale', string="Presale ID")

