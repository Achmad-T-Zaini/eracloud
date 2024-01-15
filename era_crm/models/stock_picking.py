# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'


    def action_assign(self):
        """ Check availability of picking moves.
        This has the effect of changing the state and reserve quants on available moves, and may
        also impact the state of the picking as it is computed based on move's states.
        @return: True
        """

        # check move_ids if there a manufacture product should be made and not ready
        mto = self.move_ids.filtered(lambda move: move.product_id.bom_count>0)
#        raise UserError(_('mto %s = %s')%(self.move_ids,mto))

        self.filtered(lambda picking: picking.state == 'draft').action_confirm()
        moves = self.move_ids.filtered(lambda move: move.state not in ('draft', 'cancel', 'done') and move.product_id.bom_count==0).sorted(
            key=lambda move: (-int(move.priority), not bool(move.date_deadline), move.date_deadline, move.date, move.id)
        )
        if not moves:
            raise UserError(_("Nothing to check the availability for, or there's a product should be Manufacture"))
        

        # If a package level is done when confirmed its location can be different than where it will be reserved.
        # So we remove the move lines created when confirmed to set quantity done to the new reserved ones.
        package_level_done = self.mapped('package_level_ids').filtered(lambda pl: pl.is_done and pl.state == 'confirmed')
        package_level_done.write({'is_done': False})
        moves._action_assign()
        package_level_done.write({'is_done': True})

        return True


class StockMove(models.Model):
    _inherit = 'stock.move'


    bom_count = fields.Integer(string='BOM Count', related="product_id.bom_count")