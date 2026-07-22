{
    "name": "API Shopify",
    "version": "18.0.1.0.0",
    "summary": "Integración Shopify con Odoo",
    "depends": ["base", "web"],
    "data": [
        "security/ir.model.access.csv",
        "data/shopify_account_data.xml",
        "views/menu.xml",
        "views/shopify_account_views.xml",
    ],
    "installable": True,
    "application": True,
}
