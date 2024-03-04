# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    """ Manufacturing Orders """
    _inherit = 'mrp.production'

    workorder_status = fields.Char(string='WO Status')

    @api.onchange('state')
    def _onchange_state_era(self):
        if self.name and self.state:
            self.update({'workorder_status': self.name + ' ' + dict(self._fields['state'].selection).get(self.state)})

class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'


    def button_pending(self):
        self.end_previous()
        self.production_id.update({'workorder_status': self.name + ' ' + dict(self._fields['state'].selection).get(self.state)})
        return True

    def button_start(self):
        res = super().button_start()
        self.production_id.update({'workorder_status': self.name + ' ' + dict(self._fields['state'].selection).get(self.state)})
        return res

    def button_finish(self):
        res = super().button_finish()
        for line in self:
            line.production_id.update({'workorder_status': line.name + ' ' + dict(line._fields['state'].selection).get(line.state)})
        return res

class MrpBom(models.Model):
    """ Defines bills of material for a product or a product template """
    _inherit = 'mrp.bom'

    recurrence_id = fields.Many2one('sale.temporal.recurrence', string='Recurrence', ondelete='restrict', readonly=False, store=True)
    lead_id = fields.Many2one('crm.lead',string='CRM ID',readonly=True, copy=False)


class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'

    recurrence_id = fields.Many2one('sale.temporal.recurrence', string='Recurrence', related="product_tmpl_id.recurrence_id")
    product_categ_id = fields.Many2one('product.category',string='Product Category', related="product_tmpl_id.categ_id")
