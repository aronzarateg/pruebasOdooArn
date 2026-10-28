from odoo import models, _
from odoo.exceptions import ValidationError

from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        result = super().button_validate()

        for picking in self:

            if (
                    picking.state != 'done'
                    or picking.picking_type_id.code != 'incoming'
                    or not picking.purchase_id
            ):
                continue

            for line in picking.move_line_ids:
                lot = line.lot_id
                print("lot", lot)
                if not lot:
                    continue
                if (line.product_id.product_tmpl_id.gas_product_type != 'cylinder'):
                    continue
                vals = {}
                if line.lot_supplier:
                    if lot.lot_supplier and lot.lot_supplier != line.lot_supplier:
                        raise ValidationError(_(
                            'El lote del proveedor ya tiene un valor '
                            'diferente para la serie %s.'
                        ) % lot.name)

                    vals['lot_supplier'] = line.lot_supplier

                if line.code_supplier:
                    if lot.code_supplier and lot.code_supplier != line.code_supplier:
                        raise ValidationError(_(
                            'El código del proveedor ya tiene un valor '
                            'diferente para la serie %s.'
                        ) % lot.name)

                    vals['code_supplier'] = line.code_supplier
                print("vals", vals)
                #raise UserError('dddd')
                if vals:
                    lot.write(vals)

        return result
