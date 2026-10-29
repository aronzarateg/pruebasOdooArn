
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    gas_refill_cylinder_id = fields.Many2one(
        'gas.cylinder',
        string='Cilindro / serie',
        copy=False,
        ondelete='restrict',
        index=True,
    )

    gas_refill_reference = fields.Boolean(
        string='Referencia de recarga',
        default=False,
        copy=False,
    )

    gas_refill_source_line_id = fields.Many2one(
        'purchase.order.line',
        string='Referencia de cilindro',
        copy=False,
        ondelete='restrict',
        index=True,
    )

    gas_can_select = fields.Boolean(
        string='Puede seleccionar gas',
        compute='_compute_gas_can_select',
    )

    @api.depends(
        'product_id',
        'order_id.state',
        'gas_refill_reference',
        'display_type',
    )
    def _compute_gas_can_select(self):
        Cylinder = self.env['gas.cylinder'].sudo()

        for line in self:
            line.gas_can_select = False

            if (
                not line.product_id
                or line.display_type
                or line.gas_refill_reference
                or line.order_id.state not in ('draft', 'sent')
                or line.product_id.product_tmpl_id.gas_product_type
                    != 'cylinder'
            ):
                continue

            line.gas_can_select = bool(Cylinder.search([
                ('product_id', '=', line.product_id.id),
                ('company_id', '=', line.order_id.company_id.id),
                ('ownership_type', '=', 'own'),
                ('active', '=', True),
            ], limit=1))

    @api.constrains(
        'gas_refill_cylinder_id',
        'gas_refill_reference',
        'gas_refill_source_line_id',
        'product_id',
        'display_type',
        'order_id',
    )
    def _check_gas_refill_data(self):
        for line in self:
            cylinder = line.gas_refill_cylinder_id

            if line.gas_refill_reference:
                if line.display_type != 'line_section' or not cylinder:
                    raise ValidationError(_(
                        'La referencia de recarga debe ser '
                        'una sección vinculada a un cilindro.'
                    ))

            if not cylinder:
                if line.gas_refill_source_line_id:
                    raise ValidationError(_(
                        'La línea de gas debe identificar '
                        'su cilindro físico.'
                    ))
                continue

            if cylinder.company_id != line.order_id.company_id:
                raise ValidationError(_(
                    'El cilindro pertenece a otra empresa.'
                ))

            if cylinder.ownership_type != 'own':
                raise ValidationError(_(
                    'Solo se admiten cilindros propios.'
                ))

            if not cylinder.active:
                raise ValidationError(_(
                    'El cilindro está inactivo.'
                ))

            if line.display_type:
                continue

            if (
                line.product_id.product_tmpl_id.gas_product_type
                != 'gas'
            ):
                raise ValidationError(_(
                    'La línea de recarga debe contener gas.'
                ))

            if line.product_id not in cylinder.allowed_gas_product_ids:
                raise ValidationError(_(
                    'El gas no es compatible con el cilindro %s.'
                ) % cylinder.display_name)

            source = line.gas_refill_source_line_id

            if source and (
                source.order_id != line.order_id
                or not source.gas_refill_reference
                or source.gas_refill_cylinder_id != cylinder
            ):
                raise ValidationError(_(
                    'La referencia de recarga no corresponde '
                    'al cilindro de esta línea.'
                ))

    def action_select_gas(self):
        self.ensure_one()

        if self.order_id.state not in ('draft', 'sent'):
            raise UserError(_(
                'La orden debe estar en borrador.'
            ))

        if (
            self.display_type
            or not self.product_id
            or self.product_id.product_tmpl_id.gas_product_type
                != 'cylinder'
        ):
            raise UserError(_(
                'Seleccione una línea de producto '
                'clasificado como cilindro.'
            ))

        cylinders = self.env['gas.cylinder'].search([
            ('product_id', '=', self.product_id.id),
            ('company_id', '=', self.order_id.company_id.id),
            ('ownership_type', '=', 'own'),
            ('active', '=', True),
        ])

        if not cylinders:
            raise UserError(_(
                'No existen cilindros físicos registrados '
                'para este producto.'
            ))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Seleccionar gas para cilindro'),
            'res_model': 'gas.purchase.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_purchase_order_id': self.order_id.id,
                'default_purchase_line_id': self.id,
                'default_cylinder_product_id': self.product_id.id,
            },
        }
