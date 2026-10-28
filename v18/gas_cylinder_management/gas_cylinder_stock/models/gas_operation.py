from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare
import inspect


class GasOperation(models.Model):
    _name = 'gas.cylinder.operation'
    _description = 'Gas Cylinder Business Operation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(default='Nuevo', required=True, copy=False, string='N.º de operación')
    company_id = fields.Many2one('res.company', string="Empresa", required=True,
                                 default=lambda self: self.env.company, )
    partner_id = fields.Many2one('res.partner', string='Proveedor / Cliente', required=True, copy=False)
    operation_type = fields.Selection([
        ('supplier_refill', 'Reposición por parte del proveedor'),
        ('customer_refill', 'Recarga para el cliente'),
        ('sale', 'Venta'),
        ('rental_out', 'En alquiler'),
        ('rental_return', 'Devolución de alquiler'),
        ('recovery', 'Recuperación'),
        ('transfer', 'Transferir'),
        ('adjustment', 'Ajuste'),
    ], required=True, string='Tipo de operación')
    config_id = fields.Many2one('gas.cylinder.operation.config', string="Configuración logística")
    line_ids = fields.One2many('gas.cylinder.operation.line', 'operation_id', )
    picking_ids = fields.Many2many('stock.picking', string='Related Pickings', copy=False, )
    outgoing_picking_id = fields.Many2one('stock.picking', string='Transferencia de envío', copy=False, readonly=True, )
    return_picking_id = fields.Many2one('stock.picking', string='Transferencia de retorno', copy=False, readonly=True, )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('ready', 'Ready'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], default='draft', required=True, tracking=True, )

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

    def _check_refill_capacity(self):
        Content = self.env['gas.cylinder.content']

        for rec in self:
            if rec.operation_type != 'supplier_refill':
                continue

            for line in rec.line_ids:
                cylinder = line.cylinder_id

                if not cylinder:
                    continue

                balances = Content.search([
                    ('cylinder_id', '=', cylinder.id),
                ])

                current = sum(balances.mapped('quantity'))
                available = max(cylinder.capacity - current, 0.0)

                if float_compare(
                        line.quantity,
                        available,
                        precision_digits=3,
                ) > 0:
                    raise UserError(
                        'No se puede preparar la recarga.\n\n'
                        'Cilindro: %s\n'
                        'Capacidad máxima: %.3f m³\n'
                        'Contenido actual: %.3f m³\n'
                        'Espacio disponible: %.3f m³\n'
                        'Recarga planificada: %.3f m³'
                        % (
                            cylinder.serial_number,
                            cylinder.capacity,
                            current,
                            available,
                            line.quantity,
                        )
                    )

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
                # Validar antes de generar transferencias.
                for line in rec.line_ids:
                    if float_compare(
                            line.quantity,
                            0.0,
                            precision_digits=3,
                    ) <= 0:
                        raise UserError(_(
                            'No se puede preparar la recarga.\n\n'
                            'Cilindro: %(serial)s\n'
                            'Gas planificado: %(quantity).3f m³\n\n'
                            'La cantidad planificada debe ser mayor que cero.'
                        ) % {
                                            'serial': line.cylinder_id.serial_number,
                                            'quantity': line.quantity,
                                        })

                rec._check_refill_capacity()
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
        Content = self.env['gas.cylinder.content'].sudo()
        Ledger = self.env['gas.cylinder.content.move'].sudo()

        for rec in self:
            if rec.operation_type != 'supplier_refill':
                raise UserError(_(
                    'El cierre solo está implementado '
                    'para recargas de proveedor.'
                ))

            # Serializar cierres de una misma operación.
            self.env.cr.execute(
                """
                SELECT id
                  FROM gas_cylinder_operation
                 WHERE id = %s
                 FOR UPDATE
                """,
                [rec.id],
            )

            rec.invalidate_recordset(['state'])

            if rec.state != 'ready':
                raise UserError(_(
                    'La operación debe estar en estado Ready.'
                ))

            outgoing = rec.outgoing_picking_id
            incoming = rec.return_picking_id

            if not outgoing or outgoing.state != 'done':
                raise UserError(_(
                    'La transferencia de salida '
                    'debe estar finalizada.'
                ))

            if not incoming or incoming.state != 'done':
                raise UserError(_(
                    'La transferencia de retorno '
                    'debe estar finalizada.'
                ))

            if (
                    outgoing.company_id != rec.company_id
                    or incoming.company_id != rec.company_id
            ):
                raise UserError(_(
                    'Las transferencias deben pertenecer '
                    'a la compañía de la operación.'
                ))

            if not rec.line_ids:
                raise UserError(_(
                    'La operación no tiene cilindros.'
                ))

            cylinder_ids = rec.line_ids.mapped('cylinder_id').ids

            if len(cylinder_ids) != len(rec.line_ids):
                raise UserError(_(
                    'Existen cilindros duplicados.'
                ))

            # Verificar las series realmente transferidas.
            for picking in (outgoing, incoming):
                move_lines = picking.move_line_ids.filtered(
                    lambda ml: ml.state == 'done'
                               and ml.quantity > 0
                )

                for line in rec.line_ids:
                    cylinder = line.cylinder_id

                    matching = move_lines.filtered(
                        lambda ml:
                        ml.product_id == cylinder.product_id
                        and ml.lot_id == cylinder.lot_id
                    )

                    total = sum(matching.mapped('quantity'))

                    if float_compare(
                            total,
                            1.0,
                            precision_rounding=cylinder.product_id.uom_id.rounding,
                    ) != 0:
                        raise UserError(_(
                            'La transferencia %(picking)s '
                            'no contiene exactamente una unidad '
                            'de la serie %(serial)s.'
                        ) % {
                                            'picking': picking.name,
                                            'serial': cylinder.serial_number,
                                        })

                if len(move_lines) != len(rec.line_ids):
                    raise UserError(_(
                        'La transferencia %s contiene '
                        'líneas adicionales o inesperadas.'
                    ) % picking.name)

            # Bloquear por cilindro, incluso si aún no existe
            # un registro en gas.cylinder.content.
            self.env.cr.execute(
                """
                SELECT id
                  FROM gas_cylinder
                 WHERE id = ANY(%s)
                 ORDER BY id
                 FOR UPDATE
                """,
                [cylinder_ids],
            )

            # Bloquear los saldos existentes.
            self.env.cr.execute(
                """
                SELECT id
                  FROM gas_cylinder_content
                 WHERE cylinder_id = ANY(%s)
                 ORDER BY id
                 FOR UPDATE
                """,
                [cylinder_ids],
            )

            if Ledger.search([
                ('operation_id', '=', rec.id),
            ], limit=1):
                raise UserError(_(
                    'La operación ya tiene movimientos '
                    'de contenido contabilizados.'
                ))

            movements = []

            for line in rec.line_ids:
                cylinder = line.cylinder_id
                gas = line.gas_product_id
                final_qty = line.quantity_received
                print("final_qty", final_qty)

                if float_compare(final_qty, 0.0, precision_digits=3, ) <= 0:
                    raise UserError(_(
                        'Debe registrar una cantidad de gas recibido '
                        'mayor que cero para el cilindro %s.'
                    ) % cylinder.serial_number)

                if cylinder.company_id != rec.company_id:
                    raise UserError(_(
                        'El cilindro pertenece a otra compañía.'
                    ))

                if cylinder.ownership_type != 'own':
                    raise UserError(_(
                        'Esta operación solo admite '
                        'cilindros propios.'
                    ))

                if gas.product_tmpl_id.gas_product_type != 'gas':
                    raise UserError(_(
                        'El producto seleccionado no es gas.'
                    ))

                if float_compare(
                        final_qty,
                        0.0,
                        precision_digits=3,
                ) < 0:
                    raise UserError(_(
                        'El contenido recibido no puede '
                        'ser negativo.'
                    ))

                if float_compare(
                        final_qty,
                        cylinder.capacity,
                        precision_digits=3,
                ) > 0:
                    raise UserError(_(
                        'El contenido de la serie %s '
                        'supera su capacidad.'
                    ) % cylinder.serial_number)

                # Para esta primera versión no se permite
                # reemplazar un gas distinto que todavía
                # tenga contenido registrado.
                other_balances = Content.search([
                    ('cylinder_id', '=', cylinder.id),
                    ('gas_product_id', '!=', gas.id),
                    ('quantity', '>', 0),
                ])

                if other_balances:
                    raise UserError(_(
                        'El cilindro %s tiene contenido '
                        'registrado de otro gas. '
                        'Debe regularizarse antes de la recarga.'
                    ) % cylinder.serial_number)

                balance = Content.search([
                    ('cylinder_id', '=', cylinder.id),
                    ('gas_product_id', '=', gas.id),
                ], limit=1)

                if not balance:
                    balance = Content.create({
                        'cylinder_id': cylinder.id,
                        'gas_product_id': gas.id,
                    })

                previous_qty = balance.quantity
                previous_available = balance.available_quantity

                received_qty = line.quantity_received

                # La cantidad recibida representa gas adicional.
                final_qty = previous_qty + received_qty
                final_available = previous_available + received_qty

                # Validar la capacidad considerando el contenido anterior.
                if float_compare(
                        final_qty,
                        cylinder.capacity,
                        precision_digits=3,
                ) > 0:
                    raise UserError(_(
                        'La recarga de %(received).3f m³ supera la capacidad '
                        'del cilindro %(serial)s. '
                        'Contenido anterior: %(previous).3f m³. '
                        'Capacidad máxima: %(capacity).3f m³.'
                    ) % {
                                        'received': received_qty,
                                        'serial': cylinder.serial_number,
                                        'previous': previous_qty,
                                        'capacity': cylinder.capacity,
                                    })

                balance.with_context(
                    gas_content_posting=True
                ).write({
                    'quantity': final_qty,
                    'available_quantity': final_available,
                })

                movements.append({
                    'cylinder_id': cylinder.id,
                    'gas_product_id': gas.id,
                    'operation_id': rec.id,
                    'quantity_delta': received_qty,
                    'available_delta': received_qty,
                    'note': (
                                'Recarga proveedor %s - '
                                'Contenido anterior: %.3f m³ - '
                                'Gas recibido: %.3f m³ - '
                                'Contenido final: %.3f m³'
                            ) % (
                                rec.display_name,
                                previous_qty,
                                received_qty,
                                final_qty,
                            ),
                })

            Ledger.with_context(
                gas_content_posting=True
            ).create(movements)

            rec.write({'state': 'done'})

        return True

    def _create_return_picking(self):
        self.ensure_one()

        if self.return_picking_id:
            return self.return_picking_id

        if self.operation_type != 'supplier_refill':
            raise UserError(_(
                'El retorno solo está disponible para recargas de proveedor.'
            ))

        if self.state != 'ready':
            raise UserError(_(
                'La operación debe estar en estado Ready.'
            ))

        if (
                not self.outgoing_picking_id
                or self.outgoing_picking_id.state != 'done'
        ):
            raise UserError(_(
                'Primero debe validar la transferencia de salida.'
            ))

        # Bloquear la operación para evitar retornos duplicados.
        self.env.cr.execute(
            """
            SELECT id
            FROM gas_cylinder_operation
            WHERE id = %s
            FOR UPDATE
            """,
            [self.id],
        )

        self.invalidate_recordset(['return_picking_id'])

        if self.return_picking_id:
            return self.return_picking_id

        config = self.config_id
        source = config.return_location_src_id
        destination = config.return_location_dest_id
        picking_type = config.return_picking_type_id

        if not source or not destination or not picking_type:
            raise UserError(_(
                'Complete la configuración logística de retorno.'
            ))

        if (
                source == destination
                or source.usage != 'internal'
                or destination.usage != 'internal'
                or picking_type.code != 'internal'
        ):
            raise UserError(_(
                'El retorno requiere dos ubicaciones internas '
                'diferentes y un tipo de traslado interno.'
            ))

        if (
                picking_type.company_id
                and picking_type.company_id != self.company_id
        ):
            raise UserError(_(
                'El tipo de traslado pertenece a otra compañía.'
            ))

        for location in (source, destination):
            if location.company_id and location.company_id != self.company_id:
                raise UserError(_(
                    'Una ubicación pertenece a otra compañía.'
                ))

        # Verificar que no se repitan cilindros.
        cylinders = self.line_ids.mapped('cylinder_id')

        if len(cylinders) != len(self.line_ids):
            raise UserError(_(
                'La operación contiene cilindros duplicados.'
            ))

        # Bloquear las existencias de las series de retorno.
        lot_ids = cylinders.mapped('lot_id').ids

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
            [lot_ids, source.id, self.company_id.id],
        )

        Quant = self.env['stock.quant'].with_company(self.company_id)

        for cylinder in cylinders:
            quants = Quant.search([
                ('product_id', '=', cylinder.product_id.id),
                ('lot_id', '=', cylinder.lot_id.id),
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
                    precision_rounding=cylinder.product_id.uom_id.rounding,
            ) < 0:
                raise UserError(_(
                    'La serie %(serial)s no está disponible '
                    'en la ubicación de retorno. Disponible: %(qty)s.'
                ) % {
                                    'serial': cylinder.lot_id.name,
                                    'qty': available,
                                })

        Picking = self.env['stock.picking'].with_company(self.company_id)
        Move = self.env['stock.move'].with_company(self.company_id)

        picking = Picking.create({
            'picking_type_id': picking_type.id,
            'location_id': source.id,
            'location_dest_id': destination.id,
            'company_id': self.company_id.id,
            'origin': self.outgoing_picking_id.name,
        })

        expected_lots = {}

        for cylinder in cylinders:
            product = cylinder.product_id

            move = Move.create({
                'name': '%s - Retorno serie %s' % (
                    product.display_name,
                    cylinder.lot_id.name,
                ),
                'picking_id': picking.id,
                'product_id': product.id,
                'product_uom_qty': 1.0,
                'product_uom': product.uom_id.id,
                'location_id': source.id,
                'location_dest_id': destination.id,
                'company_id': self.company_id.id,
                'picking_type_id': picking_type.id,
            })

            expected_lots[move.id] = cylinder.lot_id

        # Confirmar sin fusionar movimientos.
        picking.move_ids._action_confirm(merge=False)

        # Retirar cualquier reserva automática.
        moves_to_unreserve = picking.move_ids.filtered(
            lambda move: move.move_line_ids
        )

        if moves_to_unreserve:
            moves_to_unreserve._do_unreserve()

        # Reservar exactamente cada serie.
        for move in picking.move_ids:
            expected_lot = expected_lots.get(move.id)

            if not expected_lot:
                raise UserError(_(
                    'Se encontró un movimiento sin serie asociada.'
                ))

            # El motor estándar también aplicará las restricciones
            # de caducidad que correspondan al producto.
            taken_quantity = move._update_reserved_quantity(
                need=1.0,
                location_id=source,
                lot_id=expected_lot,
                strict=True,
            )

            move.invalidate_recordset(['move_line_ids'])

            if float_compare(
                    taken_quantity,
                    1.0,
                    precision_rounding=move.product_uom.rounding,
            ) != 0:
                raise UserError(_(
                    'No se pudo reservar la serie %(serial)s. '
                    'Cantidad reservada: %(qty)s.'
                ) % {
                                    'serial': expected_lot.name,
                                    'qty': taken_quantity,
                                })

            reserved_lines = move.move_line_ids.filtered(
                lambda ml: ml.quantity > 0
            )

            reserved_qty = sum(reserved_lines.mapped('quantity'))

            if (
                    not reserved_lines
                    or any(
                ml.lot_id != expected_lot
                or ml.product_id != move.product_id
                or ml.location_id != source
                for ml in reserved_lines
            )
                    or float_compare(
                reserved_qty,
                1.0,
                precision_rounding=move.product_uom.rounding,
            ) != 0
            ):
                raise UserError(_(
                    'La reserva de la serie %s no coincide '
                    'con el movimiento esperado.'
                ) % expected_lot.name)

        picking.move_ids._recompute_state()

        for move in picking.move_ids:
            if move.state != 'assigned':
                raise UserError(_(
                    'El movimiento %s no quedó disponible.'
                ) % move.display_name)

        self.write({
            'return_picking_id': picking.id,
            'picking_ids': [(4, picking.id)],
        })

        return picking

    def action_prepare_return(self):
        for rec in self:
            rec._create_return_picking()

        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if (
                    vals.get('operation_type') == 'supplier_refill'
                    and vals.get('name', 'Nuevo') in ('Nuevo', '/')
            ):
                sequence = self.env['ir.sequence'].with_company(
                    self.env['res.company'].browse(
                        vals.get('company_id') or self.env.company.id
                    )
                )

                vals['name'] = (
                        sequence.next_by_code(
                            'gas.cylinder.operation.supplier.refill'
                        ) or 'Nuevo'
                )

                if vals['name'] == 'Nuevo':
                    raise UserError(_(
                        'No se encontró la secuencia '
                        'para recargas de proveedor.'
                    ))

        return super().create(vals_list)

    def write(self, vals):
        protected_fields = {
            'name',
            'operation_type',
            'partner_id',
            'company_id',
            'config_id',
            'line_ids',
            'picking_ids',
            'outgoing_picking_id',
            'return_picking_id',
            'state',
        }

        if protected_fields.intersection(vals):
            if any(operation.state == 'done' for operation in self):
                raise ValidationError(_(
                    'No se pueden modificar los datos de una '
                    'operación de gases finalizada.'
                ))

        return super().write(vals)

    def unlink(self):
        Ledger = self.env['gas.cylinder.content.move']

        for operation in self:
            if operation.state == 'done':
                raise ValidationError(_(
                    'No se puede eliminar la operación %s '
                    'porque está finalizada.'
                ) % operation.display_name)

            if (
                    operation.picking_ids
                    or operation.outgoing_picking_id
                    or operation.return_picking_id
            ):
                raise ValidationError(_(
                    'No se puede eliminar la operación %s '
                    'porque tiene transferencias asociadas.'
                ) % operation.display_name)

            if Ledger.search_count([
                ('operation_id', '=', operation.id),
            ]):
                raise ValidationError(_(
                    'No se puede eliminar la operación %s '
                    'porque tiene movimientos en el kardex.'
                ) % operation.display_name)

        return super().unlink()
