# -*- coding: utf-8 -*-
{
    "name": "Custom CRM",
    "author": "Achmad T. Zaini",
    "category": "Sales",
    'license': 'AGPL-3',
    "version": "16.0.1",
    "website": "https://github.com/Achmad-T-Zaini/eracloud",
    "depends": ["base", "sale", "crm", "sale_crm","sale_temporal", "sales_team",
                "mrp_account","mrp","account", "product", "era_presale", "hr_expense",
                ],
    "application": False,
    "data": [
        "security/ir.model.access.csv",
        "security/era_crm_security.xml",
        "report/crm_quotation.xml",
        "report/crm_quotation_templates.xml",
        "views/crm_views.xml",
        "views/product_views.xml",
        "views/sale_views.xml",
        "views/stock_views.xml",
        "views/crm_template_views.xml",
        "data/data.xml",
        "data/mail_template_data.xml",
    ],
    "auto_install": False,
    "installable": True,
}
