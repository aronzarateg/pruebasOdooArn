from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class GasOperationLine(models.Model):
    _name = 'gas.cylinder.operation.line'
    _description = 'Gas Cylinder Operation Line'

    operation_id = fields.Many2one('gas.cylinder.operation', required=True, ondelete='cascade')
    cylinder_id = fields.Many2one('gas.cylinder', required=True)
    gas_product_id = fields.Many2one('product.product', required=True)
    quantity = fields.Float(string='Planned Gas (m3)', digits=(16, 3), required=True)
    lot_supplier = fields.Char(string='Supplier Lot Number', copy=False)
    code_supplier = fields.Char(string='Supplier Code', copy=False)
    company_id = fields.Many2one('res.company', related='operation_id.company_id', store=True)
    quantity_received = fields.Float(
        string='Gas recibido (m³)',
        digits=(16, 3),
        copy=False,
        default=0.0,
    )
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
