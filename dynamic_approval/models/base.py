# -*- coding: utf-8 -*-
from lxml import etree
from lxml.builder import E

from odoo import api, fields, models, _
from odoo.addons.website.models.website import slugify
from odoo.exceptions import ValidationError


class BaseApproval(models.AbstractModel):
    _inherit = 'base'

    def dynamic_check_group_approval(self):
        group = self.x_approval_group_id
        if group:
            external_id = group.get_external_id()[group.id]
            if not external_id:
                external_id = group.export_data(['id'])['datas'][0][0]
            if not self.env.user.has_group(external_id):
                allowed_groups = '\n - %s' % group.display_name
                raise ValidationError("Sorry you are not allowed to approve this document, "
                                      "only user with following access can approve: %s" % allowed_groups)

    def dynamic_next_approval(self, mode='approve', note=''):
        history_obj = self.env['base.approval.history']
        model_id = self.env['ir.model'].sudo().search([('model', '=', self._name)])
        approval = self.env['dynamic.approval'].sudo().search([('model_id', '=', model_id.id)], limit=1)
        if approval:
            amount = self.read()[0].get(approval.amount_field_id.name) if approval.amount_field_id else 999999999999
            currency = self.read()[0].get(approval.currency_field_id.name)[0] if approval.currency_field_id else self.env.company.currency_id.id
            result = approval.check_approval(current_level=self.x_current_approval_level, mode=mode)
            if isinstance(result, bool):
                if result: # approval done
                    vals = {}
                    if self.x_current_approval_level != 0:
                        history = history_obj.create({
                            'user_id': self.env.user.id,
                            'from_state': self.x_approval_state or 'New',
                            'to_state': 'Approved',
                            'note': note,
                            'mode': mode
                        })
                        vals['x_approval_history_ids'] = [(4, history.id)]
                    vals.update({
                        'x_approval_done': True,
                        'x_approval_state': 'Approved',
                        'x_approval_note': note,
                        'x_dynamic_approval_state': 'approved',
                        'x_approved_user_id': self.env.user.id if self.x_current_approval_level != 0 else False
                    })
                    self.write(vals)
                    # auto execute button method
                    if approval.button_to_execute:
                        getattr(self, approval.button_to_execute)()
                else: # reject in first approval
                    history = history_obj.create({
                        'user_id': self.env.user.id,
                        'from_state': self.x_approval_state or 'New',
                        'to_state': 'New',
                        'note': note,
                        'mode': mode
                    })
                    self.write({
                        'x_approval_state': 'Rejected',
                        'x_approval_note': note,
                        'x_dynamic_approval_state': 'rejected',
                        'x_approved_user_id': self.env.user.id,
                        'x_approval_group_id': False,
                        'x_current_approval_level': 0,
                        'x_approval_history_ids': [(4, history.id)]
                    })
            else:
                if mode == 'reject':
                    x_dynamic_approval_state = 'rejected'
                    x_approval_done = False
                else:
                    document_currency = self.env['res.currency'].sudo().browse(currency)
                    document_amount = document_currency._convert(amount, approval.currency_id, self.env.company,
                                                                 fields.Date.context_today)
                    x_approval_done = approval.currency_id.compare_amounts(document_amount, result.amount)
                    x_approval_done = x_approval_done == -1
                    x_dynamic_approval_state = 'to_approve' if not x_approval_done else 'approved'
                x_approval_state = 'Approved' if x_approval_done else result.name
                vals = {}
                if self.x_current_approval_level != 0 or not x_approval_done:
                    history = history_obj.create({
                        'user_id': self.env.user.id,
                        'from_state': self.x_approval_state or 'New',
                        'to_state': x_approval_state,
                        'note': note,
                        'mode': 'submit' if self.x_dynamic_approval_state == 'draft' else mode
                    })
                    vals['x_approval_history_ids'] = [(4, history.id)]
                vals.update({
                    'x_approval_state': x_approval_state,
                    'x_current_approval_level': result.sequence,
                    'x_approval_group_id': result.group_id.id if not x_approval_done else False,
                    'x_approval_done': x_approval_done,
                    'x_approved_user_id': self.env.user.id if self.x_current_approval_level != 0 else False,
                    'x_approval_note': note,
                    'x_dynamic_approval_state': x_dynamic_approval_state
                })
                self.write(vals)
                if x_approval_done and approval.button_to_execute:
                    getattr(self, approval.button_to_execute)()
        return True

    def dynamic_action_approve(self):
        self.dynamic_check_group_approval()
        view_id = self.env.ref('dynamic_approval.form_dynamic_approval_wizard').id
        return {
            'name': _('Approve Document'),
            'type': 'ir.actions.act_window',
            'res_model': 'dynamic.approval.wizard',
            'view_mode': 'form',
            'view_id': view_id,
            'target': 'new',
            'context': {
                'default_record_id': '%s,%d' % (self._name, self.id),
                'default_mode': 'approve'
            }
        }

    def dynamic_action_reject(self):
        self.dynamic_check_group_approval()
        view_id = self.env.ref('dynamic_approval.form_dynamic_approval_wizard').id
        return {
            'name': _('Reject Document'),
            'type': 'ir.actions.act_window',
            'res_model': 'dynamic.approval.wizard',
            'view_mode': 'form',
            'view_id': view_id,
            'target': 'new',
            'context': {
                'default_record_id': '%s,%d' % (self._name, self.id),
                'default_mode': 'reject'
            }
        }

    def dynamic_action_resubmit(self):
        self.dynamic_check_group_approval()
        view_id = self.env.ref('dynamic_approval.form_dynamic_approval_wizard').id
        return {
            'name': _('Re-submit Document'),
            'type': 'ir.actions.act_window',
            'res_model': 'dynamic.approval.wizard',
            'view_mode': 'form',
            'view_id': view_id,
            'target': 'new',
            'context': {
                'default_record_id': '%s,%d' % (self._name, self.id),
                'default_mode': 'resubmit'
            }
        }

    def dynamic_do_approve(self, mode='approve', note=''):
        self.dynamic_check_group_approval()
        self.dynamic_next_approval(mode, note)


class BaseApprovalHistory(models.Model):
    _name = 'base.approval.history'
    _description = 'Approval History'

    user_id = fields.Many2one(comodel_name="res.users", string="Approval by", ondelete="restrict", required=True,
                              readonly=True)
    from_state = fields.Char(string="From Status", required=True, readonly=True)
    to_state = fields.Char(string="To Status", required=True, readonly=True)
    note = fields.Text(string="Note", required=False, )
    mode = fields.Selection(string="Action", selection=[
        ('submit', 'Submit'),
        ('approve', 'Approve'),
        ('reject', 'Reject'),
        ('resubmit', 'Re-submit'),
    ], required=False, )
