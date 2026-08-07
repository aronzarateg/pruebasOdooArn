{
    "name": "API Shopify",
    "version": "18.0.1.0.0",
    "summary": "Integración Shopify con Odoo",
    "depends": ["base", "web","sale"],
    "data": [
        "security/ir.model.access.csv",
        "data/cron.xml",
        "data/shopify_account_data.xml",
        "views/menu.xml",
        "views/shopify_account_views.xml",
        "views/shopify_order.xml",
    ],
    "installable": True,
    "application": True,
}
