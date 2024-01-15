# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import UserError


class ProductCategory(models.Model):
    _inherit = 'product.category'

    show_sales = fields.Boolean(string='Show on Sales',default=False, store=True, copy=False)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _set_price_from_bom(self, boms_to_recompute=False):
        res = super()._set_price_from_bom(boms_to_recompute)
        self.ensure_one()
        bom = self.env['mrp.bom']._bom_find(self)[self]
        if bom:
            self.standard_price = self._compute_bom_price(bom, boms_to_recompute=boms_to_recompute)
            self.lst_price = self.standard_price
#            raise UserError(_('cek %s = %s')%(self.standard_price,bom))
        return res

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _onchange_recurring_invoice(self):
        """
        Raise a warning if the user has checked 'Subscription Product'
        while the product has already been set as a 'Storable Product'.
        In this case, the 'Subscription Product' field is automatically
        unchecked.
        """
        if self.type == 'product' and self.recurring_invoice and not self.categ_id.show_sales:
            self.recurring_invoice = False
            return {'warning': {
                'title': _("Warning"),
                'message': _("A 'Storable Product' cannot be a 'Subscription Product' !")
            }}
        confirmed_lines = self.env['sale.order.line'].search([('product_template_id', 'in', self.ids), ('order_id.state', 'in', ('sale', 'done'))])
        if not self.recurring_invoice and confirmed_lines:
            self.recurring_invoice = True
            return {'warning': {
                'title': _("Warning"),
                'message': _("You can not change the recurring property of this product because it has been sold already as a subscription.")
            }}

