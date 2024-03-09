# -*- coding: utf-8 -*-

from collections import defaultdict
from lxml import etree
import json 

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.osv import expression
from odoo.tools import float_is_zero, float_compare, float_round
from odoo.tools import get_timedelta
from datetime import date, datetime, time, timedelta
from dateutil.relativedelta import relativedelta

class ResPartner(models.Model):
    _inherit = "res.partner"

    partner_initial = fields.Char(string='Initials', size=3)
    _sql_constraints = [
        (
            'unique_partner_ny_initial', 'UNIQUE(partner_initial)', 'Only one Initial for Each Partner')
    ]

class CRMTeam(models.Model):
    _inherit = "crm.team"

    team_initial = fields.Char(string='Team Initials', size=3)


class Lead(models.Model):
    _name = "crm.lead"
    _inherit = ['crm.lead', 'tier.validation']
    _state_from = ['draft']
    _state_to = ['quotation']


    def _get_recurrence_default(self):
        return self.env['sale.temporal.recurrence'].search([('unit','=','month'),('duration','=',1)], limit=1).id

    def _get_domain_team(self):
        domain = [('share', '=', False), ('company_ids', 'in', self.team_id.member_company_ids.ids,)]
        if self.team_id:
            users = self.env['res.users'].search([('id','=',self.team_id.member_ids.ids)])
            domain = [('share', '=', False), ('company_ids', 'in', self.team_id.member_company_ids.ids,),('id', 'in', users.ids)]
        return domain      

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        result = super(Lead, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)

        doc = etree.XML(result['arch']) #Get the view architecture of record
#        raise UserError(_(self.env.context))
        for node in doc.xpath("//field"): #Get all the fields navigating through xpath
            modifiers = json.loads(node.get("modifiers")) #Get all the existing modifiers of each field
            domain = [('is_won','=',True)]
            readonly = modifiers.get('readonly')
            if readonly:
                if isinstance(readonly,list):
                    new_readonly = expression.OR([readonly, domain])
                    modifiers['readonly'] = new_readonly
                    node.set('modifiers', json.dumps(modifiers))
                else:
                    modifiers['readonly'] = domain
                    node.set('modifiers', json.dumps(modifiers))
        result['arch'] = etree.tostring(doc)

        return result

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
    is_won = fields.Boolean(string='is Won', store=True, copy=False)
    recurrence_id = fields.Many2one('sale.temporal.recurrence', string='Recurrence', ondelete='restrict', readonly=False, store=True, default=_get_recurrence_default)
    duration = fields.Integer('Periode', default=12)
    term_condition = fields.Text(string='Term & Conditions',)
    order_template_id = fields.Many2one('mrp.bom', string='Order Template', domain="[('product_tmpl_id.sale_ok','=',True)]")

    total_monthly = fields.Monetary(string="Total Monthly",
        compute='_compute_expected_revenue',
        store=True, precompute=True)
    total_yearly = fields.Monetary(string="Total Yearly",
        compute='_compute_expected_revenue',
        store=True, precompute=True)
    total_onetime = fields.Monetary(string="Total One Time",
        compute='_compute_expected_revenue',
        store=True, precompute=True)
    max_disc = fields.Float(string="Max Disc (%)",
        compute='_compute_expected_revenue',
        store=True, precompute=True)
    total_disc = fields.Float(string="Total Disc (%)",
        compute='_compute_expected_revenue',
        store=True, precompute=True)
    total_discount = fields.Monetary(string="Total Discount",
        compute='_compute_expected_revenue',
        store=True, precompute=True)

    ###### untuk kebutuhan APPROVAL
    state = fields.Selection(
        selection=[
            ('draft', "Opportunity"),
            ('quotation', "Quotation"),
        ],
        string="Status",
        readonly=True, copy=False, index=True,
        tracking=3,
        default='draft')
    
    review_status = fields.Selection(
        selection=[("pending", "Pending"),
                   ("rejected", "Rejected"),
                   ("approved", "Approved")], default="pending", compute="compute_review_status")
    approver = fields.Char(string='Approver', compute="compute_review_status")
    revision_bool = fields.Boolean(string="Revision Bool", compute="compute_revision_button")

    ##### PRESALE
    presale_id = fields.Many2one('era.presale', string="Presale")

    ##### TOTAL CONTRACT
    total_contract = fields.Monetary(string="Total Contract",
        compute='_compute_expected_revenue',
        store=True, precompute=True)
    total_contract_discount = fields.Monetary(string="Special Discount",
        compute='_compute_expected_revenue',
        store=True, precompute=True)
    tax_id = fields.Many2many(
        comodel_name='account.tax',
        string="Taxes",
        store=True, readonly=False,
        check_company=True)
    total_tax = fields.Monetary(string="Total Tax",
        compute='_compute_expected_revenue',
        store=True, precompute=True)
    grand_total_contract = fields.Monetary(string="Grand Total",
        compute='_compute_expected_revenue',
        store=True, precompute=True)
    tax_country_id = fields.Many2one('res.country', string="Country", related="company_id.account_fiscal_country_id")

    ####### Supporting Document #####
    po_data = fields.Binary(string="Purchase Order")
    po_filename = fields.Char(string="Purchase Order")


    def action_request_presale(self):
        raise UserError(_('wizard preesale'))

    @api.onchange('max_disc')
    def _onchange_max_disc(self):
        if self.max_disc>0:
            tiers = self.env["tier.definition"].search([("model", "=", self._name)])
            valid_tiers = any([self.evaluate_tier(tier) for tier in tiers])
            self.need_validation = (
                not self.review_ids
                and valid_tiers
                and getattr(self, self._state_field) in self._state_from
            )

    def _get_lead_sale_order_domain(self):
        return [('state', 'not in', ('sent', 'cancel'))]

    @api.depends('review_ids')
    def compute_review_status(self):
        for rec in self:
            rec.approver = False
            if rec.review_ids:
                if rec.validated:
                    rec.review_status = "approved"
                elif rec.rejected:
                    rec.review_status = "rejected"
                else:
                    rec.review_status = "pending"
                approver = rec.review_ids.filtered(lambda l: l.status == 'pending')
                rec.approver = approver[0].todo_by + ' as ' + approver[0].name + ' ' if approver else False
            else:
                rec.review_status = "pending"

    @api.depends('review_status', 'review_ids')
    def compute_revision_button(self):
        for rec in self:
            if rec.review_status == 'pending':
                rec.revision_bool = True
            elif rec.state == 'pending' and rec.review_ids.filtered(lambda r: r.status == 'rejected'):
                rec.revision_bool = True
            else:
                rec.revision_bool = False

    @api.onchange('stage_id')
    def _onchange_stage_id_era(self):
        if self.stage_id.is_won:
            if self.need_validation and self.review_status!='approved':
                raise UserError(_('This Opportunity need Validation'))
#            elif not self.need_validation or self.review_status=='approved':
            else:
                self.write({'stage_id': self.stage_id.id, 'probability': 100, 'is_won': True})
                self.action_set_won()
        elif self.is_won:
                raise UserError(_('This Opportunity already Won, and cannot change Stage to %s')%(self.stage_id.name))
#        raise UserError(_('App %s')%(self.stage_id.is_won))

    def action_set_won(self):
        """ Won semantic: probability = 100 (active untouched) """
        self.action_unarchive()
        # group the leads by team_id, in order to write once by values couple (each write leads to frequency increment)
        leads_by_won_stage = {}
        for lead in self:
            won_stages = self._stage_find(domain=[('is_won', '=', True)], limit=None)
            # ABD : We could have a mixed pipeline, with "won" stages being separated by "standard"
            # stages. In the future, we may want to prevent any "standard" stage to have a higher
            # sequence than any "won" stage. But while this is not the case, searching
            # for the "won" stage while alterning the sequence order (see below) will correctly
            # handle such a case :
            #       stage sequence : [x] [x (won)] [y] [y (won)] [z] [z (won)]
            #       when in stage [y] and marked as "won", should go to the stage [y (won)],
            #       not in [x (won)] nor [z (won)]
            stage_id = next((stage for stage in won_stages if stage.sequence > lead.stage_id.sequence), None)
            if not stage_id:
                stage_id = next((stage for stage in reversed(won_stages) if stage.sequence <= lead.stage_id.sequence), won_stages)
            if stage_id in leads_by_won_stage:
                leads_by_won_stage[stage_id] += lead
            else:
                leads_by_won_stage[stage_id] = lead
        for won_stage_id, leads in leads_by_won_stage.items():
            leads.write({'stage_id': won_stage_id.id, 'probability': 100, 'is_won': True})
#        raise UserError(_('App1 %s')%(self.is_won))
        return True

       
    @api.onchange('order_id')
    def _onchange_order_id(self):
        if not self.order_id:
            self.write({'summary_order_line': [(6,0,[])], 'tax_id': [(6,0,[self.env.company.account_sale_tax_id.id])] })  

    @api.onchange('team_id','user_id', 'company_id')
    def _onchange_team_id(self):
        if self.user_id:
            self.update({ 'company_id': self.env.company.id})             
        
        if self.company_id:
            self.update({ 'tax_id': [(6,0,[self.env.company.account_sale_tax_id.id])] })             

        domain = {'domain': {'user_id': [('share', '=', False), ('company_ids', 'in', self.team_id.member_company_ids.ids,)]}}

        users = self.env['res.users'].search([('id','=',self.team_id.member_ids.ids)])
#        raise UserError(_('cek %s\n%s')%(users,domain))
        if users:
            domain['domain']['user_id']= [('share', '=', False), ('company_ids', 'in', self.team_id.member_company_ids.ids,),('id', 'in', users.ids)]
        return domain      

    def action_print_quotation(self):
        if not self.is_won:
            self.order_id.quotation_rev+=1
        
        if self.order_line:
            return self.env.ref('era_crm.action_crm_quotation').report_action(self)
        else:
            raise UserError(_("There's No Order Line, please create ones"))

    def action_email_quotation(self):
        if not self.is_won:
            self.order_id.quotation_rev+=1
        """ Opens a wizard to compose an email, with relevant mail template loaded by default """
        self.ensure_one()
        self.order_id.order_line._validate_analytic_distribution()
        lang = self.env.context.get('lang')
#        mail_template = self.order_id._find_mail_template()
        mail_template = self.env.ref('era_crm.email_template_era_crm', raise_if_not_found=False)
        if mail_template and mail_template.lang:
            lang = mail_template._render_lang(self.order_id.ids)[self.order_id.id]
        ctx = {
            'default_model': 'sale.order',
            'default_res_id': self.order_id.id,
            'default_use_template': bool(mail_template),
            'default_template_id': mail_template.id if mail_template else None,
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True,
            'default_email_layout_xmlid': 'mail.mail_notification_layout_with_responsible_signature',
            'proforma': self.env.context.get('proforma', False),
            'force_email': True,
            'model_description': self.order_id.with_context(lang=lang).type_name,
        }
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }    

    def _prepare_sale_order_line(self,product_id=False,order_line=False):
        return {'name':  product_id.name if product_id else order_line.product_id.name, 
                'product_uom_qty': 1 if product_id else order_line.product_uom_qty, 
                'price_unit': 0 if product_id else order_line.crm_price_unit,
                }

    def _cek_subscription(self,recurrence_id):
            monthly_subscription = self.env['product.product'].browse(int(self.env['ir.config_parameter'].sudo().get_param('sales.monthly_subscription')))
            yearly_subscription = self.env['product.product'].browse(int(self.env['ir.config_parameter'].sudo().get_param('sales.yearly_subscription')))
            if recurrence_id==monthly_subscription.product_pricing_ids[0].recurrence_id.id:
                return monthly_subscription
            elif recurrence_id==yearly_subscription.product_pricing_ids[0].recurrence_id.id:
                return yearly_subscription
            return False

    def _get_sale_order_line_values(self):
        vals = []
        self.ensure_one
        for section in self.order_line.filtered(lambda x: x.display_type=='line_section' and x.order_type=='product'):
            product_id = self.env['product.product'].search([('default_code','ilike',self.order_id.quotation_no)])
            seq = 1
            subtotal = self.order_line.filtered(lambda x: x.display_type=='line_subtotal' and x.order_sequence==section.order_sequence)
            if not product_id:
                product_id = self.env['product.product'].create({
                                        'name': section.name.capitalize(),
                                        'sale_ok': False,
                                        'purchase_ok': False,
                                        'type': 'product',
                                        'invoice_policy': 'delivery',
                                        'categ_id': section.product_categ_id.id,
                                        'default_code': self.order_id.quotation_no + '-'+str(seq).zfill(2),
                                        'list_price': 0,
                                        'route_ids': [(6,0,[self.env['stock.route'].search([('name','=','Manufacture')],limit=1).id])]
                                        })
                bom_line_ids = []
                operation_ids = []
                for workcenter in self.env['mrp.routing.workcenter'].search([('bom_id','=',1)]):
                    operation_ids.append((0,0,{'name': workcenter.name, 'workcenter_id': workcenter.workcenter_id.id,}))
                for line in self.order_line.filtered(lambda x: not x.display_type and x.product_id and x.order_sequence==section.order_sequence):
                    bom_line_ids.append((0,0,{'product_id': line.product_id.id, 'product_qty': line.product_uom_qty, 'product_uom_id': line.product_uom.id,}))

                bom = self.env['mrp.bom'].create({
                                        'product_tmpl_id': product_id.product_tmpl_id.id,
                                        'code': self.order_id.quotation_no + '-'+str(seq).zfill(2),
                                        'recurrence_id': subtotal[0].recurrence_id.id,
                                        'bom_line_ids': bom_line_ids,
                                        'operation_ids': operation_ids,
                                        'consumption': 'strict',
                                        'type': 'normal',
                                        'lead_id': self.id,
                                        })
            vals.append((0,0,{'name': product_id.name, 
                              'product_id': product_id.id,
                              'product_uom_qty': subtotal[0].product_uom_qty,
                              'product_uom': product_id.uom_id.id,
                              'price_unit': 0}))
            seq+=1


        for sub_total in self.order_line.filtered(lambda x: x.display_type=='line_subtotal' and x.recurrence_id):
            if len(sub_total)>1:
                for subtt in sub_total:
                    subscription_product = self._cek_subscription(subtt.recurrence_id.id)
                    pricing_id = self.env['product.pricing'].search([('recurrence_id','=',subtt.recurrence_id.id),('product_template_id','=',subscription_product.product_tmpl_id.id)])
                    product_uom_qty = subtt.product_uom_qty
                    if self.recurrence_id.id == subtt.recurrence_id.id:
                       summary_order = self.summary_order_line.filtered(lambda l: l.order_sequence==subtt.order_sequence 
                                                                        and l.product_categ_id==subtt.product_categ_id 
                                                                        and l.recurrence_id==subtt.recurrence_id
                                                                        and l.discount_type=='periode')
                       periode_disc = summary_order.discount if summary_order else 0
                       product_uom_qty = self.duration - periode_disc
                    vals.append((0,0,{'name': subtt.name.replace('Subtotal ','Subscriptions'), 
                                      'product_id': subscription_product.id,
                                      'product_uom_qty': product_uom_qty,
                                      'invoice_status': 'to invoice',
#                                      'product_uom': product_id.uom_id.id,
                                      'product_categ_id': subtt.product_categ_id.id,
                                      'pricing_id': pricing_id.id or False,
                                      'recurrence_id': subtt.recurrence_id.id,
                                      'price_unit': subtt.crm_price_subtotal,}))
            else:
                subscription_product = self._cek_subscription(sub_total.recurrence_id.id)
                pricing_id = self.env['product.pricing'].search([('recurrence_id','=',sub_total.recurrence_id.id),('product_template_id','=',subscription_product.product_tmpl_id.id)])
                product_uom_qty = sub_total.product_uom_qty
                if self.recurrence_id.id == sub_total.recurrence_id.id:
                    summary_order = self.summary_order_line.filtered(lambda l: l.order_sequence==sub_total.order_sequence 
                                                                    and l.product_categ_id==sub_total.product_categ_id 
                                                                    and l.recurrence_id==sub_total.recurrence_id
                                                                    and l.discount_type=='periode')
                    periode_disc = summary_order.discount if summary_order else 0
                    product_uom_qty = self.duration - periode_disc
                vals.append((0,0,{'name': sub_total.name.replace('Subtotal ','Subscriptions'), 
                                  'product_id': subscription_product.id,
                                  'product_uom_qty': product_uom_qty,
                                  'invoice_status': 'to invoice',
#                                      'product_uom': product_id.uom_id.id,
                                  'product_categ_id': sub_total.product_categ_id.id,
                                  'pricing_id': pricing_id.id or False,
                                  'recurrence_id': sub_total.recurrence_id.id,
                                  'price_unit': sub_total.crm_price_subtotal,}))

        for sub_total in self.order_line.filtered(lambda x: x.display_type=='line_subtotal' and not x.recurrence_id):
            for line in self.order_line.filtered(lambda x: not x.display_type and x.order_sequence==sub_total.order_sequence and not x.recurrence_id):
                vals.append((0,0,{'name': line.product_id.name, 
                                  'product_id': line.product_id.id,
                                  'product_uom_qty': line.product_uom_qty,
                                  'product_categ_id': sub_total.product_categ_id.id,
                                  'product_uom': line.product_uom.id,
                                  'price_unit': (100-line.discount)/100 * (line.crm_price_unit * line.product_uom_qty)}))


        return vals
    
    def action_create_sale_order(self):
        if not self.po_filename:
            raise UserError(_('Please upload Customer Purchase Order'))
        values = self._prepare_sale_order_values()
        order = self.env['sale.order'].create(values)
        order.order_line._compute_tax_id()
#        order.action_confirm()
#        picking_id = order.picking_ids[0].do_unreserve()
        action = order._get_associated_so_action()
        action['name'] = _('CRM Order')
        action['views'] = [(self.env.ref('sale_subscription.sale_subscription_primary_form_view').id, 'form')]
        action['res_id'] = order.id
#        action['context']['create'] = True
        return action

    def _prepare_sale_order_values(self):
        """
        Create a new draft order with the same lines as the parent subscription. All recurring lines are linked to their parent lines
        :return: dict of new sale order values
        """
        self.ensure_one()
        self.company_id = self.env.company.id
        subscription = self.with_company(self.company_id)
        today = fields.Date.today()
        end_date = datetime.today() + relativedelta(months=self.duration)
        order_lines = self._get_sale_order_line_values()

        # New
        internal_note = subscription.description
        return {
            'opportunity_id': subscription.id,
            'pricelist_id': subscription.pricelist_id.id,
            'partner_id': subscription.partner_id.id,
            'order_line': order_lines,
#            'analytic_account_id': subscription.analytic_account_id.id,
            'origin': subscription.order_id.quotation_no + ' Rev.' + str(self.order_id.quotation_rev).zfill(3),
            'client_order_ref': subscription.po_filename,
            'note': internal_note,
            'user_id': subscription.user_id.id,
#            'payment_term_id': subscription.payment_term_id.id,
            'company_id': subscription.company_id.id,
            'payment_token_id': False,
            'start_date': today,
            'end_date': end_date,
            'next_invoice_date': today,
            'recurrence_id': subscription.recurrence_id.id,
            'recurring_monthly': subscription.duration,
            'internal_note': internal_note,
            'lead_id': self.id,
        }

    @api.onchange('summary_order_line', 'summary_order_line.discount', 'summary_order_line.discount_type')
    def _onchange_summary_order_line(self):
        if self.summary_order_line:
            for line in self.summary_order_line:
                subtotal = self.order_line.filtered(lambda l: l.order_sequence==line.order_sequence 
                                                    and l.product_categ_id==line.product_categ_id 
                                                    and l.recurrence_id==line.recurrence_id 
                                                    and l.display_type=='line_subtotal')
                if subtotal:
                    if line.discount_type!='periode':
                        subtotal.update({'discount': line.price_discount*100,})
                    elif line.discount_type=='periode':
                        subtotal.update({'discount': 0, })
#                        raise UserError(_('cek %s == %s')%(subtotal.discount,line.discount))

    @api.onchange('order_id', 'order_id.order_line', 'order_id.order_line.product_id','order_id.order_line.product_uom_qty','order_id.order_line.price_unit','order_id.order_line.discount',
            'order_line','order_line.product_uom_qty','order_line.price_unit','order_line.discount','order_line.product_id','expected_revenue', 'order_id.amount_total',
            'order_line.crm_price_unit','order_id.order_line.crm_price_unit')        
    def _onchange_order_line(self):
        if self.order_id:
            line_section = self.order_line.filtered(lambda x: x.display_type=='line_section')
            if line_section:
                to_remove = []
                for line in line_section:
                    to_remove.append(line.order_sequence)

            elif not line_section:
                self.summary_order_line = [(6,0,[])]
                self.order_line = [(6,0,[])]
        
            line_subtotal = self.order_line.filtered(lambda x: x.display_type=='line_subtotal')
            for section in line_subtotal:
                section.crm_price_unit = 0
                section.price_unit = 0
                line_product = self.order_line.filtered(lambda x: x.order_sequence==section.order_sequence and x.product_id and x.product_categ_id.id==section.product_categ_id.id )
                line_subtotal = sum(line.product_uom_qty*line.crm_price_unit for line in line_product) or 0
                if line_product:
                    pto_update = self.summary_order_line.filtered(lambda l: l.order_sequence ==section.order_sequence and l.product_categ_id.id==section.product_categ_id.id)
                    if pto_update:
                        pto_update.update({'product_uom_qty': section.product_uom_qty,'price_unit': line_subtotal,})
                    sol_update = self.order_line.filtered(lambda l: l.order_sequence ==section.order_sequence and l.product_categ_id.id==section.product_categ_id.id and l.display_type=='line_subtotal')
                    if sol_update:
                        sol_update.update({'price_unit': line_subtotal,'crm_price_unit': line_subtotal,})


    def _update_subtotal(self,subtotals):
#        raise UserError(_('subtotals %s')%(subtotals))
        for subtotal in subtotals:
            line_product = self.order_line.filtered(lambda x: x.order_sequence==subtotal.order_sequence and x.product_categ_id.id==subtotal.product_categ_id.id and x.recurrence_id==subtotal.recurrence_id and x.product_id)
            def_qty = subtotal.product_uom_qty
            if subtotal.product_uom_qty==0:
                def_qty = 1

            line_summarys = self.summary_order_line.filtered(lambda x: x.order_sequence==subtotal.order_sequence and x.product_categ_id.id==subtotal.product_categ_id.id and x.recurrence_id==subtotal.recurrence_id)
            if line_summarys:
                subtotal.update({       'product_uom_qty': def_qty,
                                        'discount': line_summarys.price_discount*100,
                                         'price_unit': sum(lp.crm_price_subtotal for lp in line_product),
                                         'crm_price_unit': sum(lp.crm_price_subtotal for lp in line_product),})
                line_summarys.update({'name': subtotal.name,
                                     'price_unit': subtotal.price_unit,
                                     'product_uom_qty': subtotal.product_uom_qty,
                                     })
            else:
                order_summary = self.env['crm.order.summary'].create(self.prepare_summary_order_line(subtotal))
#                raise UserError(_('st %s\n%s')%(line_product,subtotal.order_sequence))



    def _calculate_subtotal(self,order_line=False):
        if not order_line:
            line_sections = self.order_line.filtered(lambda x: x.display_type=='line_section')
            if line_sections:
                for line_section in line_sections:
                    new_subtotals = self.order_line.filtered(lambda x: x.display_type=='line_subtotal' and x.order_sequence==line_section.order_sequence)
                    if new_subtotals:
                        for new_subtotal in new_subtotals:
                            subtotal = self.order_line.filtered(lambda x: x.display_type=='line_subtotal' and x.order_sequence==new_subtotal.order_sequence and x.product_categ_id==new_subtotal.product_categ_id and x.recurrence_id==new_subtotal.recurrence_id)
                            for subttl in subtotal:
                                self._update_subtotal(subttl)
                    else:
                        line_product = self.order_line.filtered(lambda x: x.order_sequence==line_section.order_sequence and x.product_id).sorted(key= lambda l: (l.product_categ_id,l.recurrence_id))
                        name = line_section.name
                        if line_product:
                            self._create_new_subtotal_line(line_section.order_sequence,line_section,line_product)

        else:
            for line in order_line:
                line_sections = self.order_line.filtered(lambda x: x.display_type=='line_section' and x.order_sequence==line.order_sequence)
                for line_section in line_sections:
                    line_subtotal = self.order_line.filtered(lambda x: x.display_type=='line_subtotal' and x.order_sequence==line.order_sequence)
                    if not line_subtotal:
                        line_product = self.order_line.filtered(lambda x: x.order_sequence==line.order_sequence and x.product_id).sorted(key= lambda l: (l.product_categ_id,l.recurrence_id))
                        name = line_section[0].name
                        if line_product:
                            self._create_new_subtotal_line(line_section.order_sequence,line_section,line_product)
                    else:
                        for subtotal in line_subtotal:
                            subttl = self.order_line.filtered(lambda x: x.display_type=='line_subtotal' and x.order_sequence==subtotal.order_sequence and x.product_categ_id==subtotal.product_categ_id and x.recurrence_id==subtotal.recurrence_id)
                            self._update_subtotal(subttl)
    
    def _create_new_subtotal_line(self,order_sequence,line_section,line_product):
        recurrence_id = False
        crm_price_unit = 0
        product_categ_id = line_product[0].product_id.categ_id
        name = line_section.name + ' ' + line_product[0].product_id.categ_id.name.capitalize()
        if line_product[0].product_id.recurring_invoice:
            name += ' ' + line_product[0].product_id.recurrence_id.name
            recurrence_id = line_product[0].product_id.recurrence_id
                        
        for product in line_product:
            if product.product_id.categ_id != product_categ_id and product.product_id.recurrence_id != recurrence_id:
                subtotal = self.env['sale.order.line'].create(self.prepare_order_line(name,order_sequence,crm_price_unit,product_categ_id,recurrence_id,product.sequence-1,product.product_id.detailed_type))
                subtotal.product_uom_qty = 1
                order_summary = self.env['crm.order.summary'].create(self.prepare_summary_order_line(subtotal))
                crm_price_unit = product.crm_price_unit*product.product_uom_qty
                product_categ_id = product.product_id.categ_id
                name = line_section.name + ' ' + product_categ_id.name.capitalize()
                if product.product_id.recurrence_id:
                    name += ' ' + product.product_id.recurrence_id.name
                    recurrence_id = product.product_id.recurrence_id
            else:
                crm_price_unit += product.crm_price_unit*product.product_uom_qty

        subtotal = self.env['sale.order.line'].create(self.prepare_order_line(name,order_sequence,crm_price_unit,product_categ_id,recurrence_id,product.sequence,product.product_id.detailed_type))
        subtotal.product_uom_qty = 1
        order_summary = self.env['crm.order.summary'].create(self.prepare_summary_order_line(subtotal))

    def prepare_order_line(self,name,order_sequence,crm_price_unit,categ_id,recurrence_id,sequence,detailed_type):
        return { 'name':  name + ' Subtotal', 
                                            'product_uom_qty': 1, 
                                            'price_unit': crm_price_unit,
                                            'crm_price_unit': crm_price_unit,
                                            'sequence': sequence, 
                                            'order_type': detailed_type,
                                            'display_type': 'line_subtotal',
                                            'order_sequence': order_sequence,  
                                            'product_categ_id': categ_id.id if categ_id else False,
                                            'lead_id': self.id,
                                            'order_id': self.order_id.id,
                                            'recurrence_id': recurrence_id.id if recurrence_id else False,
                                            }

    def prepare_summary_order_line(self,subtotal):
        return {'name': subtotal.name, 
                                            'product_uom_qty': 1, 
                                            'price_unit': subtotal.crm_price_unit,
                                            'order_type': subtotal.order_type,
                                            'product_categ_id': subtotal.product_categ_id.id,
                                            'order_sequence': subtotal.order_sequence,  
                                            'lead_id': self.id,
                                            'recurrence_id': subtotal.recurrence_id.id if subtotal.recurrence_id else False,
                                            }

    def get_summary_subtotal(self):
        data = []
        sum_total = self.order_line.sorted(key=lambda mv: (mv.recurrence_id, mv.product_categ_id,))
        if sum_total:
            total = 0.0
            discount = total_disc = 0.0
            recurrence_id = categ = False
            for line in self.summary_order_line:
                if not recurrence_id:
                    recurrence_id = line.recurrence_id
                if not categ:
                    categ = line.product_categ_id

                if recurrence_id and (recurrence_id.id!=line.recurrence_id.id or categ.id!=line.product_categ_id.id):
                    if discount>0 and total>0:
                        total_disc = discount/total
                    data.append({'name': 'Total ' + recurrence_id.name + ' ' + categ.name,
                                 'discount': total_disc,
                                 'total': total,})
                    recurrence_id = line.recurrence_id
                    categ = line.product_categ_id
                    total = line.price_total
                    discount = line.price_discount * line.product_uom_qty * line.price_unit
                else:
                    total += line.price_total
                    discount = line.price_discount * line.product_uom_qty * line.price_unit

            if discount>0 and total>0:
                total_disc = discount/total
            if not recurrence_id:
                data.append({'name': 'Total One Time Charge' + ' ' + categ.name,
                             'discount': total_disc,
                             'total': total,})
            else:
                data.append({'name': 'Total ' + recurrence_id.name + ' ' + categ.name,
                             'discount': total_disc,
                             'total': total,})
#            raise UserError(_('data %s')%(data))
        return data
    
    def action_get_template(self):
        if self.order_template_id:
            order_line = []
            summary_order_line = []
            subtotal = 0
            order_type = 'product'
            product_categ_id = False
            sequence = 10
            order_sequence = 1
            if len(self.order_line)>0:
                sequence = self.order_line.sorted(key='sequence', reverse=True)[0].sequence+1
                order_sequence = len(self.order_line.filtered(lambda l: l.display_type=='line_section'))+1
            order_line.append((0,0,{ 'sequence': sequence, 'name': self.order_template_id.product_tmpl_id.name, 
                                    'display_type': 'line_section','order_sequence': order_sequence, 
                                    'order_type': 'product', 'product_categ_id': self.order_template_id.product_tmpl_id.categ_id.id}))
            sequence+=1
            for line in self.order_template_id.bom_line_ids.sorted(key= lambda l: (l.product_categ_id,l.recurrence_id)):
                product_categ_id = line.product_id.categ_id
                order_line.append((0,0,{ 'product_id': line.product_id.id, 
                                        'product_uom_qty': line.product_qty,
                                        'sequence': sequence, 
                                        'order_sequence': order_sequence,
                                        'recurrence_id': self.order_template_id.recurrence_id.id if self.order_template_id.recurrence_id else False,
                                        'product_categ_id': line.product_id.categ_id.id,}))
                subtotal += line.product_qty * max(line.product_id.list_price,line.product_id.lst_price)
                sequence+=1
            self.order_line = order_line
            self.summary_order_line = summary_order_line
            self.order_template_id = False


    def _convert_to_tax_base_line_dict(self):
        """ Convert the current record to a dictionary in order to use the generic taxes computation method
        defined on account.tax.

        :return: A python dictionary.
        """
        self.ensure_one()
        return self.env['account.tax']._convert_to_tax_base_line_dict(
            self,
            partner=self.order_id.partner_id,
            currency=self.order_id.currency_id,
            product=False,
            taxes=self.tax_id,
            price_unit=self.total_contract,
            quantity=1,
            discount=self.total_disc,
#            price_subtotal=self.total_contract,
        )
       
    @api.depends('order_id', 'order_id.amount_total', 'currency_id','order_line', 'order_line.price_unit', 'order_line.discount', 'order_line.product_uom_qty', 'tax_id')
    def _compute_expected_revenue(self):
        for order in self:
            total_monthly = total_discount = total_tax = periode_disc = 0
            order.total_disc =0
            max_disc = 0
            if order.order_id and order.order_line:
                max_disc = order.order_line.sorted(key='discount', reverse=True)[0].discount
            total_monthly = sum(line.crm_price_subtotal for line in order.order_line.filtered(lambda l: l.display_type=='line_subtotal' and l.recurrence_id.unit=='month'))
            total_yearly = sum(line.crm_price_subtotal  for line in order.order_line.filtered(lambda l: l.display_type=='line_subtotal' and l.recurrence_id.unit=='year'))
            total_onetime = sum(line.crm_price_subtotal for line in order.order_line.filtered(lambda l: l.display_type=='line_subtotal' and not l.recurrence_id))
            bruto_total_monthly = sum(line.crm_price_unit * line.product_uom_qty  for line in order.order_line.filtered(lambda l: l.product_id and l.recurrence_id.unit=='month'))
            bruto_total_yearly = sum(line.crm_price_unit * line.product_uom_qty   for line in order.order_line.filtered(lambda l: l.product_id and l.recurrence_id.unit=='year'))
            bruto_total_onetime = sum(line.crm_price_unit * line.product_uom_qty  for line in order.order_line.filtered(lambda l: l.product_id and not l.recurrence_id))

            periode_disc = sum(line.price_unit * line.product_uom_qty * line.discount for line in order.summary_order_line.filtered(lambda l: l.discount_type=='periode'))
            total_contract = (total_monthly * order.duration) + total_yearly + total_onetime - periode_disc
            total_contract_bruto = (bruto_total_monthly * order.duration) + bruto_total_yearly + bruto_total_onetime
            total_discount = total_contract_bruto - total_contract
#            raise UserError(_('ttl %s = %s = %s')%(total_contract,total_contract_bruto,total_discount))
            if total_contract>0:
                order.total_disc = total_discount/total_contract_bruto * 100
                order.total_contract_discount = total_discount

            order.total_contract = total_contract_bruto

            tax_results = self.env['account.tax']._compute_taxes([order._convert_to_tax_base_line_dict()])
            totals = list(tax_results['totals'].values())[0]
            amount_untaxed = totals['amount_untaxed']
            order.total_tax = totals['amount_tax']

            grand_total = sum(line.crm_price_unit * line.product_uom_qty   for line in order.order_line.filtered(lambda l: l.display_type=='line_subtotal'))

            order.update({'expected_revenue': grand_total,
                          'total_monthly': total_monthly,
                          'total_yearly': total_yearly,
                          'total_onetime': total_onetime,
#                          'total_contract': amount_untaxed,
                          'total_contract_discount': total_discount,
#                          'total_disc': total_disc,
                          'max_disc': max_disc,
                          'total_discount': total_discount,
                          'grand_total_contract': total_contract + order.total_tax})
#            order.order_id.update({'amount_total': expected_revenue,})
#            order._calculate_subtotal()


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
        order_sequence = ori_order_sequence = 1
        calc_st = True
        if vals.get('order_line',False):
            if self.order_line:
                order_sequence = self.order_line.filtered(lambda l: l.display_type=='line_section').sorted(key='order_sequence', reverse=True)[0].order_sequence +1
            for line in vals['order_line']:
                if line[2]!=False:
                    line[2].update({'order_id': self.order_id.id,})
                    if line[2].get('order_sequence',False)==False:
                        if line[2].get('display_type',False)=='line_section':
                            order_sequence +=1
                            line[2]['order_sequence']=order_sequence
                            line_section = line[2]
                        if line[2].get('product_id',False):
                            if isinstance(line[1],int):
                                line_order = self.env['sale.order.line'].browse(line[1])
                                line[2]['order_sequence']=line_order.order_sequence
                            else:
                                line[2]['order_sequence']=order_sequence
                            product_id = self.env['product.product'].browse(line[2]['product_id'])
                            if line[2].get('order_type',False):
                                line[2]['order_type'] = product_id.detailed_type
                            if line[2].get('product_categ_id',False):
                                line[2]['product_categ_id'] = product_id.categ_id.id
                            if line[2].get('recurrence_id',False)==False:
                                line[2]['recurrence_id'] = product_id.product_pricing_ids[0].recurrence_id.id if product_id.product_pricing_ids else False
                                if line[2].get('recurrence_id',False):
                                    line[2].update({'recurrence_id': line[2]['recurrence_id'],})
                        else:
                            if isinstance(line[1],int):
                                line_order = self.env['sale.order.line'].browse(line[1])
                                if line_order.display_type=='line_subtotal':
                                    calc_st = False

        res = super().write(vals)
        new_subtotals = self.order_line.filtered(lambda x: x.display_type=='line_subtotal')
#        raise UserError(_('ord seq %s \n %s\n%s')%(order_sequence,ori_order_sequence,new_subtotals))
        if new_subtotals:
            ord_seq = []
            for new_subtotal in new_subtotals:
                ord_seq.append(new_subtotal.order_sequence)
                summary_order = self.env['crm.order.summary'].search([('lead_id','=',self.id),('order_sequence', '=',int(new_subtotal.order_sequence)),('product_categ_id','=',new_subtotal.product_categ_id.id)])
#                raise UserError(_('cek %s\n%s = %s = %s')%(summary_order,line.name,line.order_sequence,line.product_categ_id))
                if summary_order:
                    summary_order.name = new_subtotal.name
                if new_subtotal.product_uom_qty == 0:
                    new_subtotal.product_uom_qty = 1
                subtotal = self.order_line.filtered(lambda x: x.display_type=='line_subtotal' and x.order_sequence==new_subtotal.order_sequence and x.product_categ_id==new_subtotal.product_categ_id and x.recurrence_id==new_subtotal.recurrence_id)
#                self._calculate_subtotal(subtotal)
#        else:
        if calc_st:
            self._calculate_subtotal()
#        raise UserError(_('vals %s'%(vals)))

        to_deletes = self.order_line.filtered(lambda x: x.display_type=='line_subtotal')
#        raise UserError(_('ord seq %s == %s\n%s')%(order_sequence,ori_order_sequence,new_subtotals))
        if to_deletes:
            ord_seq = []
            for to_delete in to_deletes:
                ord_seq.append(to_delete.order_sequence)
            ord_summ = self.env['crm.order.summary'].search([('order_sequence','not in',ord_seq),('lead_id','=',self.id)])
            ord_summ.unlink()
#            raise UserError(_('dd %s')%(ord_summ))
#        raise UserError(_('vals %s = %s')%(vals,self.is_won))
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
            if line.discount_type=='periode' and not line.product_categ_id.is_disc_period:
                raise UserError(_('This product can not Discount Period'))

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
            