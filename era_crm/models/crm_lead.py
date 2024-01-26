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

    def _get_domain_team(self):
        domain = [('share', '=', False), ('company_ids', 'in', self.team_id.member_company_ids.ids,)]
        if self.team_id:
            users = self.env['res.users'].search([('id','=',self.team_id.member_ids.ids)])
            domain = [('share', '=', False), ('company_ids', 'in', self.team_id.member_company_ids.ids,),('id', 'in', users.ids)]
        return domain      

    user_id = fields.Many2one(
        'res.users', string='Salesperson', default=lambda self: self.env.user,
        domain="['&', ('share', '=', False), ('company_ids', 'in', user_company_ids)]",
#        domain=_get_domain_team,
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
    order_template_id = fields.Many2one('mrp.bom', string='Order Template')
#    order_template_id = fields.Many2one('crm.template', string='Order Template', domain="[('type','=','product')]")
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

    def action_approve(self):
        raise UserError(_('action_approve'))


    @api.onchange('order_id', 'order_id.order_line', 'order_id.order_line.product_id','order_id.order_line.product_uom_qty','order_id.order_line.price_unit','order_id.order_line.discount',
            'order_line','order_line.product_uom_qty','order_line.price_unit','order_line.discount','order_line.product_id','expected_revenue', 'order_id.amount_total',
            'order_line.crm_price_unit','order_id.order_line.crm_price_unit',)        
    def _onchange_order_line(self):
        if self.order_id:
            line_section = self.order_line.filtered(lambda x: x.display_type=='line_section')
            if line_section:
                to_remove = []
                for line in line_section:
                    to_remove.append(line.order_sequence)
#                line2remove = self.summary_order_line.filtered(lambda l: l.order_sequence not in [to_remove])
#                if line2remove:
#                    self.summary_order_line = [(3,l.id) for l in line2remove]
#                    to_remove = self.order_line.filtered(lambda l: l.order_sequence not in [to_remove])
#                    self.order_line = [(3,tr.id) for tr in to_remove]

            elif not line_section:
                self.summary_order_line = [(6,0,[])]
                self.order_line = [(6,0,[])]
                    
            line_subtotal = self.order_line.filtered(lambda x: x.display_type=='line_subtotal')
            for section in line_subtotal:
                section.crm_price_unit = 0
                section.price_unit = 0
                line_header = self.order_line.filtered(lambda x: x.display_type=='line_section' and x.order_sequence==section.order_sequence)
                to_upd_seq =  self.order_line.filtered(lambda x: x.sequence>=line_header[0].sequence and x.sequence<=section.sequence)
                for line in to_upd_seq:
                    line.update({'order_sequence': section.order_sequence}) 
                line_product = self.order_line.filtered(lambda x: x.order_sequence==section.order_sequence and x.product_id and x.product_categ_id.id==section.product_categ_id.id )
#                raise UserError(_('line %s\n%s')%(to_upd_seq,line_product))
                line_subtotal = sum(line.product_uom_qty*line.crm_price_unit for line in line_product) or 0
                if line_product:
                    pto_update = self.summary_order_line.filtered(lambda l: l.order_sequence ==section.order_sequence and l.product_categ_id.id==section.product_categ_id.id)
                    if pto_update:
                        pto_update.update({'product_uom_qty': section.product_uom_qty,'price_unit': line_subtotal,})
                    sol_update = self.order_line.filtered(lambda l: l.order_sequence ==section.order_sequence and l.product_categ_id.id==section.product_categ_id.id and l.display_type=='line_subtotal')
                    if sol_update:
                        sol_update.update({'price_unit': line_subtotal,'crm_price_unit': line_subtotal,})

    def _calculate_subtotal(self,order_line=False):
        new_subtotal = self.order_line.filtered(lambda x: x.display_type=='line_subtotal')
        if not order_line:
            for line in new_subtotal:
                line_product = self.order_line.filtered(lambda x: x.order_sequence==line.order_sequence and x.product_categ_id.id==line.product_categ_id.id and x.product_id)
                line_summary = self.summary_order_line.filtered(lambda x: x.order_sequence==line.order_sequence and x.product_categ_id.id==line.product_categ_id.id )
                line.update({'discount': line_summary.price_discount*100,
                             'crm_price_unit': sum(lp.crm_price_subtotal for lp in line_product),})
#                line_summary.update({'price_unit': sum(lp.crm_price_subtotal for lp in line_product),})
                
#                raise UserError(_('subtotal %s\n%s = %s')%(line,line.order_sequence,line.product_categ_id.name))
        else:
            line_section = self.order_line.filtered(lambda x: x.display_type=='line_section' and x.order_sequence==order_line.order_sequence)
            if line_section.name and order_line.product_id:
                name = line_section.name + ' ' + order_line.product_id.categ_id.name.capitalize()
                if order_line.product_id.recurring_invoice:
                    name += ' ' + order_line.product_id.product_pricing_ids[0].recurrence_id.name
                new_order_line = { 'name':  name + ' Subtotal', 
                                            'product_uom_qty': 1, 
                                            'price_unit': order_line.price_unit,
                                            'crm_price_unit': order_line.price_unit,
                                            'sequence': order_line.sequence+1, 
                                            'order_type': order_line.order_type,
                                            'display_type': 'line_subtotal',
                                            'order_sequence': order_line.order_sequence,  
                                            'product_categ_id': order_line.product_categ_id.id,
                                            'lead_id': self.id,
                                            'order_id': self.order_id.id,
                                            'recurrence_id': order_line.product_id.product_pricing_ids[0].recurrence_id.id if order_line.product_id.recurring_invoice else False,
                                            }
                summary_order_line = {'name': name, 
                                            'product_uom_qty': 1, 
                                            'price_unit': order_line.price_unit,
                                            'order_type': order_line.order_type,
                                            'product_categ_id': order_line.product_categ_id.id,
                                            'order_sequence': order_line.order_sequence,  
                                            'lead_id': self.id,
                                            'recurrence_id': order_line.product_id.product_pricing_ids[0].recurrence_id.id if order_line.product_id.recurring_invoice else False,
                                            }
#                raise UserError(_('new subtotal %s\n%s')%(order_line,new_subtotal))
                ord_line = self.env['sale.order.line'].create(new_order_line)
                sum_ord_line = self.env['crm.order.summary'].create(summary_order_line)

    def get_summary_subtotal(self):
        data = []
        sum_total = self.summary_order_line.sorted(key=lambda mv: (mv.recurrence_id, mv.product_categ_id,))
        if sum_total:
            total = 0.0
            recurrence_id = categ = False
            for line in self.summary_order_line:
                if not recurrence_id:
                    recurrence_id = line.recurrence_id
                if not categ:
                    categ = line.product_categ_id

                if recurrence_id and (recurrence_id.id!=line.recurrence_id.id or categ.id!=line.product_categ_id.id):
                    data.append({'name': 'Total ' + recurrence_id.name + ' ' + categ.name,
                                 'total': total,})
                    recurrence_id = line.recurrence_id
                    categ = line.product_categ_id
                    total = line.price_total
                else:
                    total += line.price_total

            if not recurrence_id:
                data.append({'name': 'Total One Time Charge' + ' ' + categ.name,
                             'total': total,})
            else:
                data.append({'name': 'Total ' + recurrence_id.name + ' ' + categ.name,
                             'total': total,})
    #        raise UserError(_('data %s')%(data))
        return data
    
    def action_get_template(self):
        if self.order_template_id:
            order_line = []
            summary_order_line = []
            subtotal = 0
            order_type = 'product'
            product_categ_id = False
            sequence = 10
            if len(self.order_line)>0:
                sequence = self.order_line.sorted(key='sequence', reverse=True)[0].sequence+1
            order_sequence = len(self.order_line.filtered(lambda l: l.display_type=='line_section'))+1
            order_line.append((0,0,{ 'sequence': sequence, 'name': self.order_template_id.product_tmpl_id.name, 'display_type': 'line_section','order_sequence': order_sequence,}))
            sequence+=1
            for line in self.order_template_id.bom_line_ids:
                if not product_categ_id:
                    product_categ_id = line.product_id.categ_id

                name = self.order_template_id.product_tmpl_id.name + ' ' + product_categ_id.name.capitalize()
                if self.order_template_id.recurrence_id:
                    name += ' ' + self.order_template_id.recurrence_id.name

                if product_categ_id!=line.product_id.categ_id:
                    order_line.append((0,0,{ 'name': name + ' Subtotal', 
                                            'product_uom_qty': 1, 'price_unit': subtotal,'crm_price_unit': subtotal,'sequence': sequence, 'order_type': order_type,
                                            'display_type': 'line_subtotal','order_sequence': order_sequence,  'product_categ_id': product_categ_id.id,
                                            'recurrence_id': self.order_template_id.recurrence_id.id}))
                    summary_order_line.append((0,0,{ 'name': name, 
                                            'product_uom_qty': 0, 'price_unit': subtotal, 'order_type': order_type, 'product_categ_id': product_categ_id.id,
                                            'order_sequence': order_sequence,'recurrence_id': self.order_template_id.recurrence_id.id}))
                    product_categ_id = line.product_id.categ_id
                    name = self.order_template_id.product_tmpl_id.name + ' ' + product_categ_id.name.capitalize()
                    subtotal = 0
                order_line.append((0,0,{ 'product_id': line.product_id.id, 'product_uom_qty': line.product_qty,'sequence': sequence, 'order_sequence': order_sequence,'product_categ_id': product_categ_id.id,}))
                subtotal += line.product_qty * max(line.product_id.list_price,line.product_id.lst_price)
                sequence+=1
            order_line.append((0,0,{ 'name': name + ' Subtotal', 
                                            'product_uom_qty': 1, 'price_unit': subtotal,'crm_price_unit': subtotal,'sequence': sequence, 'order_type': order_type,
                                            'display_type': 'line_subtotal','order_sequence': order_sequence, 'product_categ_id': product_categ_id.id,
                                            'recurrence_id': self.order_template_id.recurrence_id.id}))
            summary_order_line.append((0,0,{ 'name': name, 
                                            'product_uom_qty': 0, 'price_unit': subtotal, 'order_type': order_type, 'product_categ_id': product_categ_id.id,
                                            'order_sequence': order_sequence,'recurrence_id': self.order_template_id.recurrence_id.id}))
            self.order_line = order_line
            self.summary_order_line = summary_order_line
            self.order_template_id = False

    @api.depends('order_id', 'order_id.amount_total', 'currency_id','order_line', 'order_line.price_unit', 'order_line.discount', 'order_line.product_uom_qty')
    def _compute_expected_revenue(self):
        for order in self:
            order._calculate_subtotal()
            expected_revenue = 0
            expected_revenue = sum(line.crm_price_subtotal for line in order.order_line.filtered(lambda l: l.display_type=='line_subtotal'))
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
        res = super().write(vals)
        if self.order_id and self.order_id.order_line:
            order_sequence = self.order_id.order_line.sorted(key='order_sequence', reverse=True)[0].order_sequence
            sol = self.order_line.filtered(lambda l: l.order_sequence==0)
            for line in sol:
                line.write({'order_sequence': order_sequence,})
                self._calculate_subtotal(line)

        new_subtotal = self.order_line.filtered(lambda x: x.display_type=='line_subtotal')
        if new_subtotal:
            for line in new_subtotal:
                line_product = self.order_line.filtered(lambda x: x.order_sequence==line.order_sequence and x.product_categ_id.id==line.product_categ_id.id and x.product_id)
                line_summary = self.summary_order_line.filtered(lambda x: x.order_sequence==line.order_sequence and x.product_categ_id.id==line.product_categ_id.id )
                line_summary.update({'price_unit': sum(lp.crm_price_subtotal for lp in line_product),})
        return res

class Lead(models.Model):
    _name = "crm.order.summary"
    _description = "CRM Order Summary"
    _order = "recurrence_id,product_categ_id"

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
#        compute='_compute_price_unit',
        digits='Product Price',
        store=True, readonly=False, required=True, precompute=True)
    discount = fields.Float(
        string="Discount",
        digits='Discount',
        store=True, readonly=False, precompute=True)
    discount_type = fields.Selection(
        selection=[
            ('percent', "Percentage"),
            ('amount', "Amount"),
            ('periode', "Periode"),
        ],
        string="Disc Type", default='percent',
        store=True)
    price_subtotal = fields.Monetary(
        string="Subtotal",
        compute='_compute_amount',
        store=True, precompute=True)
    price_discount = fields.Float(
        string="Disc (%)",
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
    product_categ_id = fields.Many2one('product.category', string='Product Category', required=True, store=True)

    @api.depends('product_uom_qty', 'discount', 'price_unit', 'discount_type')
    def _compute_amount(self):
        """
        Compute the amounts of the SO line.
        """
        for line in self:
#            tax_results = self.env['account.tax']._compute_taxes([line._convert_to_tax_base_line_dict()])
#            totals = list(tax_results['totals'].values())[0]
#            amount_untaxed = totals['amount_untaxed']
#            amount_tax = totals['amount_tax']
            price_discount = price_subtotal = price_total = 0.0
            discount = 0.0
            if line.discount_type=='percent':
                discount = line.discount * line.price_unit / 100
            elif line.discount_type=='amount':
                discount = line.discount
            
            if discount>0 and line.price_unit>0:
                price_discount = discount / line.price_unit
                price_subtotal = (line.price_unit-discount) * line.product_uom_qty

            line.update({
                'price_subtotal': price_subtotal,
                'price_discount': price_discount,
#                'price_tax': amount_tax,
                'price_total': price_subtotal,
                })
#            line_subtotal = self.lead_id.order_line.filtered(lambda x: x.display_type=='line_subtotal' and x.order_sequence==line.order_sequence and x.product_categ_id.id==line.product_categ_id.id)
#            line_subtotal.write({'discount': price_discount*100, })
            line.lead_id._calculate_subtotal()

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
            