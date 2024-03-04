# Copyright 2023 Achmad T. Zaini
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Era Helpdesk",
    "summary": """
        Eranya Cloud HelpDesk
        """,
    "version": "16.0.0.0.0",
    "license": "AGPL-3",
    "author": "Achmad T. Zaini",
    'category': 'Helpdesk',
    "website": "https://github.com/Achmad-T-Zaini/eracloud",
    "depends": ["base", "sale", "crm", "sale_crm","sale_temporal", "sales_team",
                "mrp_account","mrp","product", "helpdesk", "helpdesk_sale", "helpdesk_timesheet"
                ],
    "qweb": [],
    "data": [
        "views/era_helpdesk_views.xml",
    ],
    'installable': True,
    'application': False,
}
