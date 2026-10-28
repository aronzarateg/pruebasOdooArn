from odoo import fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    lot_supplier = fields.Char(string='Supplier Lot Number', copy=False, index=True)
    code_supplier = fields.Char(string='Supplier Code', copy=False, index=True)
