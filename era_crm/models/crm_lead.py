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

    order_line = fields.One2many('lead.order.line','lead_id', string='Order Line')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  required=True, readonly=True,
                                  default=lambda self: self.env.company.currency_id.id)

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

    tax_totals = fields.Binary(compute='_compute_tax_totals', exportable=False)
    is_won = fields.Boolean(string='is Won', related='stage_id.is_won')
    recurrence_id = fields.Many2one('sale.temporal.recurrence', string='Recurrence', ondelete='restrict', readonly=False, store=True)
    duration = fields.Integer('Periode', default=12)
#    dynamic_approval_state = fields.Selection(string="Approval Mode", selection=[
#        ('approve', 'Approve'),
#        ('resubmit', 'Resubmit'),
#        ('reject', 'Reject')], default='approve')

    def action_create_order(self):
        order_line =  []
        tax_id = []
        sub_total = 0.0
        qty = 0.0
        for line in self.order_line:
            order_line.append((0, 0, {
                                    'product_id': line.product_id.id,
                                    'name': line.name,
                                    'product_uom_qty': line.product_uom_qty,
                                    'product_uom': line.product_uom.id,
                                    'price_unit': 0,
                            }))
            sub_total += line.price_subtotal
            qty = line.product_uom_qty
            tax_id = [(6, 0, line.tax_id.ids)]
        subscription_product = self.env['product.product'].search([('sale_ok','=',True),('recurring_invoice','=',True),('product_tag_ids','=','VPS')],limit=1)
        if not subscription_product:
            raise UserError(_('No Subscription Product'))
        order_line.append((0, 0, {
                                    'product_id': subscription_product.id,
                                    'name': subscription_product.name,
                                    'product_uom_qty': qty,
                                    'product_uom': subscription_product.uom_id.id,
                                    'price_unit': sub_total,
                                    'tax_id': tax_id,
                            }))
        
        so_vals = {'opportunity_id': self.id, 
                   'partner_id': self.partner_id.id, 
                   'campaign_id': self.campaign_id.id, 
                   'medium_id': self.medium_id.id, 
                   'origin': self.name, 
                   'order_line': order_line, 
                   'company_id': self.company_id.id, 
                   'tag_ids': [(6, 0, [])], 
                   'team_id': self.team_id.id, 
                   'user_id': self.user_id.id, 
#                   'is_invoice_cron': True,
                   'recurrence_id': self.recurrence_id.id,
                   'end_date': fields.Date.today() + get_timedelta(self.duration, self.recurrence_id.unit),
                   }

#        raise UserError(_('context %s')%(so_vals))
        sale_order_id = self.env['sale.order'].create(so_vals)
        sale_order_id.action_confirm()
#        return action
    

    def write(self,vals):
        old_stage = self._origin.stage_id
        res = super(Lead,self).write(vals)
#        if vals.get('stage_id',False):
#            if self.dynamic_approval_state != 'approved' and self.stage_id.is_won:
#                raise UserError(_('Only APPROVED Lead can be WON...'))
        
        return res

    @api.depends('order_line.tax_id', 'order_line.price_unit', 'currency_id')
    def _compute_tax_totals(self):
        for order in self:
            order_lines = order.order_line
            order.tax_totals = self.env['account.tax']._prepare_tax_totals(
                [x._convert_to_tax_base_line_dict() for x in order_lines],
                order.currency_id or order.company_id.currency_id,
            )

    @api.depends('partner_id')
    def _compute_partner_shipping_id(self):
        for order in self:
            order.partner_shipping_id = order.partner_id.address_get(['delivery'])['delivery'] if order.partner_id else False

    @api.depends('order_line','order_line.price_total')
    def _compute_expected_revenue(self):
        for rec in self:
            expected_revenue = 0.0
            if rec.order_line:
                expected_revenue = sum(line.price_total for line in rec.order_line)
            rec.expected_revenue = expected_revenue

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


class LeadOrderLine(models.Model):
    _name = 'lead.order.line'
    _description = "Lead/Opportunity Order Line"

    lead_id = fields.Many2one('crm.lead', string='Order Line')
    # Order-related fields
    company_id = fields.Many2one(
        related='lead_id.company_id',
        store=True, index=True, precompute=True)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  required=True, readonly=True,
                                  default=lambda self: self.env.company.currency_id.id)
    order_partner_id = fields.Many2one(
        related='lead_id.partner_id',
        string="Customer",
        store=True, index=True, precompute=True)
    salesman_id = fields.Many2one(
        related='lead_id.user_id',
        string="Salesperson",
        store=True, precompute=True)
    # Generic configuration fields
    product_id = fields.Many2one(
        comodel_name='product.product',
        string="Product",
        change_default=True, ondelete='restrict', check_company=True, index='btree_not_null',
        domain="[('product_tag_ids', 'ilike', 'Virtual'),('sale_ok', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    product_uom_category_id = fields.Many2one(related='product_id.uom_id.category_id', depends=['product_id'])
    name = fields.Text(
        string="Description",
        compute='_compute_name',
        store=True, readonly=False, required=True, precompute=True)

    product_uom_qty = fields.Float(
        string="Quantity",
#        compute='_compute_product_uom_qty',
        digits='Product Unit of Measure', default=1.0,
        store=True, readonly=False, required=True, precompute=True)
    product_uom = fields.Many2one(
        comodel_name='uom.uom',
        string="Unit of Measure",
        compute='_compute_product_uom',
        store=True, readonly=False, precompute=True, ondelete='restrict',
        domain="[('category_id', '=', product_uom_category_id)]")

    # Pricing fields
    tax_id = fields.Many2many(
        comodel_name='account.tax',
        string="Taxes",
        compute='_compute_tax_id',
        store=True, readonly=False, precompute=True,
        context={'active_test': False},
        check_company=True)
    price_unit = fields.Float(
        string="Unit Price",
        compute='_compute_price_unit',
        digits='Product Price',
        store=True, readonly=False, required=True, precompute=True)
    price_subtotal = fields.Monetary(
        string="Subtotal",
        compute='_compute_amount',
        store=True, precompute=True)
    price_tax = fields.Float(
        string="Total Tax",
        compute='_compute_amount',
        store=True, precompute=True)
    price_total = fields.Monetary(
        string="Total",
        compute='_compute_amount',
        store=True, precompute=True)


    @api.depends('product_id', 'product_uom')
    def _compute_price_unit(self):
        for line in self:
            if not line.product_id:
                continue
            document_type = 'sale'
            line.price_unit = line.product_id._get_tax_included_unit_price(
                line.lead_id.company_id,
                line.lead_id.currency_id,
                line.lead_id.create_date,
                document_type,
                fiscal_position=line.lead_id.fiscal_position_id,
                product_uom=line.product_uom,
            )

    @api.depends('product_id')
    def _compute_name(self):
        for line in self:
            if not line.product_id:
                continue
            line.name = line.product_id.name


    @api.depends('product_id', 'product_packaging_qty')
    def _compute_product_uom_qty(self):
        for line in self:
            if line.display_type:
                line.product_uom_qty = 0.0
                continue

            if not line.product_packaging_id:
                continue
            packaging_uom = line.product_packaging_id.product_uom_id
            qty_per_packaging = line.product_packaging_id.qty
            product_uom_qty = packaging_uom._compute_quantity(
                line.product_packaging_qty * qty_per_packaging, line.product_uom)
            if float_compare(product_uom_qty, line.product_uom_qty, precision_rounding=line.product_uom.rounding) != 0:
                line.product_uom_qty = product_uom_qty

    @api.depends('product_id')
    def _compute_product_uom(self):
        for line in self:
            if not line.product_uom or (line.product_id.uom_id.id != line.product_uom.id):
                line.product_uom = line.product_id.uom_id

    @api.depends('product_id', 'company_id')
    def _compute_tax_id(self):
        taxes_by_product_company = defaultdict(lambda: self.env['account.tax'])
        lines_by_company = defaultdict(lambda: self.env['lead.order.line'])
        cached_taxes = {}
        for line in self:
            lines_by_company[line.company_id] += line
        for product in self.product_id:
            for tax in product.taxes_id:
                taxes_by_product_company[(product, tax.company_id)] += tax
        for company, lines in lines_by_company.items():
            for line in lines.with_company(company):
                taxes = taxes_by_product_company[(line.product_id, company)]
                if not line.product_id or not taxes:
                    # Nothing to map
                    line.tax_id = False
                    continue
                fiscal_position = line.lead_id.fiscal_position_id
                cache_key = (fiscal_position.id, company.id, tuple(taxes.ids))
                if cache_key in cached_taxes:
                    result = cached_taxes[cache_key]
                else:
                    result = fiscal_position.map_tax(taxes)
                    cached_taxes[cache_key] = result
                # If company_id is set, always filter taxes by the company
                line.tax_id = result

    def _convert_to_tax_base_line_dict(self):
        """ Convert the current record to a dictionary in order to use the generic taxes computation method
        defined on account.tax.

        :return: A python dictionary.
        """
        self.ensure_one()
        return self.env['account.tax']._convert_to_tax_base_line_dict(
            self,
            partner=self.lead_id.partner_id,
            currency=self.lead_id.currency_id,
            product=self.product_id,
            taxes=self.tax_id,
            price_unit=self.price_unit,
            quantity=self.product_uom_qty,
#            discount=self.discount,
            price_subtotal=self.price_subtotal,
        )

    @api.depends('product_uom_qty', 'price_unit', 'tax_id')
    def _compute_amount(self):
        """
        Compute the amounts of the SO line.
        """
        for line in self:
            tax_results = self.env['account.tax']._compute_taxes([line._convert_to_tax_base_line_dict()])
            totals = list(tax_results['totals'].values())[0]
            amount_untaxed = totals['amount_untaxed']
            amount_tax = totals['amount_tax']

            line.update({
                'price_subtotal': amount_untaxed,
                'price_tax': amount_tax,
                'price_total': amount_untaxed + amount_tax,
            })
