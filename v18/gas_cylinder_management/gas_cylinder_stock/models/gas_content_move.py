from odoo import fields, models


class GasContentMove(models.Model):
    _inherit = 'gas.cylinder.content.move'

    operation_id = fields.Many2one(
        'gas.cylinder.operation',
        string='Operación de origen',
        ondelete='restrict',
        index=True,
        copy=False,
        readonly=True,
    )

    _sql_constraints = [
        (
            'unique_operation_cylinder_gas',
            'unique(operation_id, cylinder_id, gas_product_id)',
            'Ya existe una contabilización para este '
            'cilindro y gas en la operación.',
        ),
    ]