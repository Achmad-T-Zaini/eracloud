# Copyright 2023 Achmad T. Zaini
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Era PreSale",
    "summary": """
        Eranya Cloud Presale
        """,
    "version": "16.0.0.0.0",
    "license": "AGPL-3",
    "author": "Achmad T. Zaini",
    'category': 'Presale',
    "website": "https://github.com/Achmad-T-Zaini/eracloud",
    "depends": ["base", "sale", "crm", "sale_crm","sale_temporal", "sales_team",
                "mrp_account","mrp","product", 
                ],
    "qweb": [],
    "data": [
        "security/era_presale_security.xml",
        "security/ir.model.access.csv",
        "views/era_presale_menu.xml",
        "views/era_presale_views.xml",
    ],
    'installable': True,
    'application': True,
}
