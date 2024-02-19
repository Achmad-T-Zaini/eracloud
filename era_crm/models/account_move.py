# -*- coding: utf-8 -*-

from collections import defaultdict

from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError, ValidationError
from odoo import api, models, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        posted_moves = super()._post(soft=soft)
        end_dates = False
        for move in posted_moves:
            aml_by_subscription = defaultdict(lambda: self.env['account.move.line'])
            for aml in move.invoice_line_ids:
                aml_by_subscription[aml.subscription_id] |= aml
            for subscription, aml in aml_by_subscription.items():
                sale_order = aml.sale_line_ids.order_id
                if subscription != sale_order:
                    # we are invoicing an upsell
                    continue
                # Normally, only one period_end should exist
                end_dates = [ed for ed in aml.mapped('subscription_end_date') if ed]

            for line in move.line_ids.filtered(lambda l: l.subscription_start_date):
                line.sale_line_ids[0].next_invoice_date = line.subscription_end_date + relativedelta(days=1)
            
        if end_dates:
            subscription.next_invoice_date = min(end_dates) + relativedelta(days=1)

        return posted_moves
