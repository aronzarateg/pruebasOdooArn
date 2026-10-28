from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class GasOperationConfig(models.Model):
    _name = 'gas.cylinder.operation.config'
    _description = 'Gas Operation Logistics Configuration'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    warehouse_id = fields.Many2one('stock.warehouse', required=True)
    operation_type = fields.Selection([
        ('supplier_refill', 'Supplier refill'), ('customer_refill', 'Customer refill'),
        ('sale', 'Sale'), ('rental_out', 'Rental out'), ('rental_return', 'Rental return'),
        ('recovery', 'Recovery'), ('transfer', 'Transfer'), ('adjustment', 'Adjustment')], required=True)
    picking_type_id = fields.Many2one('stock.picking.type', required=True)
    location_src_id = fields.Many2one('stock.location', required=True)
    location_dest_id = fields.Many2one('stock.location', required=True)
    return_picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Tipo de transferencia de retorno',
    )

    return_location_src_id = fields.Many2one(
        'stock.location',
        string='Ubicación origen del retorno',
    )

    return_location_dest_id = fields.Many2one(
        'stock.location',
        string='Ubicación destino del retorno',
    )

    @api.constrains('location_src_id', 'location_dest_id', 'warehouse_id', 'company_id', 'picking_type_id')
    def _check_configuration(self):
        for rec in self:
            if rec.location_src_id == rec.location_dest_id:
                raise ValidationError(_('Source and destination must be different.'))
            if rec.warehouse_id.company_id != rec.company_id:
                raise ValidationError(_('Warehouse company must match.'))
            for location in (rec.location_src_id, rec.location_dest_id):
                if location.company_id and location.company_id != rec.company_id:
                    raise ValidationError(_('Location belongs to a different company.'))
            if rec.picking_type_id.company_id and rec.picking_type_id.company_id != rec.company_id:
                raise ValidationError(_('Operation type belongs to a different company.'))
