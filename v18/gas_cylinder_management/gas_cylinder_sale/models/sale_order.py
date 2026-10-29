
from odoo import models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_open_gas_sale_wizard(self):
        self.ensure_one()

        if self.state not in ('draft', 'sent'):
            raise UserError(_(
                'Solo puede configurar gases en una cotizacion.'
            ))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Seleccionar gases para venta'),
            'res_model': 'gas.sale.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
            },
        }

    def _check_gas_sale_before_confirm(self):
        for order in self:
            gas_lines = order.order_line.filtered(
                lambda line:
                    not line.display_type
                    and line.gas_sale_cylinder_id
                    and line.product_id.product_tmpl_id.gas_product_type
                    == 'gas'
            )

            for line in gas_lines:
                cylinder = line.gas_sale_cylinder_id

                if cylinder.company_id != order.company_id:
                    raise UserError(_(
                        'El cilindro pertenece a otra empresa.'
                    ))

                if not cylinder.active or cylinder.ownership_type != 'own':
                    raise UserError(_(
                        'El cilindro debe estar activo y ser propio.'
                    ))

                if line.product_id not in cylinder.allowed_gas_product_ids:
                    raise UserError(_(
                        'El gas %(gas)s no es compatible con '
                        'el cilindro %(cylinder)s.'
                    ) % {
                        'gas': line.product_id.display_name,
                        'cylinder': cylinder.display_name,
                    })

                if float_compare(
                    line.product_uom_qty,
                    0.0,
                    precision_digits=3,
                ) <= 0:
                    raise UserError(_(
                        'La cantidad de gas debe ser mayor que cero.'
                    ))

                balance = self.env[
                    'gas.cylinder.content'
                ].search([
                    ('cylinder_id', '=', cylinder.id),
                    ('gas_product_id', '=', line.product_id.id),
                ], limit=1)

                if not balance:
                    raise UserError(_(
                        'No existe contenido para %(gas)s '
                        'en el cilindro %(cylinder)s.'
                    ) % {
                        'gas': line.product_id.display_name,
                        'cylinder': cylinder.display_name,
                    })

                requested_qty = line.product_uom._compute_quantity(
                    line.product_uom_qty,
                    line.product_id.uom_id,
                    round=False,
                )

                if float_compare(
                    requested_qty,
                    balance.available_quantity,
                    precision_digits=3,
                ) > 0:
                    raise UserError(_(
                        'Contenido insuficiente para %(gas)s '
                        'en el cilindro %(cylinder)s.\n'
                        'Disponible: %(available).3f m3\n'
                        'Solicitado: %(requested).3f m3'
                    ) % {
                        'gas': line.product_id.display_name,
                        'cylinder': cylinder.display_name,
                        'available': balance.available_quantity,
                        'requested': requested_qty,
                    })

    def action_confirm(self):
        self._check_gas_sale_before_confirm()

        result = super().action_confirm()

        for order in self:
            gas_lines = order.order_line.filtered(
                lambda line:
                    not line.display_type
                    and line.gas_sale_cylinder_id
                    and line.product_id.product_tmpl_id.gas_product_type
                    == 'gas'
            )

            for line in gas_lines:
                moves = self.env['stock.move'].search([
                    ('sale_line_id', '=', line.id),
                    ('state', '!=', 'cancel'),
                ])

                if not moves:
                    raise UserError(_(
                        'No se generaron movimientos de inventario '
                        'para el gas %(gas)s de la venta %(order)s. '
                        'Verifique el tipo de producto y las rutas.'
                    ) % {
                        'gas': line.product_id.display_name,
                        'order': order.name,
                    })

                for move in moves:
                    if move.gas_sale_cylinder_id != line.gas_sale_cylinder_id:
                        raise UserError(_(
                            'El movimiento %(move)s no conserva '
                            'el cilindro %(cylinder)s.'
                        ) % {
                            'move': move.display_name,
                            'cylinder': line.gas_sale_cylinder_id.display_name,
                        })

        return result
