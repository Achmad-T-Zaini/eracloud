# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero, float_compare, float_round


class CRMTemplate(models.Model):
    _name = 'crm.template'
    _description = 'CRM Template for Eranya'



    name = fields.Char(string='Name', copy=False)
    type = fields.Selection(string="Template Type", selection=[
        ('tc', 'Term and Conditions'),
        ('product', 'Order Template'),
        ])
    component = fields.One2many('crm.template.line','crm_tmpl_id',string='Template')
    value_text = fields.Text(string='Term & Conditions')
    company_id = fields.Many2one(
        "res.company", "Company", default=lambda self: self.env.company
    )
    recurrence_id = fields.Many2one('sale.temporal.recurrence', string='Recurrence')
    is_default_tc = fields.Boolean('Default')


class CRMTemplateLine(models.Model):
    _name = 'crm.template.line'
    _description = 'CRM Template Line for Eranya'
    _order = "order_type"

    name = fields.Char(string='Name', copy=False)
    crm_tmpl_id = fields.Many2one('crm.template',string='Template')
    recurrence_id = fields.Many2one('sale.temporal.recurrence', string='Recurrence', related="crm_tmpl_id.recurrence_id", required=True,)
    order_type = fields.Selection(
        [('product', 'Product'),
         ('service', 'Service')],
        string='Type', related="product_id.type",store=True)
    product_id = fields.Many2one(
        comodel_name='product.product',
        string="Product",
        domain="[('type','in',['product','service']),('sale_ok', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    product_uom_qty = fields.Float(
        string="Quantity",
        compute='_compute_product_uom_qty',
        digits='Product Unit of Measure', default=1.0,
        store=True, readonly=False, required=True, precompute=True)
    product_uom = fields.Many2one(
        comodel_name='uom.uom',
        string="Unit of Measure",
        compute='_compute_product_uom',
        store=True, readonly=False, precompute=True, ondelete='restrict',
        domain="[('category_id', '=', product_uom_category_id)]")
    company_id = fields.Many2one(
        "res.company", "Company", default=lambda self: self.env.company
    )
    product_uom_category_id = fields.Many2one(related='product_id.uom_id.category_id', depends=['product_id'])
    product_packaging_id = fields.Many2one(
        comodel_name='product.packaging',
        string="Packaging",
        compute='_compute_product_packaging_id',
        store=True, readonly=False, precompute=True,
        domain="[('sales', '=', True), ('product_id','=',product_id)]",
        check_company=True)
    product_packaging_qty = fields.Float(
        string="Packaging Quantity",
        compute='_compute_product_packaging_qty',
        store=True, readonly=False, precompute=True)
    product_categ_id = fields.Many2one('product.category', related="product_id.categ_id" ,string='Product Category', required=True, store=True)

    @api.depends('product_id')
    def _compute_product_uom_qty(self):
        for line in self:
            line.product_uom_qty = 0.0

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

    @api.depends('product_id', 'product_uom_qty', 'product_uom')
    def _compute_product_packaging_id(self):
        for line in self:
            # remove packaging if not match the product
            if line.product_packaging_id.product_id != line.product_id:
                line.product_packaging_id = False
            # Find biggest suitable packaging
            if line.product_id and line.product_uom_qty and line.product_uom:
                line.product_packaging_id = line.product_id.packaging_ids.filtered(
                    'sales')._find_suitable_product_packaging(line.product_uom_qty, line.product_uom) or line.product_packaging_id

    @api.depends('product_packaging_id', 'product_uom', 'product_uom_qty')
    def _compute_product_packaging_qty(self):
        for line in self:
            if not line.product_packaging_id:
                line.product_packaging_qty = False
            else:
                packaging_uom = line.product_packaging_id.product_uom_id
                packaging_uom_qty = line.product_uom._compute_quantity(line.product_uom_qty, packaging_uom)
                line.product_packaging_qty = float_round(
                    packaging_uom_qty / line.product_packaging_id.qty,
                    precision_rounding=packaging_uom.rounding)
