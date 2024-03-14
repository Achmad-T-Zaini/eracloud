# Copyright 2023 Achmad T. Zaini - achmadtz@gmail.com
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from dateutil import relativedelta
from collections import defaultdict
from odoo import api, Command, fields, models, _
from odoo.exceptions import ValidationError, UserError


class HrExpense(models.Model):
    _inherit = "hr.expense"


    lead_id = fields.Many2one(comodel_name='crm.lead', string='CRM Lead', copy=False, store=True)
    

    @api.model_create_multi
    def create(self, vals_list):
        expenses = super().create(vals_list)
        if vals_list.get('employee_id',False) or not self.employee_id:
            employee = self.env['hr.employee'].search([('user_id','=',self.env.user.id)])
#            self.employee_id = employee.id or False
            vals_list.update({'employee_id': employee.id,})
        return expenses
