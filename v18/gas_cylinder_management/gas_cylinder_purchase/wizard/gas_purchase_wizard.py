
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class GasPurchaseWizard(models.TransientModel):
    _name = 'gas.purchase.wizard'
    _description = 'Selección de gas por cilindro'

    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Orden de compra',
        required=True,
        readonly=True,
    )

    purchase_line_id = fields.Many2one(
        'purchase.order.line',
        string='Línea de cilindro',
        required=True,
        readonly=True,
    )

    cylinder_product_id = fields.Many2one(
        'product.product',
        string='Producto del cilindro',
        required=True,
        readonly=True,
    )

    company_id = fields.Many2one(
        'res.company',
        related='purchase_order_id.company_id',
        readonly=True,
    )

    cylinder_id = fields.Many2one(
        'gas.cylinder',
        string='Cilindro / serie',
        required=True,
        domain="[('product_id', '=', cylinder_product_id), "
               "('company_id', '=', company_id), "
               "('ownership_type', '=', 'own'), "
               "('active', '=', True)]",
    )

    allowed_gas_product_ids = fields.Many2many(
        'product.product',
        related='cylinder_id.allowed_gas_product_ids',
        readonly=True,
    )

    line_ids = fields.One2many(
        'gas.purchase.wizard.line',
        'wizard_id',
        string='Gases a comprar',
    )

    @api.onchange('cylinder_id')
    def _onchange_cylinder_id(self):
        self.line_ids = [(5, 0, 0)]

    def action_add_gases(self):
        self.ensure_one()

        order = self.purchase_order_id
        source = self.purchase_line_id
        cylinder = self.cylinder_id

        if order.state not in ('draft', 'sent'):
            raise UserError(_(
                'La orden de compra debe estar en borrador.'
            ))

        self.env.cr.execute(
            """
            SELECT id
            FROM purchase_order
            WHERE id = %s
            FOR UPDATE
            """,
            (order.id,),
        )

        order.invalidate_recordset(['state'])
        source.invalidate_recordset()

        if order.state not in ('draft', 'sent'):
            raise UserError(_(
                'La orden cambió de estado. Actualice la pantalla.'
            ))

        if (
                not source.exists()
                or source.order_id != order
                or source.display_type
                or source.gas_refill_reference
                or source.product_id != self.cylinder_product_id
        ):
            raise UserError(_(
                'La línea original del cilindro ya no es válida.'
            ))

        if (
                source.product_id.product_tmpl_id.gas_product_type
                != 'cylinder'
        ):
            raise UserError(_(
                'El producto seleccionado no es un cilindro.'
            ))

        if (
                not cylinder
                or cylinder.product_id != source.product_id
                or cylinder.company_id != order.company_id
                or cylinder.ownership_type != 'own'
                or not cylinder.active
        ):
            raise UserError(_(
                'El cilindro no corresponde al producto '
                'o a la empresa de la compra.'
            ))

        if (
                source.price_unit != 0
                or source.qty_received
                or source.qty_invoiced
        ):
            raise UserError(_(
                'La línea del cilindro debe estar sin precio, '
                'sin recepción y sin facturación.'
            ))

        PurchaseLine = self.env['purchase.order.line']

        existing = PurchaseLine.search([
            ('order_id', '=', order.id),
            ('gas_refill_reference', '=', True),
            ('gas_refill_cylinder_id', '=', cylinder.id),
        ], limit=1)

        if existing:
            raise UserError(_(
                'El cilindro ya tiene una referencia '
                'de recarga en esta compra.'
            ))

        # Guardar los datos del wizard antes de modificar
        # las líneas de la orden de compra.
        gas_data = []
        seen = set()
        total_quantity = 0.0

        for item in self.line_ids:
            gas = item.gas_product_id

            if not gas:
                raise UserError(_(
                    'Seleccione un producto de gas.'
                ))

            if gas.id in seen:
                raise UserError(_(
                    'El gas %s está repetido.'
                ) % gas.display_name)

            seen.add(gas.id)

            if gas not in cylinder.allowed_gas_product_ids:
                raise UserError(_(
                    'El gas %s no es compatible '
                    'con el cilindro.'
                ) % gas.display_name)

            if (
                    gas.product_tmpl_id.gas_product_type
                    != 'gas'
            ):
                raise UserError(_(
                    'El producto %s no está configurado '
                    'como gas.'
                ) % gas.display_name)

            if float_compare(
                    item.quantity,
                    0.0,
                    precision_rounding=gas.uom_id.rounding,
            ) <= 0:
                raise UserError(_(
                    'La cantidad del gas %s debe '
                    'ser mayor que cero.'
                ) % gas.display_name)

            if item.price_unit < 0:
                raise UserError(_(
                    'El precio del gas %s no puede '
                    'ser negativo.'
                ) % gas.display_name)

            gas_data.append({
                'product_id': gas.id,
                'name': gas.display_name,
                'product_qty': item.quantity,
                'product_uom': gas.uom_id.id,
                'price_unit': item.price_unit,
            })

            total_quantity += item.quantity

        if not gas_data:
            raise UserError(_(
                'Debe seleccionar al menos un gas.'
            ))

        # Esta suma presupone que todos los gases
        # utilizan una unidad comparable con m³.
        if total_quantity > cylinder.capacity + 0.001:
            raise UserError(_(
                'La cantidad total supera la capacidad '
                'del cilindro (%s m³).'
            ) % cylinder.capacity)

        original_sequence = source.sequence

        following = PurchaseLine.search([
            ('order_id', '=', order.id),
            ('id', '!=', source.id),
            ('sequence', '>=', original_sequence),
        ], order='sequence desc, id desc')

        for line in following:
            line.write({
                'sequence': line.sequence + len(gas_data) + 10,
            })

        # Primero se elimina la línea original para
        # que el envase no genere una compra.
        source.unlink()

        # Crear la sección identificadora del cilindro.
        section = PurchaseLine.create({
            'order_id': order.id,
            'display_type': 'line_section',
            'name': _(
                'RECARGA - Cilindro serie %(serial)s'
            ) % {
                        'serial': (
                                cylinder.serial_number
                                or cylinder.display_name
                        ),
                    },
            'sequence': original_sequence,

            # Valores neutros de la sección.
            'product_qty': 0.0,
            'price_unit': 0.0,

            # Identificación del cilindro.
            'gas_refill_reference': True,
            'gas_refill_cylinder_id': cylinder.id,
        })

        # Crear las líneas comerciales de gas.
        created_lines = PurchaseLine.browse()

        for index, values in enumerate(gas_data, start=1):
            vals = dict(values)

            vals.update({
                'order_id': order.id,
                'sequence': original_sequence + index,
                'date_planned': (
                        order.date_planned
                        or fields.Datetime.now()
                ),
                'gas_refill_cylinder_id': cylinder.id,
                'gas_refill_source_line_id': section.id,
            })

            created_line = PurchaseLine.create(vals)
            created_lines |= created_line

        # Forzar la escritura pendiente y verificar
        # los registros persistidos en la transacción.
        created_lines.flush_recordset([
            'order_id',
            'product_id',
            'product_qty',
            'gas_refill_cylinder_id',
            'gas_refill_source_line_id',
        ])

        actual_lines = PurchaseLine.search([
            ('id', 'in', created_lines.ids),
            ('order_id', '=', order.id),
            ('gas_refill_cylinder_id', '=', cylinder.id),
            ('gas_refill_source_line_id', '=', section.id),
        ])

        if len(actual_lines) != len(gas_data):
            raise UserError(_(
                'No se pudieron conservar todas las '
                'líneas de gas. La operación se cancelará.'
            ))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Orden de compra'),
            'res_model': 'purchase.order',
            'res_id': order.id,
            'view_mode': 'form',
            'target': 'current',
        }


class GasPurchaseWizardLine(models.TransientModel):
    _name = 'gas.purchase.wizard.line'
    _description = 'Detalle de gas por cilindro'

    wizard_id = fields.Many2one(
        'gas.purchase.wizard',
        required=True,
        ondelete='cascade',
    )

    allowed_gas_product_ids = fields.Many2many(
        'product.product',
        related='wizard_id.allowed_gas_product_ids',
        readonly=True,
    )

    gas_product_id = fields.Many2one(
        'product.product',
        string='Gas compatible',
        required=True,
        domain="[('id', 'in', allowed_gas_product_ids)]",
    )

    quantity = fields.Float(
        string='Cantidad (m³)',
        digits=(16, 3),
        required=True,
        default=1.0,
    )

    uom_id = fields.Many2one(
        'uom.uom',
        related='gas_product_id.uom_id',
        string='UdM',
        readonly=True,
    )

    price_unit = fields.Float(
        string='Precio unitario',
        digits='Product Price',
        default=0.0,
    )

