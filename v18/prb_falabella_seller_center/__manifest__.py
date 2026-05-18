{
    "name": "PRB - Falabella Seller Center Integration",
    "version": "1.0.0",
    "category": "Sales",
    "summary": "Integración con Falabella Seller Center API",
    "author": "",
    "depends": ["base", "product", "sale"],
    "data": [
        "security/ir.model.access.csv",
        "views/falabella_account_views.xml",
        "views/falabella_brand_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": True,
}