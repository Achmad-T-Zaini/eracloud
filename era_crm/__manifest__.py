# -*- coding: utf-8 -*-
{
    "name": "Custom CRM",
    "author": "Achmad T. Zaini",
    "category": "Sales",
    'license': 'AGPL-3',
    "version": "16.0.1",
    "depends": ["base", "sale", "crm", "sale_crm"],
    "application": False,
    "data": [
        "security/ir.model.access.csv",
        "views/crm_views.xml",
    ],
    "auto_install": False,
    "installable": True,
}
