# -*- coding: utf-8 -*-

from odoo import api,fields, models, _
from odoo.exceptions import UserError,ValidationError

class TierDefinition(models.Model):
    _inherit = "tier.definition"

    @api.model
    def _get_tier_validation_model_names(self):
        res = super(TierDefinition, self)._get_tier_validation_model_names()
        res.append("crm.lead")
        return res
    
