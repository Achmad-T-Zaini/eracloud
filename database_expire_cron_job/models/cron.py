# -*- coding: utf-8 -*-
from odoo import fields, models
import dateutil
from datetime import timedelta, datetime


class ir_config_extend(models.Model):
    _inherit = "ir.config_parameter"

    def extend_date(self):
        data = self.env['ir.config_parameter'].search([('key', '=', 'database.expiration_date')])
        if data:
            date = datetime.now() + timedelta(days=30)
            data.value = date.strftime('%Y-%m-%d 00:00:00')
            data.create_date = date
            print(data.value)
