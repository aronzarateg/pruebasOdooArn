{
    'name': 'Gestion de Gases y Cilindros - Ventas',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'Cotizaciones de gas por cilindro fisico',
    'license': 'LGPL-3',
    'depends': ['sale_stock', 'gas_cylinder_base', 'gas_cylinder_stock','stock'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/gas_sale_wizard_views.xml',
        'views/sale_order_views.xml',
    ],
    'application': False,
    'installable': True,
}
