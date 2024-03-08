# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero, float_compare, float_round
from dateutil.relativedelta import relativedelta
from datetime import date, datetime, time, timedelta

import calendar

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    lead_id = fields.Many2one('crm.lead', string='CRM Lead', readonly=True)
    quotation_no = fields.Char(string='Quotation', store=True, readonly=True)
    quotation_rev = fields.Integer(string='Rev.', store=True, readonly=True, default=-1)
    mrp_order_line = fields.One2many('sale.order.line','mrp_order_id',string='MRP Order Line', domain="[('manufacture_id','!='.False)]")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'company_id' in vals:
                self = self.with_company(vals['company_id'])
            era_code = 'SG'
            if vals.get('lead_id',False):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['date_order'])
                ) if 'date_order' in vals else None
                lead_id = self.env['crm.lead'].browse(vals['lead_id'])
                if lead_id.team_id and lead_id.user_id and lead_id.team_id.team_initial and lead_id.user_id.partner_id.partner_initial:
                    era_code = lead_id.team_id.team_initial + '-' + lead_id.user_id.partner_id.partner_initial
                else:
                    era_code = "GN-SP"                    
                vals['quotation_no']= self.env['ir.sequence'].next_by_code_era(
                                'quotation.sequence', era_code,sequence_date=seq_date) or _("New")
                vals['name'] = vals['quotation_no']
            elif vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['date_order'])
                ) if 'date_order' in vals else None
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sale.order', sequence_date=seq_date) or _("New")
        return super().create(vals_list)


    def action_confirm(self):
        res = super().action_confirm()
        mto = self.order_line.filtered(lambda l: l.product_id.bom_count>0)
        if mto:
            picking_id = self.picking_ids[0].do_unreserve()
            for line in mto:
                manufacture_order = self.env['mrp.production'].create({
                            'product_id': mto[0].product_id.id,
                        })
                manufacture_order.action_confirm()
                line.write({ 'manufacture_id': manufacture_order.id, 'mrp_order_id': line.order_id.id, 'manufacture_state': manufacture_order.state})

        return res

    @api.onchange('order_line','order_line.product_uom_qty','order_line.price_unit','order_line.discount',
                  'lead_id', 'lead_id.summary_order_line', 'lead_id.summary_order_line.product_uom_qty', 'lead_id.summary_order_line.price_unit',
                  'lead_id.order_line','lead_id.order_line.product_uom_qty','lead_id.order_line.price_unit','lead_id.order_line.discount','lead_id.expected_revenue')        
    def _onchange_order_line(self):
        if self.lead_id:
            line_section = self.order_line.filtered(lambda x: x.display_type=='line_section')
            line_subtotal = self.order_line.filtered(lambda x: x.display_type=='line_subtotal')

            for section in line_subtotal:
                line_product = self.order_line.filtered(lambda x: x.order_sequence==section.order_sequence and x.product_id and x.order_type==section.order_type )
                line_subtotal = sum(line.product_uom_qty*line.crm_price_unit for line in line_product) or 0
                if line_product and line_subtotal>0:
                    pto_update = self.lead_id.summary_order_line.filtered(lambda l: l.order_sequence ==section.order_sequence and l.order_type==section.order_type)
                    if pto_update:
                        pto_update.write({'product_uom_qty': section.product_uom_qty,'price_unit': line_subtotal,})
                    sol_update = self.order_line.filtered(lambda l: l.order_sequence ==section.order_sequence and l.order_type==section.order_type and l.display_type=='line_subtotal')
                    if sol_update:
                        sol_update.write({'price_unit': line_subtotal,})

    @api.onchange('next_invoice_date')
    def _onchange_next_invoice_date_era(self):
        last_invoice_date = False
        next_invoice_date = False
        if self.invoice_ids:
            last_invoice_date = self.invoice_ids.filtered(lambda l: l.state=='posted').sorted(key='invoice_date', reverse=True)

        if not last_invoice_date and not next_invoice_date:
            self.next_invoice_date = self.start_date
        else:
            raise UserError(_('cek %s = %s')%(last_invoice_date,next_invoice_date))

    def _get_invoiceable_lines(self, final=False):
        if self.delivery_status=='pending':
            raise UserError(_('Product has not Delivered Yet'))
        res = super()._get_invoiceable_lines(final=final)
        invoiceable_line_ids = []
        for line in res:
            if line.invoice_status == 'to invoice' and line.recurrence_id and line.next_invoice_date<=fields.Date.today() and line.price_unit>0:
#            if line.invoice_status == 'to invoice' and line.recurrence_id and line.price_unit>0:
                invoiceable_line_ids.append(line.id)
            elif not line.recurrence_id and line.qty_invoiced==0 and line.price_unit>0:
                invoiceable_line_ids.append(line.id)
        return self.env["sale.order.line"].browse(invoiceable_line_ids)

    def action_invoice_subscription(self):
        account_move = self._create_recurring_invoice()
        if self.lead_id:
            for line in account_move.invoice_line_ids:
                if line.product_id.recurring_invoice and line.product_id.detailed_type=='service':
                    line.quantity = 1
        if account_move:
            return self.action_view_invoice()
        else:
            raise UserError(self._nothing_to_invoice_error_message())


    def _get_invoiced(self):
        # The invoice_ids are obtained thanks to the invoice lines of the SO
        # lines, and we also search for possible refunds created directly from
        # existing invoices. This is necessary since such a refund is not
        # directly linked to the SO.
        for order in self:
            invoices = order.order_line.invoice_lines.move_id.filtered(lambda r: r.move_type in ('out_invoice', 'out_refund'))
            order.invoice_ids = invoices
            order.invoice_count = len(invoices)

            next_invoice_date = order.date_order.date()
            if order.invoice_count == 0 and order.recurrence_id:
                for line in order.order_line.filtered(lambda l: l.recurrence_id):
                    line.next_invoice_date =  order.date_order.date()
            elif order.invoice_count > 0 and order.recurrence_id:
                for invoice in invoices:
                    if invoice.state=='posted':
                        next_invoice_date = datetime(year=invoice.invoice_date.year, month=invoice.invoice_date.month+1,day=1)
            order.next_invoice_date = next_invoice_date


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    _order = 'order_id, order_sequence, sequence, id'

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

    mrp_order_id = fields.Many2one('sale.order', string='MRP Order', readonly=True)
    manufacture_id = fields.Many2one('mrp.production', string='Manufacture Order', readonly=True)
    manufacture_state = fields.Char(string="Status", related="manufacture_id.workorder_status")
    next_invoice_date = fields.Date(
        string='Date of Next Invoice',
        compute='_compute_next_invoice_date',
        store=True, copy=False, tracking=True,
        readonly=False,
        help="The next invoice will be created on this date then the period will be extended.")

    @api.depends('recurrence_id','order_id', 'order_id.next_invoice_date','order_id.invoice_ids')
    def _compute_next_invoice_date(self):
        for sol in self:
            last_invoice = False
            if sol.order_id.invoice_ids and sol.invoice_lines:
                last_invoice = sol.invoice_lines.filtered(lambda l: l.move_id.state=='posted').sorted(key='date', reverse=True)
            if sol.recurrence_id:
                if sol.recurrence_id.unit=='month' and last_invoice:
                    sol.next_invoice_date = sol.order_id.next_invoice_date
            else:
                sol.next_invoice_date = False

    @api.onchange('display_type','product_id','name')
    def _onchange_display_type_era(self):
        if self.display_type=='line_section' and not self.order_sequence:
            self.order_sequence = False
        elif self.product_id and not self.order_sequence:
            self.order_sequence = False
            self.product_categ_id = self.product_id.categ_id.id

        if self.display_type=='line_section':
            subtotals = self.order_id.order_line.filtered(lambda x: x.display_type=='line_subtotal' and x.order_sequence==self.order_sequence)
            for subtotal in subtotals:
                subtotal.name = self.name + ' ' + subtotal.product_categ_id.name + ' Subtotal'
                summaries = self.lead_id.summary_order_line.filtered(lambda l: l.order_sequence==self.order_sequence and l.product_categ_id==subtotal.product_categ_id.id)
                if summaries:
                    summaries.name = subtotal.name

        if self.display_type=='line_subtotal' and (self.product_uom_qty==0 or not self.product_uom_qty):
            self.product_uom_qty = 1


    @api.onchange('sequence')
    def _onchange_sequence(self):
        if self.sequence and self.product_id and self.display_type!='line_section':
            line_subtotal = self.order_id.order_line.filtered(lambda l: l.display_type=='line_subtotal' and l.sequence>=self.sequence)
            if line_subtotal:
                line_section = self.order_id.order_line.filtered(lambda l: l.display_type=='line_section' and l.order_sequence==line_subtotal[0].order_sequence)
                if line_section:
                    if not self.product_categ_id and self.product_id.categ_id:
                        self.product_categ_id = self.product_id.categ_id.id
                    self.order_sequence = line_section.order_sequence
#            raise UserError(_('new %s = %s')%(self.sequence,self.order_sequence))

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
            vals.update({'order_type': product_id.detailed_type, 'product_categ_id': product_id.categ_id.id,})
        if vals.get('display_type',False) and vals['display_type']=='line_subtotal':
            vals.update({'product_uom_qty': 1,})
            
        return res

    def write(self, vals):
        res = super().write(vals)
        if vals.get('product_categ_id',False) and vals.get('product_id',False):
            product_id = self.env['product.product'].browse(vals['product_id'])
            vals.update({'product_categ_id': product_id.categ_id.id,})

        if (vals.get('product_uom_qty',False)==False or vals.get('product_uom_qty',False)==0 ) and vals.get('display_type',False)=='line_subtotal':
            vals.update({'product_uom_qty': 1,})

        return res


    @api.depends('product_id', 'order_id.recurrence_id')
    def _compute_pricing(self):
        # search pricing_ids for each variant in self
        available_pricing_ids = self.env['product.pricing'].search([
            ('product_template_id', 'in', self.product_id.product_tmpl_id.ids),
            ('recurrence_id', 'in', self.order_id.recurrence_id.ids),
            '|',
            ('product_template_id', 'in', self.product_id.product_tmpl_id.ids),
            ('recurrence_id', 'in', self.recurrence_id.ids),
            '|',
            ('product_variant_ids', 'in', self.product_id.ids),
            ('product_variant_ids', '=', False),
            '|',
            ('pricelist_id', 'in', self.order_id.pricelist_id.ids),
            ('pricelist_id', '=', False)
        ])
        for line in self:
            if not line.product_id.recurring_invoice:
                line.pricing_id = False
                continue
            line.pricing_id = available_pricing_ids.filtered(
                lambda pricing:
                    line.product_id.product_tmpl_id == pricing.product_template_id and (
                        line.product_id in pricing.product_variant_ids or not pricing.product_variant_ids
                    ) and (line.order_id.pricelist_id == pricing.pricelist_id or not pricing.pricelist_id)
            )[:1]

            if not line.pricing_id:
                if line.recurrence_id and line.product_id:
                    line.pricing_id = self.env['product.pricing'].search([('recurrence_id','=',line.recurrence_id.id),('product_template_id','=',line.product_id.product_tmpl_id.id)], limit=1).id

    def _prepare_invoice_line(self, **optional_values):
        res = super()._prepare_invoice_line( **optional_values)
        if self.recurrence_id.unit=='month' and self.order_id.date_order.date()==self.order_id.next_invoice_date:
            subscription_end_date = datetime(year=self.order_id.date_order.year, month=self.order_id.date_order.month+1,day=1) - relativedelta(days=1)
            num_days = calendar.monthrange(self.order_id.date_order.year, self.order_id.date_order.month)[1]
            res['name'] = res['name'][:-10] + subscription_end_date.strftime('%m/%d/%Y')
            res['price_unit'] = (self.price_unit / num_days) * (num_days - self.order_id.date_order.day +1)
            res['subscription_end_date']=subscription_end_date.date()
            self.next_invoice_date = subscription_end_date.date() + relativedelta(days=1)
        elif self.recurrence_id.unit=='year' and self.order_id.date_order.date()==self.order_id.next_invoice_date:
            subscription_end_date = datetime(year=self.order_id.date_order.year+1, month=self.order_id.date_order.month,day=self.order_id.date_order.day) - relativedelta(days=1)
            res['name'] = res['name'].replace('month','year')[:-10] + subscription_end_date.strftime('%m/%d/%Y')
            res['subscription_end_date']=subscription_end_date.date()
            self.next_invoice_date = subscription_end_date.date() + relativedelta(days=1)
        elif self.recurrence_id.unit=='month' and self.next_invoice_date==self.order_id.next_invoice_date:
            subscription_end_date = datetime(year=self.next_invoice_date.year, month=self.next_invoice_date.month+1,day=1) - relativedelta(days=1)
            res['subscription_end_date']=subscription_end_date.date()
            self.next_invoice_date = subscription_end_date.date() + relativedelta(days=1)
#        raise UserError(_('vals %s')%(res))
            
        return res

    @api.depends('state', 'product_uom_qty', 'qty_delivered', 'qty_to_invoice', 'qty_invoiced')
    def _compute_invoice_status(self):
        """
        Compute the invoice status of a SO line. Possible statuses:
        - no: if the SO is not in status 'sale' or 'done', we consider that there is nothing to
          invoice. This is also the default value if the conditions of no other status is met.
        - to invoice: we refer to the quantity to invoice of the line. Refer to method
          `_compute_qty_to_invoice()` for more information on how this quantity is calculated.
        - upselling: this is possible only for a product invoiced on ordered quantities for which
          we delivered more than expected. The could arise if, for example, a project took more
          time than expected but we decided not to invoice the extra cost to the client. This
          occurs only in state 'sale', so that when a SO is set to done, the upselling opportunity
          is removed from the list.
        - invoiced: the quantity invoiced is larger or equal to the quantity ordered.
        """
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for line in self:
            if line.state not in ('sale', 'done'):
                line.invoice_status = 'no'
            elif line.is_downpayment and line.untaxed_amount_to_invoice == 0:
                line.invoice_status = 'invoiced'
            elif not float_is_zero(line.qty_to_invoice, precision_digits=precision):
                line.invoice_status = 'to invoice'
            elif line.state == 'sale' and line.product_id.invoice_policy == 'order' and\
                    line.product_uom_qty >= 0.0 and\
                    float_compare(line.qty_delivered, line.product_uom_qty, precision_digits=precision) == 1:
                line.invoice_status = 'upselling'
            elif float_compare(line.qty_invoiced, line.product_uom_qty, precision_digits=precision) >= 0:
                line.invoice_status = 'invoiced'
            elif line.price_unit == 0:
                line.invoice_status = 'no'
            else:
                line.invoice_status = 'no'

