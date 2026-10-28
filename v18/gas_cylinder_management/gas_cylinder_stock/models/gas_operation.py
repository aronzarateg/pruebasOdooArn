from odoo import fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare
import inspect

class GasOperation(models.Model):
    _name = 'gas.cylinder.operation'
    _description = 'Gas Cylinder Business Operation'
    _order = 'id desc'

    name = fields.Char(
        default='Nuevo',
        required=True,
        copy=False,
    )

    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
    )

    partner_id = fields.Many2one('res.partner')

    operation_type = fields.Selection([
        ('supplier_refill', 'Supplier refill'),
        ('customer_refill', 'Customer refill'),
        ('sale', 'Sale'),
        ('rental_out', 'Rental out'),
        ('rental_return', 'Rental return'),
        ('recovery', 'Recovery'),
        ('transfer', 'Transfer'),
        ('adjustment', 'Adjustment'),
    ], required=True)

    config_id = fields.Many2one(
        'gas.cylinder.operation.config',
    )

    line_ids = fields.One2many(
        'gas.cylinder.operation.line',
        'operation_id',
    )

    picking_ids = fields.Many2many(
        'stock.picking',
        string='Related Pickings',
        copy=False,
    )

    outgoing_picking_id = fields.Many2one(
        'stock.picking',
        string='Transferencia de envío',
        copy=False,
        readonly=True,
    )

    return_picking_id = fields.Many2one(
        'stock.picking',
        string='Transferencia de retorno',
        copy=False,
        readonly=True,
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('ready', 'Ready'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], default='draft', required=True)

    def _check_supplier_refill_outgoing(self):
        self.ensure_one()

        if self.operation_type != 'supplier_refill':
            raise UserError(_(
                'Esta función solo admite recargas de proveedor.'
            ))

        config = self.config_id

        if not config or not config.active:
            raise UserError(_(
                'Seleccione una configuración logística activa.'
            ))

        if (
                config.operation_type != 'supplier_refill'
                or config.company_id != self.company_id
        ):
            raise UserError(_(
                'La configuración no corresponde a esta '
                'operación o compañía.'
            ))

        if (
                config.warehouse_id.company_id != self.company_id
                or config.picking_type_id.code != 'internal'
        ):
            raise UserError(_(
                'La configuración debe utilizar un almacén '
                'de la compañía y un traslado interno.'
            ))

        source = config.location_src_id
        destination = config.location_dest_id

        if (
                not source
                or not destination
                or source == destination
                or source.usage != 'internal'
                or destination.usage != 'internal'
        ):
            raise UserError(_(
                'Revise las ubicaciones de salida.'
            ))

        for location in (source, destination):
            if (
                    location.company_id
                    and location.company_id != self.company_id
            ):
                raise UserError(_(
                    'Una ubicación pertenece a otra compañía.'
                ))

        if not self.line_ids:
            raise UserError(_('Agregue al menos un cilindro.'))

        seen = set()

        for line in self.line_ids:
            cylinder = line.cylinder_id
            product = cylinder.product_id
            lot = cylinder.lot_id

            if cylinder.id in seen:
                raise UserError(_(
                    'El cilindro %s está duplicado.'
                ) % cylinder.display_name)

            seen.add(cylinder.id)

            if (
                    cylinder.company_id != self.company_id
                    or cylinder.ownership_type != 'own'
            ):
                raise UserError(_(
                    'El cilindro %s debe ser propio '
                    'y pertenecer a esta compañía.'
                ) % cylinder.display_name)

            if not product or not lot:
                raise UserError(_(
                    'El cilindro %s no tiene producto o serie.'
                ) % cylinder.display_name)

            if (
                    lot.product_id != product
                    or cylinder.serial_number != lot.name
            ):
                raise UserError(_(
                    'El producto o número de serie del '
                    'cilindro %s no coincide.'
                ) % cylinder.display_name)

            if (
                    lot.company_id
                    and lot.company_id != self.company_id
            ):
                raise UserError(_(
                    'La serie %s pertenece a otra compañía.'
                ) % lot.name)

            if product.tracking != 'serial':
                raise UserError(_(
                    'El producto %s debe tener seguimiento '
                    'por número de serie.'
                ) % product.display_name)

            if product.uom_id.rounding > 1.0:
                raise UserError(_(
                    'La unidad de medida del cilindro '
                    'no permite mover una unidad exacta.'
                ))

            if (
                    line.gas_product_id.product_tmpl_id
                            .gas_product_type != 'gas'
            ):
                raise UserError(_(
                    'Seleccione un producto clasificado como gas.'
                ))

    def _check_serial_availability(self, cylinder):
        """Comprueba la disponibilidad exacta de una serie.

        Consulta stock.quant; nunca modifica sus cantidades.
        """
        self.ensure_one()

        product = cylinder.product_id
        lot = cylinder.lot_id
        source = self.config_id.location_src_id

        Quant = self.env['stock.quant'].with_company(
            self.company_id
        )

        quants = Quant.search([
            ('product_id', '=', product.id),
            ('lot_id', '=', lot.id),
            ('location_id', '=', source.id),
            ('company_id', '=', self.company_id.id),
        ])

        available = sum(
            quant.quantity - quant.reserved_quantity
            for quant in quants
        )

        if float_compare(
                available,
                1.0,
                precision_rounding=product.uom_id.rounding,
        ) < 0:
            raise UserError(_(
                'La serie %(serial)s no tiene una unidad '
                'disponible en %(location)s. '
                'Disponible: %(quantity)s.'
            ) % {
                                'serial': lot.name,
                                'location': source.display_name,
                                'quantity': available,
                            })

    def _create_outgoing_picking(self):
        self.ensure_one()

        if self.outgoing_picking_id:
            return self.outgoing_picking_id

        self._check_supplier_refill_outgoing()

        # Evitar preparación simultánea de la misma operación.
        self.env.cr.execute(
            'SELECT id FROM gas_cylinder_operation '
            'WHERE id = %s FOR UPDATE',
            [self.id],
        )

        self.invalidate_recordset(['outgoing_picking_id'])

        if self.outgoing_picking_id:
            return self.outgoing_picking_id

        config = self.config_id

        lot_ids = self.line_ids.mapped('cylinder_id.lot_id').ids

        # Bloquear existencias de las series seleccionadas.
        self.env.cr.execute(
            """
            SELECT id
              FROM stock_quant
             WHERE lot_id = ANY(%s)
               AND location_id = %s
               AND company_id = %s
             ORDER BY id
             FOR UPDATE
            """,
            [
                lot_ids,
                config.location_src_id.id,
                self.company_id.id,
            ],
        )

        # Verificar disponibilidad de cada cilindro.
        for cylinder in self.line_ids.mapped('cylinder_id'):
            self._check_serial_availability(cylinder)

        Picking = self.env['stock.picking'].with_company(self.company_id)

        Move = self.env['stock.move'].with_company(self.company_id)

        # Crear transferencia de salida.
        picking = Picking.create({
            'picking_type_id': config.picking_type_id.id,
            'location_id': config.location_src_id.id,
            'location_dest_id': config.location_dest_id.id,
            'company_id': self.company_id.id,
            'origin': self.name,
        })

        expected_lots = {}

        # Crear un movimiento por cada cilindro.
        for line in self.line_ids:
            cylinder = line.cylinder_id
            product = cylinder.product_id

            move = Move.create({
                'name': '%s - Serie %s' % (
                    product.display_name,
                    cylinder.lot_id.name,
                ),
                'picking_id': picking.id,
                'product_id': product.id,
                'product_uom_qty': 1.0,
                'product_uom': product.uom_id.id,
                'location_id': config.location_src_id.id,
                'location_dest_id': config.location_dest_id.id,
                'company_id': self.company_id.id,
                'picking_type_id': config.picking_type_id.id,
            })

            expected_lots[move.id] = cylinder.lot_id

        # Confirmar sin fusionar movimientos.
        picking.move_ids._action_confirm(merge=False)

        # Eliminar reservas automáticas si existen.
        moves_to_unreserve = picking.move_ids.filtered(
            lambda move: move.move_line_ids
        )

        if moves_to_unreserve:
            moves_to_unreserve._do_unreserve()

        # Reservar cada cilindro por su serie exacta.
        for move in picking.move_ids:
            expected_lot = expected_lots.get(move.id)
            if not expected_lot:
                raise UserError(_(
                    'Se encontró un movimiento sin una '
                    'serie de cilindro asociada.'
                ))

            # 2. Verificar caducidad cuando el producto la utiliza.
            if (
                    move.product_id.use_expiration_date
                    and expected_lot.expiration_date
                    and expected_lot.expiration_date <= move.date
            ):
                raise UserError(_(
                    'La serie %(serial)s está vencida. '
                    'Fecha de caducidad: %(expiration)s. '
                    'No se puede reservar.'
                ) % {
                                    'serial': expected_lot.name,
                                    'expiration': expected_lot.expiration_date,
                                })

            # IMPORTANTE:
            # Ejecutar la reserva una sola vez.
            taken_quantity = move._update_reserved_quantity(
                need=1.0,
                location_id=config.location_src_id,
                lot_id=expected_lot,
                strict=True,
            )
            move.invalidate_recordset(['move_line_ids'])
            # Verificar cantidad reservada.
            if float_compare(
                    taken_quantity,
                    1.0,
                    precision_rounding=move.product_uom.rounding,
            ) != 0:
                raise UserError(_(
                    'No se pudo reservar la serie %(serial)s. '
                    'Cantidad reservada: %(quantity)s.'
                ) % {
                                    'serial': expected_lot.name,
                                    'quantity': taken_quantity,
                                })

            # Obtener líneas reservadas.
            reserved_lines = move.move_line_ids.filtered(
                lambda ml: ml.quantity > 0
            )

            reserved_qty = sum(
                reserved_lines.mapped('quantity')
            )

            # Verificar producto, serie y ubicación.
            correct_lot = (
                    bool(reserved_lines)
                    and all(
                ml.lot_id == expected_lot
                and ml.product_id == move.product_id
                and ml.location_id == config.location_src_id
                for ml in reserved_lines
            )
            )

            if (
                    not correct_lot
                    or float_compare(
                reserved_qty,
                1.0,
                precision_rounding=move.product_uom.rounding,
            ) != 0
            ):
                raise UserError(_(
                    'La reserva del cilindro %(serial)s '
                    'no coincide con el movimiento esperado.'
                ) % {
                                    'serial': expected_lot.name,
                                })

        # Actualizar estados después de reservar.
        picking.move_ids._recompute_state()

        # Todos los movimientos deben quedar asignados.
        for move in picking.move_ids:
            if move.state != 'assigned':
                raise UserError(_(
                    'El movimiento %(move)s no quedó '
                    'en estado asignado.'
                ) % {
                                    'move': move.display_name,
                                })

        # Vincular transferencia a la operación.
        self.write({
            'outgoing_picking_id': picking.id,
            'picking_ids': [(4, picking.id)],
        })

        return picking

    def action_ready(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_(
                    'Solo se pueden preparar operaciones '
                    'en borrador.'
                ))

            if not rec.line_ids:
                raise UserError(_(
                    'Agregue líneas antes de preparar.'
                ))

            if rec.operation_type == 'supplier_refill':
                rec._create_outgoing_picking()

            rec.state = 'ready'

        return True

    def action_cancel(self):
        for rec in self:
            if rec.state == 'done':
                raise UserError(_(
                    'Las operaciones finalizadas requieren '
                    'una reversión explícita.'
                ))

            pickings = (
                    rec.picking_ids
                    | rec.outgoing_picking_id
                    | rec.return_picking_id
            )

            if any(p.state == 'done' for p in pickings):
                raise UserError(_(
                    'No se puede cancelar porque existen '
                    'transferencias realizadas.'
                ))

            pending = pickings.filtered(
                lambda p: p.state != 'cancel'
            )

            if pending:
                pending.action_cancel()

            rec.state = 'cancel'

        return True

    def action_done(self):
        raise UserError(_(
            'La recepción y contabilización del gas '
            'todavía no están implementadas.'
        ))
