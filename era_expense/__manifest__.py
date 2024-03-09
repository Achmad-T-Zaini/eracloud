# Copyright 2023 Achmad T. Zaini
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Era Expense",
    "summary": """
        Eranya Cloud Expense
        """,
    "version": "16.0.0.0.0",
    "license": "AGPL-3",
    "author": "Achmad T. Zaini",
    'category': 'Expenses',
    "website": "https://github.com/Achmad-T-Zaini/eracloud",
    "depends": ["base", "sale", "crm", "hr_expense"
                ],
    "qweb": [],
    "data": [
        "views/era_expense_views.xml",
    ],
    'installable': True,
    'application': False,
}
