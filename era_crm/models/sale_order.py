# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero, float_compare, float_round


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    manufacture_id = fields.Many2one('mrp.production', string='Manufacture Order', readonly=True)
    lead_id = fields.Many2one('crm.lead', string='CRM Lead', readonly=True)
    quotation_no = fields.Char(string='Quotation', store=True, readonly=True)
    quotation_rev = fields.Integer(string='Rev.', store=True, readonly=True, default=1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'company_id' in vals:
                self = self.with_company(vals['company_id'])
            if vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['date_order'])
                ) if 'date_order' in vals else None
                vals['name'] = "New CRM"
                era_code = 'SG'
                if vals.get('lead_id',False):
                    lead_id = self.env['crm.lead'].browse(vals['lead_id'])
                    era_code = lead_id.team_id.team_initial + '-' + lead_id.user_id.partner_id.partner_initial
                vals['quotation_no']= self.env['ir.sequence'].next_by_code_era(
                    'quotation.sequence', era_code,sequence_date=seq_date) or _("New")
        return super().create(vals_list)


    def action_confirm(self):
        res = super().action_confirm()
        mto = self.order_line.filtered(lambda l: l.product_id.bom_count>0)
        if mto:
            manufacture_order = self.env['mrp.production'].create({
                            'product_id': mto[0].product_id.id,
                        })
            manufacture_order.action_confirm()
            self.update({ 'manufacture_id': manufacture_order.id})

        return res

    @api.onchange('order_line','order_line.product_uom_qty','order_line.price_unit','order_line.discount',
                  'lead_id', 'lead_id.summary_order_line', 'lead_id.summary_order_line.product_uom_qty', 'lead_id.summary_order_line.price_unit',
                  'lead_id.order_line','lead_id.order_line.product_uom_qty','lead_id.order_line.price_unit','lead_id.order_line.discount','lead_id.expected_revenue')        
    def _onchange_order_line(self):
        if self.lead_id:
            line_section = self.order_line.filtered(lambda x: x.display_type=='line_section')
            line_subtotal = self.order_line.filtered(lambda x: x.display_type=='line_subtotal')
            if line_section:
                to_remove = self.lead_id.summary_order_line.filtered(lambda l: l.order_sequence not in [line_section.order_sequence])
                if to_remove:
                    self.lead_id.summary_order_line = [(3,to_remove.id)]
                    to_remove = self.order_line.filtered(lambda l: l.order_sequence not in [line_section.order_sequence])
                    self.order_line = [(3,tr.id) for tr in to_remove]
#                raise UserError(_('section %s\n%s')%(line_section,to_remove))

            for section in line_subtotal:
                line_product = self.order_line.filtered(lambda x: x.order_sequence==section.order_sequence and x.product_id and x.order_type==section.order_type )
#                raise UserError(_('line %s')%(line_product))
                line_subtotal = sum(line.product_uom_qty*line.crm_price_unit for line in line_product) or 0
                if line_product and line_subtotal>0:
                    pto_update = self.lead_id.summary_order_line.filtered(lambda l: l.order_sequence ==section.order_sequence and l.order_type==section.order_type)
                    if pto_update:
                        pto_update.write({'product_uom_qty': section.product_uom_qty,'price_unit': line_subtotal,})
                    sol_update = self.order_line.filtered(lambda l: l.order_sequence ==section.order_sequence and l.order_type==section.order_type and l.display_type=='line_subtotal')
                    if sol_update:
                        sol_update.write({'price_unit': line_subtotal,})


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    _order = 'order_id, order_sequence, sequence, product_categ_id, id'

    _sql_constraints = [
        ('accountable_required_fields',
            "CHECK(display_type IS NOT NULL OR (product_id IS NOT NULL AND product_uom IS NOT NULL))",
            "Missing required fields on accountable sale order line."),
        ('non_accountable_null_fields',
            "CHECK(display_type IS NULL OR product_id IS NULL )",
            "Forbidden values on non-accountable sale order line"),
    ]

    lead_id = fields.Many2one('crm.lead', string='CRM Lead', related="order_id.lead_id")
    pricelist_id = fields.Many2one('product.pricelist', string="Pricelist", related="order_id.pricelist_id")
    partner_id = fields.Many2one('res.partner',string='Customer', related="order_id.partner_id")
    tax_country_id = fields.Many2one(
        comodel_name='res.country',
        compute='_compute_tax_country_id',
        # Avoid access error on fiscal position when reading a sale order with company != user.company_ids
        compute_sudo=True)  # used to filter available taxes depending on the fiscal country and position
    fiscal_position_id = fields.Many2one('account.fiscal.position',string='Fiscal Position', related='order_id.fiscal_position_id')
    display_type = fields.Selection(
        selection=[
            ('line_section', "Section"),
            ('line_note', "Note"),
            ('line_subtotal', "Subtotal"),
        ],
        default=False)
    order_type = fields.Selection(
        [('product', 'Product'),
         ('service', 'Service')],
        string='Type',store=True)
    order_sequence = fields.Float(string='Order Sequence', default=0.0)
    recurrence_id = fields.Many2one('sale.temporal.recurrence', string='Recurrence', )

    crm_price_unit = fields.Float(
        string="Unit Price",
        compute='_compute_price_unit',
        digits='Product Price',
        store=True, readonly=False, required=True, precompute=True)
    crm_price_subtotal = fields.Monetary(
        string="Subtotal",
        compute='_compute_amount',
        store=True, precompute=True)
    product_categ_id = fields.Many2one('product.category',string='Product Category', required=True, store=True)


    @api.onchange('display_type','product_id')
    def _onchange_display_type_era(self):
        if self.display_type=='line_section' and not self.order_sequence:
            order_sequence = 0
            if self.order_id.order_line:
                order_sequence = self.order_id.order_line.sorted(key='order_sequence', reverse=True)[0].order_sequence
            self.order_sequence = order_sequence+1
        elif self.product_id and not self.order_sequence:
#            order_sequence = self.order_id.order_line.sorted(key='order_sequence', reverse=True)[0].order_sequence+1
#            self.order_sequence = order_sequence
            self.product_categ_id = self.product_id.categ_id.id
            self.lead_id._calculate_subtotal(self)
#            raise UserError(_('vals %s \n %s')%(self.order_sequence,self.product_id.detailed_type))


    def _convert_to_tax_base_line_dict_crm(self):
        """ Convert the current record to a dictionary in order to use the generic taxes computation method
        defined on account.tax.

        :return: A python dictionary.
        """
        self.ensure_one()
        return self.env['account.tax']._convert_to_tax_base_line_dict(
            self,
            partner=self.order_id.partner_id,
            currency=self.order_id.currency_id,
            product=self.product_id,
            taxes=self.tax_id,
            price_unit=self.crm_price_unit,
            quantity=self.product_uom_qty,
            discount=self.discount,
            price_subtotal=self.crm_price_subtotal,
        )

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

            crm_tax_results = self.env['account.tax']._compute_taxes([line._convert_to_tax_base_line_dict_crm()])
            crm_totals = list(crm_tax_results['totals'].values())[0]
            crm_amount_untaxed = crm_totals['amount_untaxed']
            crm_amount_tax = crm_totals['amount_tax']

            line.update({
                'crm_price_subtotal': crm_amount_untaxed,
#                'price_tax': crm_amount_tax,
#                'crm_price_total': crm_amount_untaxed + crm_amount_tax,
            })

    def _compute_price_unit(self):
        for line in self:
            # check if there is already invoiced amount. if so, the price shouldn't change as it might have been
            # manually edited
            if line.display_type!='line_subtotal':
                if line.qty_invoiced > 0:
                    continue
                if not line.product_uom or not line.product_id or not line.order_id.pricelist_id:
                    line.price_unit = 0.0
                    line.crm_price_unit = 0.0
                else:
                    if line.crm_price_unit==0:
                        price = line.with_company(line.company_id)._get_display_price()
                    else:
                        price=line.crm_price_unit

                    line.crm_price_unit = line.product_id._get_tax_included_unit_price(
                        line.company_id,
                        line.order_id.currency_id,
                        line.order_id.date_order,
                        'sale',
                        fiscal_position=line.order_id.fiscal_position_id,
                        product_price_unit=price,
                        product_currency=line.currency_id
                    )

    @api.depends('company_id')
    def _compute_tax_country_id(self):
        for record in self:
            if record.fiscal_position_id.foreign_vat:
                record.tax_country_id = record.fiscal_position_id.country_id
            else:
                record.tax_country_id = record.company_id.account_fiscal_country_id

    def unlink(self):
        for rec in self:
            if rec.lead_id and rec.display_type not in ('line_subtotal','line_discount'):
                return super().unlink()

    @api.model
    def create(self, vals):
        res = super().create(vals)
        if vals.get('product_id',False):
            product_id = self.env['product.product'].browse(vals['product_id'])
            vals.update({'order_type': product_id.detailed_type,})
        if vals.get('display_type',False) and vals['display_type']=='line_subtotal':
            vals.update({'product_uom_qty': 1,})
#        raise UserError(_('vals %s \n %s')%(vals,product_id.detailed_type))
            
        return res
    
    