
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero
from markupsafe import Markup

class StockMove(models.Model):
    _inherit = 'stock.move'

    gas_sale_cylinder_id = fields.Many2one(
        'gas.cylinder',
        string='Cilindro origen de venta',
        copy=False,
        ondelete='restrict',
        index=True,
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        SaleLine = self.env['sale.order.line']

        for vals in vals_list:
            sale_line_id = vals.get('sale_line_id')
            if not sale_line_id:
                continue

            sale_line = SaleLine.browse(sale_line_id).exists()
            if not sale_line or sale_line.display_type:
                continue

            cylinder = sale_line.gas_sale_cylinder_id

            if (
                    cylinder
                    and sale_line.product_id.product_tmpl_id.gas_product_type
                    in ('gas', 'cylinder')
            ):
                vals['gas_sale_cylinder_id'] = cylinder.id

        return super().create(vals_list)

    def _update_reserved_quantity_vals(
            self,
            need,
            location_id,
            lot_id=None,
            package_id=None,
            owner_id=None,
            strict=True,
    ):
        self.ensure_one()
        if self.id == 173:
            print(
                "\n========== GAS SALE RESERVATION DEBUG =========="
                f"\nMovimiento: {self.id}"
                f"\nCilindro: {self.gas_sale_cylinder_id.id}"
                f"\nSerie: {self.gas_sale_cylinder_id.serial_number}"
                f"\nLote: {self.gas_sale_cylinder_id.lot_id.id}"
                f"\nCantidad requerida: {need}"
                f"\nUbicación: {location_id.id}"
                f"\nStrict: {strict}"
                "\n================================================\n",
                flush=True,
            )
        cylinder = self.gas_sale_cylinder_id

        if (
                cylinder
                and self.product_id.product_tmpl_id.gas_product_type == 'cylinder'
                and self.picking_type_id.code == 'outgoing'
                and self.location_dest_id.usage == 'customer'
        ):
            expected_lot = cylinder.lot_id

            if not expected_lot:
                raise UserError(_(
                    'El cilindro %(serial)s no tiene un número '
                    'de serie asociado.'
                ) % {
                                    'serial': cylinder.serial_number,
                                })

            if expected_lot.product_id != self.product_id:
                raise UserError(_(
                    'El número de serie %(serial)s no corresponde '
                    'al producto de la transferencia.'
                ) % {
                                    'serial': expected_lot.name,
                                })

            if lot_id and lot_id != expected_lot:
                # No reservar otro lote.
                return [], 0.0

            lot_id = expected_lot

            # Permitir buscar el lote dentro de las ubicaciones
            # hijas cuando la asignación original no es estricta.
            # No cambiamos strict porque forma parte de la lógica
            # estándar de ubicación de Odoo.
        if self.id == 173:
            Quant = self.env['stock.quant']
            cylinder = self.gas_sale_cylinder_id

            available_normal = Quant._get_available_quantity(
                self.product_id,
                location_id,
                lot_id=cylinder.lot_id,
                strict=True,
            )

            available_without_expiration = (
                Quant.with_context(with_expiration=False)
                ._get_available_quantity(
                    self.product_id,
                    location_id,
                    lot_id=cylinder.lot_id,
                    strict=True,
                )
            )

            print(
                "\n========== PRUEBA CONTEXTO CADUCIDAD =========="
                f"\nDisponible normal: {available_normal}"
                f"\nDisponible sin caducidad: {available_without_expiration}"
                "\n===============================================\n",
                flush=True,
            )
        return super()._update_reserved_quantity_vals(
            need,
            location_id,
            lot_id=lot_id,
            package_id=package_id,
            owner_id=owner_id,
            strict=strict,
        )

    def _action_done(self, cancel_backorder=False):
        result = super()._action_done(
            cancel_backorder=cancel_backorder
        )

        # PRIMERO: descontar el contenido de los gases.
        completed_gas_moves = result.filtered(
            lambda move:
            move.state == 'done'
            and move.gas_sale_cylinder_id
            and move.sale_line_id
            and move.picking_id
            and move.picking_id.picking_type_id.code == 'outgoing'
            and move.location_dest_id.usage == 'customer'
            and move.product_id.product_tmpl_id.gas_product_type == 'gas'
        )

        for move in completed_gas_moves.sorted('id'):
            move._post_sale_gas_content()

        # SEGUNDO: desactivar los cilindros vendidos definitivamente.
        completed_cylinder_moves = result.filtered(
            lambda move:
            move.state == 'done'
            and move.gas_sale_cylinder_id
            and move.sale_line_id
            and move.picking_id
            and move.picking_id.picking_type_id.code == 'outgoing'
            and move.location_dest_id.usage == 'customer'
            and move.product_id.product_tmpl_id.gas_product_type == 'cylinder'
            and move.sale_line_id.gas_sale_mode == 'cylinder_with_gas'
        )

        for move in completed_cylinder_moves.sorted('id'):
            move._close_sold_cylinder()

        return result

    def _post_sale_gas_content(self):
        self.ensure_one()

        cylinder = self.gas_sale_cylinder_id
        gas = self.product_id
        sale_line = self.sale_line_id

        if not cylinder or not sale_line:
            return False

        if self.state != 'done':
            raise UserError(_(
                'El movimiento debe estar finalizado.'
            ))

        if (
            not self.picking_id
            or self.picking_id.picking_type_id.code != 'outgoing'
            or self.location_dest_id.usage != 'customer'
        ):
            raise UserError(_(
                'Solo se permite descontar contenido '
                'en entregas salientes a clientes.'
            ))

        if (
            sale_line.product_id != gas
            or sale_line.gas_sale_cylinder_id != cylinder
            or sale_line.order_id.company_id != cylinder.company_id
            or self.company_id != cylinder.company_id
        ):
            raise UserError(_(
                'El movimiento no corresponde al gas, '
                'cilindro o empresa de la venta.'
            ))

        if (
            cylinder.ownership_type != 'own'
            or not cylinder.active
        ):
            raise UserError(_(
                'El cilindro debe estar activo y ser propio.'
            ))

        if gas not in cylinder.allowed_gas_product_ids:
            raise UserError(_(
                'El gas no es compatible con el cilindro.'
            ))

        quantity = self.product_uom._compute_quantity(
            self.quantity,
            gas.uom_id,
            round=False,
        )
        quantity = round(quantity, 3)

        if float_is_zero(quantity, precision_digits=3):
            return False

        if float_compare(
            quantity, 0.0, precision_digits=3
        ) < 0:
            raise UserError(_(
                'La cantidad entregada no puede ser negativa.'
            ))

        Content = self.env[
            'gas.cylinder.content'
        ].sudo().with_company(cylinder.company_id)

        Ledger = self.env[
            'gas.cylinder.content.move'
        ].sudo().with_company(cylinder.company_id)

        # Serializar movimientos del mismo cilindro.
        self.env.cr.execute(
            """
            SELECT id
              FROM gas_cylinder
             WHERE id = %s
             FOR UPDATE
            """,
            (cylinder.id,),
        )

        # Idempotencia: una entrega no debe descontar dos veces.
        existing = Ledger.search([
            ('stock_move_id', '=', self.id),
            ('cylinder_id', '=', cylinder.id),
            ('gas_product_id', '=', gas.id),
        ], limit=1)

        if existing:
            return False

        balance = Content.search([
            ('cylinder_id', '=', cylinder.id),
            ('gas_product_id', '=', gas.id),
        ], limit=1)

        if not balance:
            raise UserError(_(
                'No existe contenido registrado para '
                'el gas seleccionado en este cilindro.'
            ))

        balance.invalidate_recordset([
            'quantity',
            'available_quantity',
        ])

        if (
            float_compare(
                balance.quantity,
                quantity,
                precision_digits=3,
            ) < 0
            or float_compare(
                balance.available_quantity,
                quantity,
                precision_digits=3,
            ) < 0
        ):
            raise UserError(_(
                'Contenido insuficiente en cilindro %(serial)s.\n'
                'Gas: %(gas)s\n'
                'Contenido: %(content).3f m³\n'
                'Disponible: %(available).3f m³\n'
                'Entrega: %(requested).3f m³'
            ) % {
                'serial': cylinder.serial_number,
                'gas': gas.display_name,
                'content': balance.quantity,
                'available': balance.available_quantity,
                'requested': quantity,
            })

        posting_context = {
            'gas_content_posting': True,
        }

        balance.with_context(**posting_context).write({
            'quantity': round(balance.quantity - quantity, 3),
            'available_quantity': round(
                balance.available_quantity - quantity, 3
            ),
        })

        Ledger.with_context(**posting_context).create({
            'cylinder_id': cylinder.id,
            'gas_product_id': gas.id,
            'stock_move_id': self.id,
            'quantity_delta': -quantity,
            'available_delta': -quantity,
            'note': _(
                'Venta %(order)s / Entrega %(picking)s / '
                'Cilindro %(serial)s'
            ) % {
                'order': sale_line.order_id.name,
                'picking': self.picking_id.name,
                'serial': cylinder.serial_number,
            },
        })

        return True

    def _close_sold_cylinder(self):
        self.ensure_one()

        cylinder = self.gas_sale_cylinder_id

        if not cylinder:
            return False

        if (
                self.state != 'done'
                or not self.sale_line_id
                or not self.picking_id
                or self.picking_id.picking_type_id.code != 'outgoing'
                or self.location_dest_id.usage != 'customer'
                or self.product_id.product_tmpl_id.gas_product_type != 'cylinder'
                or self.sale_line_id.gas_sale_mode != 'cylinder_with_gas'
        ):
            return False

        if (
                self.product_id != cylinder.product_id
                or self.sale_line_id.gas_sale_cylinder_id != cylinder
                or self.company_id != cylinder.company_id
        ):
            raise UserError(_(
                'El cilindro vendido no coincide con '
                'el cilindro registrado en la venta.'
            ))

        if not cylinder.active:
            return False

        # Desactivar el cilindro vendido.
        cylinder.write({
            'active': False,
        })

        # Registrar la venta en el chatter del cilindro.
        sale_order = self.sale_line_id.order_id
        picking = self.picking_id

        message = Markup(
            '<b>Cilindro vendido - Venta definitiva</b><br/>'
            'El cilindro <b>%s</b> fue vendido '
            'y entregado al cliente.<br/><br/>'
            '<b>Pedido de venta:</b> %s<br/>'
            '<b>Transferencia:</b> %s<br/>'
            '<b>Movimiento de inventario:</b> %s<br/>'
            '<b>Cliente:</b> %s<br/>'
            '<b>Estado:</b> Cilindro desactivado '
            'automáticamente después de su venta.'
        ) % (
                      cylinder.serial_number,
                      sale_order.name,
                      picking.name,
                      self.id,
                      sale_order.partner_id.display_name,
                  )

        cylinder.message_post(
            body=message,
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

        return True
