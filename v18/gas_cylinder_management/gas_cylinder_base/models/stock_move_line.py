from odoo import fields, models


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