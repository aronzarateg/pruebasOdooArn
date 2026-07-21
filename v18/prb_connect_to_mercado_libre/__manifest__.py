{
    "name": "PRB Mercado Libre Connector",
    "version": '18.0.0.0.0',
    "category": "Custom",
    "author": "INTI TEC PERU",
    "sequence": 1,
    "website": "https://www.intitecperu.com/",
    "contributors": [
        "Aron zarate <aron.zarate@intitecperu.com>",
    ],
    "summary": "",
    "description": "personalized",
    "depends": ["base", "sale", "stock", "product"],
    "data": [
        "security/ir.model.access.csv",
        "data/cron.xml",

        "views/menu.xml",
        "views/meli_account_views.xml",
        "views/meli_order_views.xml",
        "views/meli_product_views.xml",
        "views/meli_category.xml",
        "views/meli_attribute.xml",
        "views/meli_brand.xml",
        "views/meli_publication.xml",

        "views/product_template.xml",
    ],
    "assets": {

    },
    "license": "LGPL-3",
    "installable": True,
    "application": True,
}
# -*- coding: utf-8 -*-
