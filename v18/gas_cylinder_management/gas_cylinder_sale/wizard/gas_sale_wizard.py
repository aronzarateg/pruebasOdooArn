from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class GasSaleWizard(models.TransientModel):
    _name = 'gas.sale.wizard'
    _description = 'Seleccionar gases para venta'

    sale_order_id = fields.Many2one('sale.order', required=True, readonly=True)
    sale_line_id = fields.Many2one('sale.order.line', readonly=True)
    cylinder_product_id = fields.Many2one('product.product', readonly=True)
    sale_mode = fields.Selection([
        ('gas_only', 'Solo oxigeno'),
        ('cylinder_with_gas', 'Cilindro con oxigeno'),
    ], required=True, default='gas_only', string='Modalidad')
    cylinder_id = fields.Many2one('gas.cylinder', required=True, string='Cilindro / serie')
    capacity = fields.Float(compute='_compute_content_info', digits=(16, 3), string='Capacidad (m3)')
    current_quantity = fields.Float(compute='_compute_content_info', digits=(16, 3), string='Contenido actual (m3)')
    free_capacity = fields.Float(compute='_compute_content_info', digits=(16, 3), string='Capacidad libre (m3)')
    line_ids = fields.One2many('gas.sale.wizard.line', 'wizard_id', string='Gases a vender')
    sell_cylinder = fields.Boolean(
        string='Vender cilindro con todo su contenido',
        default=False,
    )

    @api.depends('cylinder_id')
    def _compute_content_info(self):
        Content = self.env['gas.cylinder.content']
        for wizard in self:
            wizard.capacity = wizard.cylinder_id.capacity if wizard.cylinder_id else 0.0
            total = sum(Content.search([
                ('cylinder_id', '=', wizard.cylinder_id.id),
            ]).mapped('quantity')) if wizard.cylinder_id else 0.0
            wizard.current_quantity = total
            wizard.free_capacity = max(wizard.capacity - total, 0.0)

    @api.onchange('sell_cylinder', 'sale_line_id')
    def _onchange_sell_cylinder(self):
        self.sale_mode = (
            'cylinder_with_gas'
            if self.sell_cylinder
            else 'gas_only'
        )

        if self.cylinder_id:
            self._onchange_cylinder_id()

    @api.onchange('cylinder_id', 'sell_cylinder')
    def _onchange_cylinder_id(self):
        self.sale_mode = (
            'cylinder_with_gas'
            if self.sell_cylinder
            else 'gas_only'
        )

        if not self.cylinder_id:
            self.line_ids = [fields.Command.clear()]
            return

        cylinder = self.cylinder_id

        balances = self.env['gas.cylinder.content'].search([
            ('cylinder_id', '=', cylinder.id),
            ('gas_product_id', 'in',
             cylinder.allowed_gas_product_ids.ids),
        ])

        commands = []

        for balance in balances:
            if not balance.gas_product_id:
                continue

            if float_compare(
                    balance.quantity,
                    0.0,
                    precision_digits=3,
            ) <= 0:
                continue

            commands.append(fields.Command.create({
                'gas_product_id': balance.gas_product_id.id,
                'available_quantity': balance.available_quantity,
                'quantity': (
                    balance.quantity
                    if self.sell_cylinder
                    else 0.0
                ),
                'price_unit': 0.0,
            }))

        self.line_ids = [
            fields.Command.clear(),
            *commands,
        ]

    def action_add_gases(self):
        self.ensure_one()

        order = self.sale_order_id
        cylinder = self.cylinder_id
        source_line = self.sale_line_id
        sale_mode = (
            'cylinder_with_gas'
            if self.sell_cylinder
            else 'gas_only'
        )

        self.sale_mode = sale_mode
        if order.state not in ('draft', 'sent'):
            raise UserError(_(
                'Solo puede agregar gases en una cotización '
                'en borrador o enviada.'
            ))

        if not cylinder:
            raise UserError(_('Seleccione un cilindro físico.'))

        if (
                cylinder.company_id != order.company_id
                or not cylinder.active
                or cylinder.ownership_type != 'own'
        ):
            raise UserError(_(
                'Seleccione un cilindro propio, activo '
                'y perteneciente a la empresa.'
            ))

        if source_line:
            if (
                    source_line.order_id != order
                    or source_line.product_id != cylinder.product_id
            ):
                raise UserError(_(
                    'La línea seleccionada no corresponde '
                    'al cilindro físico.'
                ))

        if self.sale_mode == 'cylinder_with_gas':
            if not source_line:
                raise UserError(_(
                    'Para vender cilindro con oxígeno '
                    'debe existir una línea de cilindro.'
                ))

            if float_compare(
                    source_line.product_uom_qty,
                    1.0,
                    precision_digits=3,
            ) != 0:
                raise UserError(_(
                    'La cantidad del cilindro debe ser 1.'
                ))

        for line in self.line_ids:
            if not line.gas_product_id:
                raise UserError(_(
                    'Existe una línea sin producto de gas.'
                ))

            if float_compare(
                    line.quantity, 0.0, precision_digits=3
            ) < 0:
                raise UserError(_(
                    'No se permiten cantidades negativas.'
                ))

        selected = self.line_ids.filtered(
            lambda line: float_compare(
                line.quantity, 0.0, precision_digits=3
            ) > 0
        )

        if not selected:
            raise UserError(_(
                'Seleccione al menos un gas con cantidad positiva.'
            ))

        if len(selected.mapped('gas_product_id')) != len(selected):
            raise UserError(_(
                'No puede seleccionar dos veces el mismo gas.'
            ))

        # Bloqueo de concurrencia del cilindro.
        self.env.cr.execute(
            'SELECT id FROM gas_cylinder '
            'WHERE id = %s FOR UPDATE',
            (cylinder.id,)
        )

        Content = (
            self.env['gas.cylinder.content']
            .sudo()
            .with_company(order.company_id)
        )

        balances = Content.search([
            ('cylinder_id', '=', cylinder.id),
        ])

        balances.invalidate_recordset([
            'quantity',
            'available_quantity',
        ])

        total_content = sum(balances.mapped('quantity'))

        if float_compare(
                total_content,
                cylinder.capacity,
                precision_digits=3,
        ) > 0:
            raise UserError(_(
                'El contenido registrado supera '
                'la capacidad del cilindro.'
            ))
        if self.sell_cylinder:
            if not source_line:
                raise UserError(_(
                    'Para vender el cilindro debe existir '
                    'una línea comercial del producto cilindro.'
                ))

            positive_balances = balances.filtered(
                lambda b: float_compare(
                    b.quantity, 0.0, precision_digits=3
                ) > 0
            )

            selected_gases = self.line_ids.filtered(
                lambda line: float_compare(
                    line.quantity, 0.0, precision_digits=3
                ) > 0
            )

            if len(positive_balances) != len(selected_gases):
                raise UserError(_(
                    'La venta completa debe incluir todos '
                    'los gases contenidos en el cilindro.'
                ))

            for balance in positive_balances:
                wizard_lines = selected_gases.filtered(
                    lambda line:
                    line.gas_product_id == balance.gas_product_id
                )

                if len(wizard_lines) != 1:
                    raise UserError(_(
                        'Falta incluir el gas %s.'
                    ) % balance.gas_product_id.display_name)

                if float_compare(
                        balance.quantity,
                        balance.available_quantity,
                        precision_digits=3,
                ) != 0:
                    raise UserError(_(
                        'El gas %s tiene contenido físico '
                        'distinto de su cantidad disponible. '
                        'No se puede vender el cilindro completo '
                        'hasta resolver esa diferencia.'
                    ) % balance.gas_product_id.display_name)

                if float_compare(
                        wizard_lines.quantity,
                        balance.quantity,
                        precision_digits=3,
                ) != 0:
                    raise UserError(_(
                        'Para vender el cilindro completo, '
                        'debe incluirse toda la cantidad del gas %s.'
                    ) % balance.gas_product_id.display_name)

        # Evitar reutilizar el mismo cilindro en esta cotización.
        existing = order.order_line.filtered(
            lambda line:
            line.gas_sale_cylinder_id == cylinder
            and line != source_line
        )

        if existing:
            raise UserError(_(
                'Este cilindro ya tiene líneas de gas '
                'asociadas en la cotización.'
            ))

        for line in selected:
            gas = line.gas_product_id

            if gas not in cylinder.allowed_gas_product_ids:
                raise UserError(_(
                    'El gas %s no está permitido '
                    'para este cilindro.'
                ) % gas.display_name)

            balance = balances.filtered(
                lambda b: b.gas_product_id == gas
            )

            if len(balance) != 1:
                raise UserError(_(
                    'No existe un saldo único '
                    'para el gas %s.'
                ) % gas.display_name)

            if float_compare(
                    line.quantity,
                    balance.available_quantity,
                    precision_digits=3,
            ) > 0:
                raise UserError(_(
                    'Gas: %(gas)s\n'
                    'Disponible: %(available).3f m³\n'
                    'Solicitado: %(requested).3f m³'
                ) % {
                                    'gas': gas.display_name,
                                    'available': balance.available_quantity,
                                    'requested': line.quantity,
                                })

        SaleLine = self.env['sale.order.line']

        # Determinar la posición de la sección en la cotización.
        if source_line:
            base_sequence = source_line.sequence
        else:
            base_sequence = max(
                order.order_line.mapped('sequence') or [0]
            ) + 10

        # Modalidad: vender el cilindro y los gases.
        if self.sale_mode == 'cylinder_with_gas':
            source_line.write({
                'gas_sale_cylinder_id': cylinder.id,
                'gas_sale_mode': 'cylinder_with_gas',
            })

        # Crear sección visual para identificar el cilindro.
        section_name = _(
            'VENTA DE OXÍGENO - CILINDRO SERIE %s'
        ) % cylinder.serial_number

        section = SaleLine.create({
            'order_id': order.id,
            'name': section_name,
            'display_type': 'line_section',
            'sequence': base_sequence,
        })

        # Posicionar las líneas inmediatamente después
        # de la sección, respetando las demás líneas.
        for index, line in enumerate(selected, start=1):
            gas = line.gas_product_id

            vals = {
                'order_id': order.id,
                'product_id': gas.id,
                'name': gas.display_name,
                'product_uom_qty': line.quantity,
                'product_uom': gas.uom_id.id,
                'price_unit': line.price_unit,
                'gas_sale_cylinder_id': cylinder.id,
                'gas_sale_mode': self.sale_mode,
                'sequence': base_sequence + index,
            }

            if (
                    self.sale_mode == 'cylinder_with_gas'
                    and source_line
            ):
                vals['gas_sale_source_line_id'] = source_line.id

            SaleLine.create(vals)

        # Solo oxígeno: retirar la línea de cilindro
        # utilizada como selector comercial.
        if self.sale_mode == 'gas_only' and source_line:
            source_line.unlink()

        return {
            'type': 'ir.actions.act_window_close',
        }


class GasSaleWizardLine(models.TransientModel):
    _name = 'gas.sale.wizard.line'
    _description = 'Gas a vender por cilindro'

    wizard_id = fields.Many2one('gas.sale.wizard', required=True, ondelete='cascade')
    gas_product_id = fields.Many2one('product.product', required=True, string='Gas')
    available_quantity = fields.Float(string='Disponible (m3)', digits=(16, 3), readonly=True)
    quantity = fields.Float(string='Vender (m3)', digits=(16, 3))
    uom_id = fields.Many2one('uom.uom', related='gas_product_id.uom_id', readonly=True)
    price_unit = fields.Float(string='Precio unitario', digits='Product Price')
