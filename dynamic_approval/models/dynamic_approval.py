# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

BASE_ARCH = """<?xml version="1.0"?>
<data><!--button-placeholder--><xpath expr="//sheet" position="before">
          <div class="card alert alert-info">
            <div class="card-header bg-info text-white text-bf">
              Approval Operations
            </div>
            <div class="card-body p-2">
              <header>
                <button name="dynamic_next_approval" type="object" string="Submit" class="oe_highlight" attrs="{'invisible': ['|', ('x_approval_done', '=', True), ('x_dynamic_approval_state', '!=', 'draft')]}"/>
                <button name="dynamic_action_resubmit" type="object" string="Re-submit" class="oe_highlight" attrs="{'invisible': ['|', ('x_approval_done', '=', True), ('x_dynamic_approval_state', '!=', 'rejected')]}"/>
                <button name="dynamic_action_approve" type="object" string="Approve" class="oe_highlight" attrs="{'invisible': ['|', ('x_approval_done', '=', True), ('x_dynamic_approval_state', '!=', 'to_approve')]}"/>
                <button name="dynamic_action_reject" type="object" string="Reject" attrs="{'invisible': ['|', ('x_approval_done', '=', True), ('x_dynamic_approval_state', '!=', 'to_approve')]}"/>
                <field name="x_dynamic_approval_state" widget="statusbar" statusbar_visible="draft,to_approve,approved"/>
              </header>
            </div>
          </div>
        </xpath>
        <xpath expr="//sheet" position="inside">
          <sheet>
            <group string="Approval Information">
              <group>
                <field name="x_approval_state"/>
                <field name="x_approved_user_id"/>
                <field name="x_current_approval_level" invisible="1"/>
              </group>
              <group>
                <field name="x_approval_note"/>
                <field name="x_approval_group_id" attrs="{'invisible': [('x_approval_done', '=', True)]}"/>
                <field name="x_approval_done" invisible="1"/>
              </group>
            </group>
            <notebook>
              <page string="Approval History">
                <field name="x_approval_history_ids" nolabel="1">
                  <tree decoration-info="mode in ['submit', 'resubmit']" decoration-danger="mode=='reject'" decoration-success="mode=='approve'">
                    <field name="create_date" string="Date"/>
                    <field name="mode"/>
                    <field name="from_state"/>
                    <field name="to_state"/>
                    <field name="user_id"/>
                    <field name="note"/>
                  </tree>
                </field>
              </page>
            </notebook>
          </sheet>
        </xpath>
      </data>"""


class DynamicApproval(models.Model):
    _name = 'dynamic.approval'
    _description = 'Dynamic Approval'
    _order = 'name, id'

    name = fields.Char(string="Reference", required=True)
    model_id = fields.Many2one(comodel_name="ir.model", string="Model", required=False, copy=False)
    model_name = fields.Char(string="Model Technical Name", related='model_id.model', store=True)
    apply_specific_form = fields.Boolean(string="Apply to Specific Form")
    form_ids = fields.Many2many(comodel_name="ir.ui.view", string="Apply to Forms", required=False)
    amount_field_id = fields.Many2one(comodel_name="ir.model.fields", string="Amount Field", required=False)
    currency_field_id = fields.Many2one(comodel_name="ir.model.fields", string="Currency Field", required=False)
    button_to_hide = fields.Char(string="Buttons to Hide", required=False,
                                 help="Buttons name that will be hide during approval process "
                                      "(input multiple button name with comma separated)")
    button_to_execute = fields.Char(string="Button to Execute", required=False,
                                    help="Button name than will be execute automatically when the approval is done")
    created_form_ids = fields.One2many(comodel_name="ir.ui.view", inverse_name="dynamic_approval_id",
                                       string="Generated Form Views")
    created_form_count = fields.Integer(string="Generated Form Count", compute='compute_form_count')
    line_ids = fields.One2many(comodel_name="dynamic.approval.line", inverse_name="approval_id", string="Details",
                               required=True)
    arch_base = fields.Text(string='Base View Architecture',
                            help="This field is the same as `arch` field without translations",
                            default=BASE_ARCH)
    company_id = fields.Many2one(comodel_name="res.company", string="Company", required=True, ondelete="restrict",
                                default=lambda self: self.env.company.id)
    currency_id = fields.Many2one(comodel_name="res.currency", string="Currency", required=True, ondelete="restrict",
                                  default=lambda self: self.env.company.currency_id.id)

    _sql_constraints = [
        ('model_company_uniq', 'unique (model_id,company_id)',
         'The model of the dynamic approval must be unique per company !')
    ]

    def compute_form_count(self):
        for rec in self:
            self.created_form_count = len(self.created_form_ids)

    def generate_fields(self):
        # TODO next version: handle case if there is module update and will add generated field
        if not hasattr(self.env[self.model_name], 'x_approval_state'):
            field_obj = self.env['ir.model.fields']
            field_obj.create([
                {
                    'name': 'x_approval_state',
                    'field_description': 'Approval Status',
                    'model_id': self.model_id.id,
                    'ttype': 'char',
                    'required': False,
                    'readonly': True,
                    'copied': False,
                    'tracking': 1,
                }, {
                    'name': 'x_approved_user_id',
                    'field_description': 'Approval by',
                    'model_id': self.model_id.id,
                    'ttype': 'many2one',
                    'required': False,
                    'readonly': True,
                    'copied': False,
                    'tracking': 1,
                    'relation': 'res.users',
                    'on_delete': 'restrict'
                }, {
                    'name': 'x_approval_group_id',
                    'field_description': 'Group to Approve',
                    'model_id': self.model_id.id,
                    'ttype': 'many2one',
                    'required': False,
                    'readonly': True,
                    'copied': False,
                    'tracking': 1,
                    'relation': 'res.groups',
                }, {
                    'name': 'x_current_approval_level',
                    'field_description': 'Current Approval Level',
                    'model_id': self.model_id.id,
                    'ttype': 'integer',
                    'required': False,
                    'readonly': True,
                    'copied': False,
                }, {
                    'name': 'x_approval_history_ids',
                    'field_description': 'Approval History',
                    'model_id': self.model_id.id,
                    'ttype': 'many2many',
                    'required': False,
                    'readonly': True,
                    'copied': False,
                    'relation': 'base.approval.history',
                }, {
                    'name': 'x_approval_done',
                    'field_description': 'Is Approval Done?',
                    'model_id': self.model_id.id,
                    'ttype': 'boolean',
                    'required': False,
                    'readonly': True,
                    'copied': False,
                }, {
                    'name': 'x_approval_note',
                    'field_description': 'Approval Note',
                    'model_id': self.model_id.id,
                    'ttype': 'text',
                    'required': False,
                    'readonly': True,
                    'copied': False,
                }
            ])
            state_field = field_obj.create({
                    'name': 'x_dynamic_approval_state',
                    'field_description': 'Dynamic Approval Status',
                    'model_id': self.model_id.id,
                    'ttype': 'selection',
                    'required': False,
                    'readonly': True,
                    'copied': False,
                    'selection_ids': [
                        (0, 0, {'value': 'draft', 'name': 'Draft'}),
                        (0, 0, {'value': 'to_approve', 'name': 'To Approve'}),
                        (0, 0, {'value': 'approved', 'name': 'Approved'}),
                        (0, 0, {'value': 'rejected', 'name': 'Rejected'}),
                    ]
            })
            self.env['ir.default'].create({
                'field_id': state_field.id,
                'json_value': '"draft"'
            })

    def generate_forms(self):
        view_obj = self.env['ir.ui.view'].sudo()
        if self.apply_specific_form:
            parents = self.form_ids
        else:
            parents = view_obj.search([('type', '=', 'form'), ('inherit_id', '=', False), ('model', '=', self.model_name)])
            parents += view_obj.search([('type', '=', 'form'), ('inherit_id', '!=', False), ('model', '=', self.model_name),
                                        ('mode', '=', 'primary')])
        for parent in parents:
            try:
                view_obj.create({
                    'name': 'Dynamic Approval Generated Form for {} {}'.format(self.model_id.display_name, parent.name),
                    'inherit_id': parent.id,
                    'model': self.model_name,
                    'arch': self.arch_base,
                    'dynamic_approval_id': self.id
                })
            except ValueError as e:
                raise ValidationError(e.args[0])

    @api.onchange('button_to_hide')
    @api.depends('button_to_hide')
    def onchange_button_to_hide(self):
        if self.button_to_hide:
            self.button_to_hide = self.button_to_hide.replace(' ', '')
            button_arch = ''
            for button in self.button_to_hide.split(','):
                if not hasattr(self.env[self.model_name], button):
                    # TODO: check if button exist in form
                    raise ValidationError("Method {} is not found in object {}".format(button, self.model_id.display_name))
                button_arch += """<xpath expr="//button[@name='{}']" position="attributes">
                <attribute name="invisible">[('x_approval_state', '=', ''),('x_approval_done', '=', False)]</attribute>
                </xpath>\n""".format(button)
            arch_base = BASE_ARCH.replace("<!--button-placeholder-->", button_arch)
            self.arch_base = arch_base
        else:
            self.arch_base = BASE_ARCH

    @api.onchange('button_to_execute')
    @api.depends('button_to_execute')
    def onchange_button_to_execute(self):
        if self.button_to_execute:
            self.button_to_execute = self.button_to_execute.replace(' ', '')

    def check_approval(self, current_level, mode):
        if current_level == 0:
            return self.line_ids[0]
        line = self.line_ids.filtered(lambda l: l.sequence == current_level)
        if not line:
            raise ValidationError("Approval level {} is not found in dynamic approval {}.".format(current_level,                                                                                self.name))
        lines = self.line_ids.mapped('id')
        index_change = -1 if mode == 'reject' else 1
        try:
            line_index = lines.index(line.id)+index_change
            if line_index < 0:
                return False
            next_id = lines[line_index]
            dynamic_next_approval = self.line_ids.browse(next_id)
            return dynamic_next_approval
        except IndexError:
            return True

    @api.model
    def create(self, vals):
        if not vals.get('line_ids'):
            raise ValidationError("Sorry you have to input approval details to save this document.")
        res = super(DynamicApproval, self).create(vals)
        level = 1
        for line in res.line_ids:
            line.write({
                'sequence': level
            })
            level += 1
        res.sudo().generate_fields()
        res.sudo().generate_forms()
        return res

    def write(self, vals):
        res = super(DynamicApproval, self).write(vals)
        for rec in self:
            level = 1
            for line in rec.line_ids:
                line.write({
                    'sequence': level
                })
                level += 1
        field_to_check = ['model_id', 'button_to_hide', 'arch_base']
        if list(set(field_to_check).intersection(vals.keys())):
            for rec in self:
                rec.created_form_ids.sudo().unlink()
                rec.sudo().generate_fields()
                rec.sudo().generate_forms()
        return res

    def action_view_form(self):
        self.ensure_one()
        action_vals = {
            'name': 'Generated Form Views',
            'domain': [('id', 'in', self.created_form_ids.ids)],
            'view_mode': 'form',
            'res_model': 'ir.ui.view',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'context': {'create': False}
        }
        if len(self.created_form_ids) == 1:
            action_vals.update({'res_id': self.created_form_ids.id, 'view_mode': 'form'})
        else:
            action_vals['view_mode'] = 'tree,form'
        return action_vals


class DynamicApprovalLine(models.Model):
    _name = 'dynamic.approval.line'
    _description = 'Dynamic Approval Details'
    _order = 'approval_id, sequence'

    approval_id = fields.Many2one(comodel_name="dynamic.approval", string="Approval", ondelete="cascade")
    sequence = fields.Integer(string="Level", required=False, default=1)
    name = fields.Char(string="Name", required=True)
    group_id = fields.Many2one(comodel_name="res.groups", string="User Groups", required=True)
    amount = fields.Monetary(string="Amount", default=0)
    currency_id = fields.Many2one(comodel_name="res.currency", string="Currency", required=True, ondelete="restrict",
                                  related='approval_id.currency_id')
