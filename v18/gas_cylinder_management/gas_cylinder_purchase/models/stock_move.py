
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class StockMove(models.Model):
    _inherit = 'stock.move'

    gas_refill_cylinder_id = fields.Many2one(
        'gas.cylinder',
        string='Cilindro de recarga',
        copy=False,
        ondelete='restrict',
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        """
        Propaga el cilindro desde purchase.order.line
        al movimiento de inventario generado por la compra.
        """
        PurchaseLine = self.env['purchase.order.line']

        for vals in vals_list:
            purchase_line_id = vals.get('purchase_line_id')

            if not purchase_line_id:
                continue

            purchase_line = PurchaseLine.browse(
                purchase_line_id
            ).exists()

            if (
                purchase_line
                and purchase_line.gas_refill_cylinder_id
                and not purchase_line.display_type
                and purchase_line.product_id.product_tmpl_id
                    .gas_product_type == 'gas'
            ):
                vals['gas_refill_cylinder_id'] = (
                    purchase_line.gas_refill_cylinder_id.id
                )

        return super().create(vals_list)

    def _action_done(self, cancel_backorder=False):
        """
        Contabiliza el gas cuando stock.move termina.

        La contabilización se ejecuta después del proceso
        estándar, pero dentro de la misma transacción.
        """
        result = super()._action_done(
            cancel_backorder=cancel_backorder
        )

        completed_moves = result.filtered(
            lambda move:
                move.state == 'done'
                and move.gas_refill_cylinder_id
                and move.purchase_line_id
                and move.picking_id
                and move.picking_id.picking_type_id.code
                    == 'incoming'
                and move.product_id.product_tmpl_id
                    .gas_product_type == 'gas'
        )

        for move in completed_moves.sorted('id'):
            move._post_purchase_gas_content()

        return result

    def _post_purchase_gas_content(self):
        """
        Registra el ingreso físico y disponible de gas
        en el cilindro asociado a la compra.

        No registra movimientos para productos cilindro.
        """
        self.ensure_one()

        if self.state != 'done':
            raise UserError(_(
                'El movimiento de inventario debe estar '
                'completado antes de registrar el contenido.'
            ))

        cylinder = self.gas_refill_cylinder_id
        gas = self.product_id
        purchase_line = self.purchase_line_id

        if not cylinder or not purchase_line:
            return False

        if (
            gas.product_tmpl_id.gas_product_type != 'gas'
            or self.picking_id.picking_type_id.code
                != 'incoming'
        ):
            return False

        if (
            purchase_line.gas_refill_cylinder_id != cylinder
            or purchase_line.product_id != gas
            or purchase_line.order_id.company_id
                != cylinder.company_id
            or self.company_id != cylinder.company_id
        ):
            raise UserError(_(
                'La recepción no corresponde al gas, '
                'cilindro o empresa de la compra.'
            ))

        if (
            cylinder.ownership_type != 'own'
            or not cylinder.active
        ):
            raise UserError(_(
                'El cilindro debe estar activo y ser '
                'propiedad de la empresa.'
            ))

        if gas not in cylinder.allowed_gas_product_ids:
            raise UserError(_(
                'El gas %(gas)s no es compatible con '
                'el cilindro %(cylinder)s.'
            ) % {
                'gas': gas.display_name,
                'cylinder': cylinder.display_name,
            })

        # La cantidad ejecutada de stock.move en Odoo 18
        # se expresa en la UdM del movimiento.
        quantity = self.product_uom._compute_quantity(
            self.quantity,
            gas.uom_id,
            round=False,
        )

        quantity = round(quantity, 3)

        if float_is_zero(
            quantity,
            precision_digits=3,
        ):
            return False

        if float_compare(
            quantity,
            0.0,
            precision_digits=3,
        ) < 0:
            raise UserError(_(
                'La cantidad recibida no puede ser negativa.'
            ))

        Content = self.env[
            'gas.cylinder.content'
        ].sudo().with_company(cylinder.company_id)

        Ledger = self.env[
            'gas.cylinder.content.move'
        ].sudo().with_company(cylinder.company_id)

        # Serialización por cilindro.
        # Evita que dos recepciones simultáneas
        # sobrepasen la capacidad disponible.
        self.env.cr.execute(
            """
            SELECT id
              FROM gas_cylinder
             WHERE id = %s
             FOR UPDATE
            """,
            (cylinder.id,),
        )

        # Evitar contabilizar dos veces el mismo
        # movimiento de inventario.
        existing = Ledger.search([
            ('stock_move_id', '=', self.id),
            ('cylinder_id', '=', cylinder.id),
            ('gas_product_id', '=', gas.id),
        ], limit=1)

        if existing:
            return False

        balances = Content.search([
            ('cylinder_id', '=', cylinder.id),
        ])

        balances.invalidate_recordset([
            'quantity',
            'available_quantity',
        ])

        balance = balances.filtered(
            lambda record:
                record.gas_product_id == gas
        )

        if len(balance) > 1:
            raise UserError(_(
                'Existen saldos duplicados para el '
                'mismo gas y cilindro.'
            ))

        current_total = sum(
            balances.mapped('quantity')
        )

        new_total = current_total + quantity

        if float_compare(
            new_total,
            cylinder.capacity,
            precision_digits=3,
        ) > 0:
            raise UserError(_(
                'La recepción supera la capacidad '
                'del cilindro %(cylinder)s.\n'
                'Capacidad: %(capacity).3f m³.\n'
                'Contenido actual: %(current).3f m³.\n'
                'Ingreso: %(incoming).3f m³.'
            ) % {
                'cylinder': cylinder.display_name,
                'capacity': cylinder.capacity,
                'current': current_total,
                'incoming': quantity,
            })

        posting_context = {
            'gas_content_posting': True,
        }

        if balance:
            balance.with_context(
                **posting_context
            ).write({
                'quantity': round(
                    balance.quantity + quantity, 3
                ),
                'available_quantity': round(
                    balance.available_quantity + quantity, 3
                ),
            })
        else:
            Content.with_context(
                **posting_context
            ).create({
                'cylinder_id': cylinder.id,
                'gas_product_id': gas.id,
                'quantity': quantity,
                'available_quantity': quantity,
            })

        Ledger.with_context(
            **posting_context
        ).create({
            'cylinder_id': cylinder.id,
            'gas_product_id': gas.id,
            'stock_move_id': self.id,
            'quantity_delta': quantity,
            'available_delta': quantity,
            'note': _(
                'Compra de gas %(order)s / '
                'Recepción %(picking)s'
            ) % {
                'order': purchase_line.order_id.name,
                'picking': self.picking_id.name,
            },
        })

        return True
