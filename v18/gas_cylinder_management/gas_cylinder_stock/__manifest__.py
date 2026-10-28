
{
    'name': 'Gestión de Gases y Cilindros - Movimientos',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'gas_cylinder_base',
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/gas_stock_rules.xml',
        'views/gas_operation_config_views.xml',
        'views/gas_operation_views.xml',
        'views/gas_stock_views.xml',
    ],
    'application': False,
    'installable': True,
}
