from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    lot_supplier = fields.Char(
        string='Lote del proveedor',
        copy=False,
    )

    code_supplier = fields.Char(
        string='Código del proveedor',
        copy=False,
    )

    gas_tracking_serial = fields.Boolean(
        string='Seguimiento por serie única',
        compute='_compute_gas_tracking_serial',
    )

    @api.depends('product_id')
    def _compute_gas_tracking_serial(self):
        for line in self:
            line.gas_tracking_serial = (
                line.product_id.tracking == 'serial'
            )