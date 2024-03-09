# Copyright 2023 Achmad T. Zaini - achmadtz@gmail.com
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from dateutil import relativedelta
from collections import defaultdict
from odoo import api, Command, fields, models, _
from odoo.exceptions import ValidationError, UserError


class HrExpense(models.Model):
    _inherit = "hr.expense"


    lead_id = fields.Many2one(comodel_name='crm.lead', string='CRM Lead', copy=False, store=True)
    