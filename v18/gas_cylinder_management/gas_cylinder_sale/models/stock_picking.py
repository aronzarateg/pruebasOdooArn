from odoo import models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _check_gas_sale_cylinder_delivery(self):
        """
        Verifica la serie física de los cilindros vendidos.

        No modifica existencias, reservas ni saldos de gas.
        """
        for picking in self:
            if picking.picking_type_id.code != 'outgoing':
                continue

            cylinder_moves = picking.move_ids.filtered(
                lambda move:
                    move.state not in ('done', 'cancel')
                    and move.gas_sale_cylinder_id
                    and move.product_id.product_tmpl_id.gas_product_type
                    == 'cylinder'
                    and move.location_dest_id.usage == 'customer'
            )

            for move in cylinder_moves:
                cylinder = move.gas_sale_cylinder_id
                expected_lot = cylinder.lot_id

                if not expected_lot:
                    raise UserError(_(
                        'El cilindro %(serial)s no tiene '
                        'un número de serie de Odoo asociado.'
                    ) % {
                        'serial': cylinder.serial_number,
                    })

                if expected_lot.product_id != move.product_id:
                    raise UserError(_(
                        'La serie %(serial)s no corresponde '
                        'al producto del movimiento.'
                    ) % {
                        'serial': expected_lot.name,
                    })

                if cylinder.company_id != picking.company_id:
                    raise UserError(_(
                        'El cilindro %(serial)s pertenece '
                        'a otra empresa.'
                    ) % {
                        'serial': cylinder.serial_number,
                    })

                if not cylinder.active:
                    raise UserError(_(
                        'El cilindro %(serial)s está inactivo.'
                    ) % {
                        'serial': cylinder.serial_number,
                    })

                if cylinder.ownership_type != 'own':
                    raise UserError(_(
                        'El cilindro %(serial)s no está '
                        'registrado como propio.'
                    ) % {
                        'serial': cylinder.serial_number,
                    })

                if float_compare(
                    move.product_uom_qty,
                    1.0,
                    precision_rounding=move.product_uom.rounding,
                ) != 0:
                    raise UserError(_(
                        'El cilindro %(serial)s debe '
                        'entregarse en una cantidad de '
                        'una unidad por número de serie.'
                    ) % {
                        'serial': cylinder.serial_number,
                    })

                lines = move.move_line_ids.filtered(
                    lambda line:
                        not float_is_zero(
                            line.quantity,
                            precision_rounding=line.product_uom_id.rounding,
                        )
                )

                if not lines:
                    raise UserError(_(
                        'El cilindro %(serial)s no tiene '
                        'una operación detallada preparada '
                        'para su entrega.\n'
                        'Transferencia: %(picking)s.'
                    ) % {
                        'serial': cylinder.serial_number,
                        'picking': picking.name,
                    })

                for line in lines:
                    if line.lot_id != expected_lot:
                        raise UserError(_(
                            'La serie preparada no coincide '
                            'con la serie seleccionada '
                            'en la venta.\n'
                            'Transferencia: %(picking)s\n'
                            'Serie esperada: %(expected)s\n'
                            'Serie preparada: %(actual)s'
                        ) % {
                            'picking': picking.name,
                            'expected': expected_lot.name,
                            'actual': (
                                line.lot_id.name
                                if line.lot_id
                                else 'Sin serie'
                            ),
                        })

                prepared_quantity = sum(
                    line.product_uom_id._compute_quantity(
                        line.quantity,
                        move.product_uom,
                        round=False,
                    )
                    for line in lines
                )

                if float_compare(
                    prepared_quantity,
                    1.0,
                    precision_rounding=move.product_uom.rounding,
                ) != 0:
                    raise UserError(_(
                        'La cantidad preparada del cilindro '
                        '%(serial)s debe ser exactamente '
                        'una unidad.\n'
                        'Cantidad actual: %(quantity).3f.'
                    ) % {
                        'serial': cylinder.serial_number,
                        'quantity': prepared_quantity,
                    })

    def button_validate(self):
        """
        Control previo a la validación estándar.

        No descuenta gas ni desactiva cilindros.
        """
        self._check_gas_sale_cylinder_delivery()
        return super().button_validate()