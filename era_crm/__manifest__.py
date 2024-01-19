# -*- coding: utf-8 -*-
{
    "name": "Custom CRM",
    "author": "Achmad T. Zaini",
    "category": "Sales",
    'license': 'AGPL-3',
    "version": "16.0.1",
    "depends": ["base", "sale", "crm", "sale_crm","sale_temporal",
                "mrp_account","mrp","account", "product",
                ],
    "application": False,
    "data": [
        "security/ir.model.access.csv",
        "views/crm_views.xml",
        "views/product_views.xml",
        "views/sale_views.xml",
        "views/stock_views.xml",
        "views/crm_template_views.xml",
        "report/crm_quotation.xml",
        "report/crm_quotation_templates.xml",
    ],
    "auto_install": False,
    "installable": True,
}
