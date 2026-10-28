
from odoo import api, fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    lot_supplier = fields.Char(
        string='Supplier Lot Number',
        copy=False,
        index=True,
    )

    code_supplier = fields.Char(
        string='Supplier Code',
        copy=False,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        print("\n========== STOCK.LOT CREATE ==========", flush=True)
        print("Valores recibidos:", vals_list, flush=True)

        lots = super().create(vals_list)

        for lot in lots:
            print("LOTE CREADO", flush=True)
            print("ID:", lot.id, flush=True)
            print("Serie:", lot.name, flush=True)
            print("Producto:", lot.product_id.display_name, flush=True)
            print("Lote proveedor:", lot.lot_supplier, flush=True)
            print("Código proveedor:", lot.code_supplier, flush=True)

        print("========== FIN CREATE ==========\n", flush=True)

        return lots

    def write(self, vals):
        print("\n========== STOCK.LOT WRITE ==========", flush=True)
        print("IDs:", self.ids, flush=True)
        print("Valores recibidos:", vals, flush=True)

        result = super().write(vals)

        for lot in self:
            print("LOTE ACTUALIZADO", flush=True)
            print("Serie:", lot.name, flush=True)
            print("Lote proveedor:", lot.lot_supplier, flush=True)
            print("Código proveedor:", lot.code_supplier, flush=True)

        print("========== FIN WRITE ==========\n", flush=True)

        return result
