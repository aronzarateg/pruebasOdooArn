from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    gas_sale_cylinder_id = fields.Many2one(
        'gas.cylinder', string='Cilindro / serie', copy=False,
        ondelete='restrict', index=True,
    )
    gas_sale_source_line_id = fields.Many2one(
        'sale.order.line', string='Linea de cilindro relacionada',
        copy=False, ondelete='restrict', index=True,
    )
    gas_sale_mode = fields.Selection([
        ('gas_only', 'Solo oxigeno'),
        ('cylinder_with_gas', 'Cilindro con oxigeno'),
    ], string='Modalidad de venta', copy=False)
    gas_can_select = fields.Boolean(
        string='Puede seleccionar gases',
        compute='_compute_gas_can_select',
    )
    @api.constrains('gas_sale_cylinder_id', 'gas_sale_source_line_id',
                    'gas_sale_mode', 'product_id', 'order_id', 'product_uom_qty')
    def _check_gas_sale_reference(self):
        for line in self:
            cylinder = line.gas_sale_cylinder_id
            if not cylinder:
                if line.gas_sale_source_line_id or line.gas_sale_mode:
                    raise ValidationError(_('La linea requiere un cilindro fisico.'))
                continue
            if line.display_type:
                raise ValidationError(_('La referencia del cilindro requiere una linea de producto.'))
            if cylinder.company_id != line.order_id.company_id:
                raise ValidationError(_('El cilindro pertenece a otra empresa.'))
            if cylinder.ownership_type != 'own' or not cylinder.active:
                raise ValidationError(_('El cilindro debe estar activo y ser propio.'))
            product_type = line.product_id.product_tmpl_id.gas_product_type
            if product_type == 'gas':
                if line.product_id not in cylinder.allowed_gas_product_ids:
                    raise ValidationError(_('El gas no es compatible con el cilindro.'))
                if not line.gas_sale_mode:
                    raise ValidationError(_('Indique la modalidad de venta.'))
                if line.gas_sale_mode == 'gas_only' and line.gas_sale_source_line_id:
                    raise ValidationError(_('Una venta solo de gas no debe vincular una linea de cilindro.'))
                if line.gas_sale_mode == 'cylinder_with_gas':
                    source = line.gas_sale_source_line_id
                    if (not source or source == line or
                            source.order_id != line.order_id or
                            source.product_id != cylinder.product_id or
                            source.gas_sale_cylinder_id != cylinder or
                            source.gas_sale_mode != 'cylinder_with_gas'):
                        raise ValidationError(_('La linea de gas no corresponde al cilindro vendido.'))
            elif product_type == 'cylinder':
                if (line.product_id != cylinder.product_id or
                        line.gas_sale_mode != 'cylinder_with_gas' or
                        line.gas_sale_source_line_id):
                    raise ValidationError(_('La linea de cilindro vendido no es valida.'))
                if line.product_uom_qty != 1:
                    raise ValidationError(_('Cada cilindro por serie debe venderse en una linea de una unidad.'))
            else:
                raise ValidationError(_('La referencia solo admite productos gas o cilindro.'))

    def action_select_gas(self):
        self.ensure_one()
        if not self.gas_can_select:
            raise UserError(_(
                'Este producto no tiene cilindros físicos propios '
                'y activos registrados en la empresa.'
            ))
        if self.order_id.state not in ('draft', 'sent'):
            raise UserError(_(
                'Solo se pueden configurar gases '
                'en cotizaciones sin confirmar.'
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

        return {
            'type': 'ir.actions.act_window',
            'name': _('Seleccionar gases para venta'),
            'res_model': 'gas.sale.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.order_id.id,
                'default_sale_line_id': self.id,
                'default_cylinder_product_id': self.product_id.id,
            },
        }

    @api.depends('product_id', 'order_id.state', 'display_type')
    def _compute_gas_can_select(self):
        Cylinder = self.env['gas.cylinder']

        for line in self:
            line.gas_can_select = False

            if (
                    not line.product_id
                    or line.display_type
                    or line.order_id.state not in ('draft', 'sent')
                    or line.product_id.product_tmpl_id.gas_product_type
                    != 'cylinder'
            ):
                continue

            company = line.order_id.company_id or self.env.company

            line.gas_can_select = bool(Cylinder.search_count([
                ('product_id', '=', line.product_id.id),
                ('company_id', '=', company.id),
                ('ownership_type', '=', 'own'),
                ('active', '=', True),
            ], limit=1))

    def _prepare_procurement_values(self, group_id=False):
        self.ensure_one()

        values = super()._prepare_procurement_values(
            group_id=group_id
        )

        if (
                self.gas_sale_cylinder_id
                and self.product_id.product_tmpl_id.gas_product_type
                in ('gas', 'cylinder')
        ):
            values['gas_sale_cylinder_id'] = (
                self.gas_sale_cylinder_id.id
            )

        return values

