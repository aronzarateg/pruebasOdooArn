from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class GasOperationLine(models.Model):
    _name = 'gas.cylinder.operation.line'
    _description = 'Gas Cylinder Operation Line'

    operation_id = fields.Many2one('gas.cylinder.operation', required=True, ondelete='cascade')
    cylinder_id = fields.Many2one('gas.cylinder', string="Cilindro", required=True)
    gas_product_id = fields.Many2one('product.product', string="Producto de gas", required=True)
    quantity = fields.Float(string='Gas planificado (m³)', digits=(16, 3), required=True)
    lot_supplier = fields.Char(string='Lote del proveedor', copy=False)
    code_supplier = fields.Char(string='Código del proveedor', copy=False)
    company_id = fields.Many2one('res.company', related='operation_id.company_id', store=True)
    quantity_received = fields.Float(string='Gas recibido (m³)', digits=(16, 3), copy=False, default=0.0, )
    cylinder_capacity = fields.Float(string='Capacidad máxima (m³)', compute='_compute_capacity_info', digits=(16, 3), )
    current_content = fields.Float(string='Contenido actual (m³)', compute='_compute_capacity_info', digits=(16, 3), )
    available_capacity = fields.Float(string='Espacio disponible (m³)', compute='_compute_capacity_info',
                                      digits=(16, 3), )
    is_full = fields.Boolean(string='Cilindro lleno', compute='_compute_capacity_info', )
    @api.depends('cylinder_id', 'gas_product_id')
    def _compute_capacity_info(self):
        Content = self.env['gas.cylinder.content']
        for line in self:
            line.cylinder_capacity = 0.0
            line.current_content = 0.0
            line.available_capacity = 0.0
            line.is_full = False
            if not line.cylinder_id:
                continue
            capacity = line.cylinder_id.capacity
            balances = Content.search([('cylinder_id', '=', line.cylinder_id.id), ])

            current = sum(balances.mapped('quantity'))
            line.cylinder_capacity = capacity
            line.current_content = current
            line.available_capacity = max(capacity - current, 0.0)
            line.is_full = current >= capacity - 0.001

    @api.constrains('quantity', 'cylinder_id', 'gas_product_id', 'operation_id')
    def _check_line(self):
        for rec in self:
            if rec.quantity < 0:
                raise ValidationError(_('Quantity cannot be negative.'))
            if rec.cylinder_id.company_id != rec.company_id:
                raise ValidationError(_('Cylinder and operation companies must match.'))
            if rec.gas_product_id.product_tmpl_id.gas_product_type != 'gas':
                raise ValidationError(_('Choose a gas product.'))

    @api.constrains('quantity_received')
    def _check_quantity_received(self):
        for rec in self:
            if rec.quantity_received < 0:
                raise ValidationError(
                    _('La cantidad recibida no puede ser negativa.')
                )

    @api.onchange('cylinder_id')
    def _onchange_cylinder_supplier_data(self):
        for line in self:
            cylinder = line.cylinder_id
            lot = cylinder.lot_id if cylinder else False

            line.lot_supplier = lot.lot_supplier if lot else False
            line.code_supplier = lot.code_supplier if lot else False

            print(
                '[GAS OPERATION LINE] '
                f'Cilindro: {cylinder.serial_number if cylinder else ""} | '
                f'Lote proveedor: {line.lot_supplier} | '
                f'Código proveedor: {line.code_supplier}',
                flush=True,
            )

    @api.model_create_multi
    def create(self, vals_list):
        operation_ids = {
            vals['operation_id']
            for vals in vals_list
            if vals.get('operation_id')
        }

        operations = self.env[
            'gas.cylinder.operation'
        ].browse(list(operation_ids))

        if any(op.state == 'done' for op in operations):
            raise UserError(_(
                'No se pueden agregar cilindros '
                'a una operación finalizada.'
            ))

        return super().create(vals_list)

    def write(self, vals):
        protected_fields = {
            'operation_id',
            'cylinder_id',
            'gas_product_id',
            'quantity',
            'quantity_received',
            'lot_supplier',
            'code_supplier',
        }

        if protected_fields.intersection(vals):
            if any(
                    line.operation_id.state == 'done'
                    for line in self
            ):
                raise UserError(_(
                    'No se pueden modificar los datos '
                    'de una operación finalizada.'
                ))

        return super().write(vals)

    def unlink(self):
        if any(
                line.operation_id.state == 'done'
                for line in self
        ):
            raise UserError(_(
                'No se pueden eliminar cilindros '
                'de una operación finalizada.'
            ))

        return super().unlink()
