{
    'name': 'Gestión de Gases y Cilindros - Compras',
    'version': '18.0.1.0.0',
    'category': 'Purchases',
    'summary': 'Compra de gas asociada a cilindros físicos',
    'license': 'LGPL-3',
    'depends': [
        'purchase_stock',
        'gas_cylinder_base',
        'gas_cylinder_stock',
        'purchase',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/gas_purchase_wizard_views.xml',
        'views/purchase_order_views.xml',
    ],
    'application': False,
    'installable': True,
}