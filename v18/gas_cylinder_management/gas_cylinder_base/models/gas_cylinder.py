from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class GasCylinder(models.Model):
    _name = 'gas.cylinder'
    _description = 'Cilindro físico de gas'
    _order = 'id desc'
    _rec_name = 'serial_number'

    active = fields.Boolean(string='Activo', default=True, )

    serial_number = fields.Char(string='Número de serie físico', index=True, )

    product_id = fields.Many2one('product.product', string='Producto del cilindro', required=True, ondelete='restrict',
                                 domain="[('product_tmpl_id.gas_product_type', '=', 'cylinder')]", )

    lot_id = fields.Many2one('stock.lot', string='Número de serie / lote de Odoo', ondelete='restrict', copy=False,
                             domain="[('product_id', '=', product_id)]", )

    ownership_type = fields.Selection(
        [
            ('own', 'Propio de la empresa'),
            ('third_party', 'Propiedad de terceros'),
        ],
        string='Tipo de propiedad', required=True, default='own', )

    owner_id = fields.Many2one('res.partner', string='Propietario externo', ondelete='restrict', )

    company_id = fields.Many2one('res.company', string='Empresa', required=True,
                                 default=lambda self: self.env.company, )

    capacity = fields.Float(string='Capacidad (m³)', digits=(16, 3), required=True, )

    notes = fields.Text(string='Observaciones')
    allowed_gas_product_ids = fields.Many2many(
        comodel_name='product.product',
        relation='gas_cylinder_allowed_gas_rel',
        column1='cylinder_id',
        column2='product_id',
        string='Gases compatibles',
        domain="[('product_tmpl_id.gas_product_type', '=', 'gas')]",
        help=(
            'Productos de gas que pueden asignarse a este cilindro. '
            'Esta configuración no representa el contenido actual '
            'ni modifica los saldos de gas.'
        ),
    )

    @api.constrains('allowed_gas_product_ids')
    def _check_allowed_gas_products(self):
        for cylinder in self:
            invalid_products = cylinder.allowed_gas_product_ids.filtered(
                lambda product:
                product.product_tmpl_id.gas_product_type != 'gas'
            )

            if invalid_products:
                raise ValidationError(_(
                    'Solo se pueden asignar productos '
                    'clasificados como gas.'
                ))

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if not self.product_id:
            self.lot_id = False
            return

        if (self.product_id.product_tmpl_id.gas_product_type == 'cylinder'):
            self.capacity = (self.product_id.product_tmpl_id.cylinder_capacity)
        if (self.lot_id and self.lot_id.product_id != self.product_id):
            self.lot_id = False
            self.serial_number = False

    @api.onchange('lot_id')
    def _onchange_lot_id(self):
        if self.lot_id:
            self.serial_number = self.lot_id.name
            self.product_id = self.lot_id.product_id

    @api.constrains(
        'capacity',
        'product_id',
        'lot_id',
        'serial_number',
        'ownership_type',
        'owner_id',
        'company_id',
    )
    def _check_cylinder(self):
        for rec in self:
            if rec.capacity <= 0:
                raise ValidationError(
                    _('La capacidad del cilindro debe ser mayor que cero.')
                )

            if (
                    rec.product_id.product_tmpl_id.gas_product_type
                    != 'cylinder'
            ):
                raise ValidationError(
                    _('El producto debe estar clasificado como cilindro.')
                )

            if rec.product_id.tracking != 'serial':
                raise ValidationError(
                    _('El producto debe tener seguimiento por número de serie.')
                )

            if rec.ownership_type == 'own' and not rec.lot_id:
                raise ValidationError(
                    _('Los cilindros propios requieren un número de serie de Odoo.')
                )

            if rec.ownership_type == 'third_party' and not rec.owner_id:
                raise ValidationError(
                    _('Debe seleccionar el propietario externo.')
                )

            if rec.lot_id:
                if rec.lot_id.product_id != rec.product_id:
                    raise ValidationError(
                        _('El producto del lote no coincide con el cilindro.')
                    )

                if (
                        rec.lot_id.company_id
                        and rec.lot_id.company_id != rec.company_id
                ):
                    raise ValidationError(
                        _('La empresa del lote no coincide con la del cilindro.')
                    )

                if self.search_count([
                    ('id', '!=', rec.id),
                    ('lot_id', '=', rec.lot_id.id),
                ]):
                    raise ValidationError(
                        _('Esta serie ya está vinculada a otro cilindro.')
                    )

            if self.search_count([
                ('id', '!=', rec.id),
                ('company_id', '=', rec.company_id.id),
                ('product_id', '=', rec.product_id.id),
                ('serial_number', '=', rec.serial_number),
                ('ownership_type', '=', rec.ownership_type),
                (
                        'owner_id',
                        '=',
                        rec.owner_id.id
                        if rec.ownership_type == 'third_party'
                        else False,
                ),
            ]):
                raise ValidationError(
                    _('Ya existe un cilindro con esta identificación.')
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            lot_id = vals.get('lot_id')

            if lot_id:
                lot = self.env['stock.lot'].browse(lot_id).exists()

                if not lot:
                    raise ValidationError(
                        _('El número de serie seleccionado no existe.')
                    )

                # Sincronizar los datos del lote con el cilindro.
                vals['serial_number'] = lot.name
                vals['product_id'] = lot.product_id.id

                print(
                    '[GAS CYLINDER CREATE] '
                    f'Lote: {lot.name} | '
                    f'Serie: {vals["serial_number"]}',
                    flush=True,
                )

        return super().create(vals_list)

    def write(self, vals):
        vals = vals.copy()

        if 'lot_id' in vals:
            lot_id = vals.get('lot_id')

            if lot_id:
                lot = self.env['stock.lot'].browse(lot_id).exists()

                if not lot:
                    raise ValidationError(
                        _('El número de serie seleccionado no existe.')
                    )

                vals['serial_number'] = lot.name
                vals['product_id'] = lot.product_id.id

                print(
                    '[GAS CYLINDER WRITE] '
                    f'IDs: {self.ids} | '
                    f'Lote: {lot.name} | '
                    f'Serie: {vals["serial_number"]}',
                    flush=True,
                )

        return super().write(vals)
