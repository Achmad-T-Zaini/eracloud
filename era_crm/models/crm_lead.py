# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.osv import expression
from odoo.tools import float_is_zero, float_compare, float_round
from odoo.tools import get_timedelta

class Lead(models.Model):
    _inherit = "crm.lead"

    user_id = fields.Many2one(
        'res.users', string='Salesperson', default=lambda self: self.env.user,
        domain="['&', ('share', '=', False), ('company_ids', 'in', user_company_ids)]",
        check_company=True, index=True, tracking=True)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  required=True, readonly=True,
                                  default=lambda self: self.env.company.currency_id.id)
    order_id = fields.Many2one('sale.order',string='Order ID',readonly=True, copy=False)
    order_line = fields.One2many('sale.order.line','lead_id', string='Order Line')
    summary_order_line = fields.One2many('crm.order.summary','lead_id', string='Order Summary')
    expected_revenue = fields.Monetary('Expected Revenue', compute="_compute_expected_revenue",
                                       currency_field='company_currency', tracking=True)
    partner_shipping_id = fields.Many2one(
        comodel_name='res.partner',
        string="Delivery Address",
        compute='_compute_partner_shipping_id',
        store=True, readonly=False, required=True, precompute=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",)

    fiscal_position_id = fields.Many2one(
        comodel_name='account.fiscal.position',
        string="Fiscal Position",
        compute='_compute_fiscal_position_id',
        store=True, readonly=False, precompute=True, check_company=True,
        help="Fiscal positions are used to adapt taxes and accounts for particular customers or sales orders/invoices."
            "The default value comes from the customer.",
        domain="[('company_id', '=', company_id)]")
    pricelist_id = fields.Many2one(
        comodel_name='product.pricelist',
        string="Pricelist",
        compute='_compute_pricelist_id',
        store=True, readonly=False, precompute=True, check_company=True, required=True,  # Unrequired company
        tracking=1,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="If you change the pricelist, only newly added lines will be affected.")
    tax_totals = fields.Binary(compute='_compute_tax_totals', exportable=False)
    is_won = fields.Boolean(string='is Won', related='stage_id.is_won')
    recurrence_id = fields.Many2one('sale.temporal.recurrence', string='Recurrence', ondelete='restrict', readonly=False, store=True)
    duration = fields.Integer('Periode', default=12)
    term_condition = fields.Text(string='Term & Conditions',)
    order_template_id = fields.Many2one('crm.template', string='Order Template', domain="[('type','=','product')]")
#    dynamic_approval_state = fields.Selection(string="Approval Mode", selection=[
#        ('approve', 'Approve'),
#        ('resubmit', 'Resubmit'),
#        ('reject', 'Reject')], default='approve')
    
    @api.onchange('team_id')
    def _onchange_team_id(self):
        self.user_id = False
        domain = {'domain': {'user_id': [('share', '=', False), ('company_ids', 'in', self.team_id.member_company_ids.ids,)]}}

        users = self.env['res.users'].search([('id','=',self.team_id.member_ids.ids)])
#        raise UserError(_('cek %s\n%s')%(users,domain))
        if users:
            domain['domain']['user_id']= [('share', '=', False), ('company_ids', 'in', self.team_id.member_company_ids.ids,),('id', 'in', users.ids)]
        return domain      

    @api.onchange('order_id', 'order_id.order_line','order_id.order_line.product_uom_qty','order_id.order_line.price_unit','order_id.order_line.discount',
            'order_line','order_line.product_uom_qty','order_line.price_unit','order_line.discount','expected_revenue', 'order_id.amount_total')        
    def _onchange_order_line(self):
        if self.order_id:
            line_section = self.order_line.filtered(lambda x: x.display_type=='line_section')
            line_subtotal = self.order_line.filtered(lambda x: x.display_type=='line_subtotal')
            if line_section:
                to_remove = self.summary_order_line.filtered(lambda l: l.order_sequence not in [line_section.order_sequence])
                if to_remove:
                    self.summary_order_line = [(3,l.id) for l in to_remove]
                    to_remove = self.order_line.filtered(lambda l: l.order_sequence not in [line_section.order_sequence])
                    self.order_line = [(3,tr.id) for tr in to_remove]
            else:
                self.summary_order_line = [(6,0,[])]
                self.order_line = [(6,0,[])]
                    
            for section in line_subtotal:
                line_product = self.order_line.filtered(lambda x: x.order_sequence==section.order_sequence and x.product_id and x.order_type==section.order_type )
#                raise UserError(_('line %s')%(line_product))
                line_subtotal = sum(line.product_uom_qty*line.price_unit for line in line_product) or 0
                if line_product and line_subtotal>0:
                    pto_update = self.summary_order_line.filtered(lambda l: l.order_sequence ==section.order_sequence and l.order_type==section.order_type)
                    if pto_update:
                        pto_update.write({'product_uom_qty': section.product_uom_qty,'price_unit': line_subtotal,})
                    sol_update = self.order_line.filtered(lambda l: l.order_sequence ==section.order_sequence and l.order_type==section.order_type and l.display_type=='line_subtotal')
                    if sol_update:
                        sol_update.write({'price_unit': line_subtotal,})

    def action_get_template(self):
        if self.order_template_id:
            order_line = []
            summary_order_line = []
            subtotal = 0
            order_type = 'product'
            if len(self.order_line)>0:
                sequence = self.order_line.sorted(key='sequence', reverse=True)[0].sequence+1
            else:
                sequence = 9
            order_sequence = len(self.order_line.filtered(lambda l: l.display_type=='line_section'))+1
            order_line.append((0,0,{ 'sequence': sequence, 'name': self.order_template_id.name, 'display_type': 'line_section','order_sequence': order_sequence,}))
            for line in self.order_template_id.component:
                if order_type!=line.order_type:
                    order_line.append((0,0,{ 'name': self.order_template_id.name + ' ' + order_type.capitalize() + ' Subtotal', 
                                            'product_uom_qty': 1, 'price_unit': subtotal,'sequence': sequence, 'order_type': order_type,
                                            'display_type': 'line_subtotal','order_sequence': order_sequence, 
                                            'recurrence_id': self.order_template_id.recurrence_id.id}))
                    summary_order_line.append((0,0,{ 'name': self.order_template_id.name + ' ' + order_type.capitalize(), 
                                            'product_uom_qty': 0, 'price_unit': subtotal, 'order_type': order_type,
                                            'order_sequence': order_sequence,'recurrence_id': self.order_template_id.recurrence_id.id}))
                    order_type = line.order_type
                    subtotal = 0
                order_line.append((0,0,{ 'product_id': line.product_id.id, 'product_uom_qty': line.product_uom_qty,'sequence': sequence, 'order_sequence': order_sequence,}))
                subtotal += line.product_uom_qty * max(line.product_id.list_price,line.product_id.lst_price)
                sequence+=1
            order_line.append((0,0,{ 'name': self.order_template_id.name + ' ' + order_type.capitalize() + ' Subtotal', 
                                            'product_uom_qty': 1, 'price_unit': subtotal,'sequence': sequence, 'order_type': order_type,
                                            'display_type': 'line_subtotal','order_sequence': order_sequence,
                                            'recurrence_id': self.order_template_id.recurrence_id.id}))
            summary_order_line.append((0,0,{ 'name': self.order_template_id.name + ' ' + order_type.capitalize(), 
                                            'product_uom_qty': 0, 'price_unit': subtotal, 'order_type': order_type,
                                            'order_sequence': order_sequence,'recurrence_id': self.order_template_id.recurrence_id.id}))
            self.order_line = order_line
            self.summary_order_line = summary_order_line
            self.order_template_id = False

    @api.depends('order_id', 'order_id.amount_total', 'currency_id','order_line','order_line.price_unit','order_line.product_uom_qty')
    def _compute_expected_revenue(self):
        for order in self:
            expected_revenue = 0
            expected_revenue = sum(line.price_subtotal for line in order.order_line)
            order.update({'expected_revenue': expected_revenue,})
#            order.order_id.update({'amount_total': expected_revenue,})


    @api.depends('order_line.tax_id', 'order_line.price_unit', 'expected_revenue', 'currency_id')
    def _compute_tax_totals(self):
        for order in self:
            order_lines = order.order_line.filtered(lambda x: not x.display_type)
            order.tax_totals = self.env['account.tax']._prepare_tax_totals(
                [x._convert_to_tax_base_line_dict() for x in order_lines],
                order.currency_id or order.company_id.currency_id,
            )

    @api.depends('partner_id')
    def _compute_pricelist_id(self):
        for order in self:
            if not order.partner_id:
                order.pricelist_id = False
                continue
            order = order.with_company(order.company_id)
            order.pricelist_id = order.partner_id.property_product_pricelist

    
    @api.depends('partner_id')
    def _compute_partner_shipping_id(self):
        for order in self:
            order.partner_shipping_id = order.partner_id.address_get(['delivery'])['delivery'] if order.partner_id else False


    @api.depends('partner_id', 'company_id')
    def _compute_fiscal_position_id(self):
        """
        Trigger the change of fiscal position when the shipping address is modified.
        """
        cache = {}
        for order in self:
            if not order.partner_id:
                order.fiscal_position_id = False
                continue
            key = (order.company_id.id, order.partner_id.id, order.partner_shipping_id.id)
            if key not in cache:
                cache[key] = self.env['account.fiscal.position'].with_company(
                    order.company_id
                )._get_fiscal_position(order.partner_id, order.partner_shipping_id)
            order.fiscal_position_id = cache[key]

    def action_sale_quotations_new(self):
        if not self.partner_id:
            return self.env["ir.actions.actions"]._for_xml_id("sale_crm.crm_quotation_partner_action")
        else:
#            return self.action_new_quotation()
            order_id = self.env['sale.order'].create({'partner_id': self.partner_id.id, 'lead_id': self.id,
                                                      'team_id': self.team_id.id, 'user_id': self.user_id.id,})
            self.order_id = order_id.id
            term_condition = self.env['crm.template'].search([('is_default_tc','=',True)],limit=1)
            if term_condition:
                self.term_condition = term_condition.value_text 

    def write(self,vals):
        if vals.get('order_line',False):
            for line in vals['order_line']:
                if line[2]!=False:
                    line[2].update({'order_id': self.order_id.id,})
        return super().write(vals)

class Lead(models.Model):
    _name = "crm.order.summary"
    _description = "CRM Order Summary"

    currency_id = fields.Many2one('res.currency', string='Currency',
                                  required=True, readonly=True,
                                  default=lambda self: self.env.company.currency_id.id)
    lead_id = fields.Many2one('crm.lead',string='CRM ID',readonly=True, copy=False)
    name = fields.Char(string='Name', copy=False,)
    product_uom_qty = fields.Float(
        string="Quantity",
        default=1.0,
        store=True, readonly=False, required=True)
    product_uom = fields.Many2one(
        comodel_name='uom.uom',
        string="Unit of Measure",
        store=True, readonly=False,)
    price_unit = fields.Float(
        string="Unit Price",
        compute='_compute_price_unit',
        digits='Product Price',
        store=True, readonly=False, required=True, precompute=True)
    discount = fields.Float(
        string="Discount (%)",
        digits='Discount',
        store=True, readonly=False, precompute=True)
    discount_type = fields.Selection(
        selection=[
            ('percent', "Percentage"),
            ('amount', "Amount"),
            ('periode', "Periode"),
        ],
        string="Disc Type",
        store=True)
    price_subtotal = fields.Monetary(
        string="Subtotal",
        compute='_compute_amount',
        store=True, precompute=True)
    price_discount = fields.Monetary(
        string="Discount",
        compute='_compute_amount',
        store=True, precompute=True)
    price_total = fields.Monetary(
        string="Total",
        compute='_compute_amount',
        store=True, precompute=True)
    order_type = fields.Selection(
        [('product', 'Product'),
         ('service', 'Service')],
        string='Type',store=True)
    order_sequence = fields.Float(string='Order Sequence',)
    recurrence_id = fields.Many2one('sale.temporal.recurrence', string='Recurrence', )

    @api.depends('product_uom_qty', 'discount', 'price_unit')
    def _compute_amount(self):
        """
        Compute the amounts of the SO line.
        """
        for line in self:
#            tax_results = self.env['account.tax']._compute_taxes([line._convert_to_tax_base_line_dict()])
#            totals = list(tax_results['totals'].values())[0]
#            amount_untaxed = totals['amount_untaxed']
#            amount_tax = totals['amount_tax']

            line.update({
                'price_subtotal': line.price_unit * line.product_uom_qty,
#                'price_tax': amount_tax,
                'price_total': (line.price_unit * line.product_uom_qty),
            })

    @api.onchange('product_uom_qty', 'discount', 'price_unit', 'price_subtotal', 'price_total')
    def _onchange_qty_disc_price(self):
        line_subtotal = self.env['sale.order.line'].search([('display_type','=','line_subtotal'),
                                                            ('order_sequence','=',self.order_sequence),
                                                            ('order_type','=',self.order_type)])
        if line_subtotal:
            line_subtotal.update({'product_uom_qty': self.product_uom_qty,
                                  'price_unit': self.price_unit,
            #                      'discount': self.discount,
                                  })
            