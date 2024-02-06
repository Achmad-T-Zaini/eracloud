# -*- coding: utf-8 -*-

from collections import defaultdict

from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError, ValidationError
from odoo import api, models, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        posted_moves = super()._post(soft=soft)
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
                if end_dates and max(end_dates) > subscription.next_invoice_date:
                    subscription.next_invoice_date = max(end_dates) + relativedelta(days=1)

            sale_line = aml.sale_line_ids.filtered(lambda l: l.recurrence_id and l.recurrence_id.id==subscription.recurrence_id.id)
            if sale_line:
                subscription.next_invoice_date = sale_line.next_invoice_date
        return posted_moves
