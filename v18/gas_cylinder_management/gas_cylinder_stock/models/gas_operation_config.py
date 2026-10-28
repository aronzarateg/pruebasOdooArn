from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class GasOperationConfig(models.Model):
    _name = 'gas.cylinder.operation.config'
    _description = 'Gas Operation Logistics Configuration'

    name = fields.Char(required=True, string="Nombre de configuración")
    active = fields.Boolean(default=True, string="Activo")
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company,string="Empresa")
    warehouse_id = fields.Many2one('stock.warehouse', required=True, string="Almacén")
    operation_type = fields.Selection([
        ('supplier_refill','Reposición por parte del proveedor'),
        ('customer_refill','Recarga para el cliente'),
        ('sale', 'Venta'),
        ('rental_out', 'En alquiler'),
        ('rental_return', 'Devolución de alquiler'),
        ('recovery', 'Recuperación'),
        ('transfer', 'Transferir'),
        ('adjustment', 'Ajuste')
    ], required=True,string="Tipo de operación")
    picking_type_id = fields.Many2one('stock.picking.type', required=True, string="Tipo de transferencia")
    location_src_id = fields.Many2one('stock.location', required=True,string="Ubicación de origen")
    location_dest_id = fields.Many2one('stock.location', required=True,string="Ubicación de destino")
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

    @api.constrains(
        'operation_type',
        'return_picking_type_id',
        'return_location_src_id',
        'return_location_dest_id',
        'company_id',
    )
    def _check_return_configuration(self):
        for rec in self:
            if rec.operation_type != 'supplier_refill':
                continue

            picking_type = rec.return_picking_type_id
            source = rec.return_location_src_id
            destination = rec.return_location_dest_id

            if not picking_type or not source or not destination:
                raise ValidationError(_(
                    'Configure el tipo de transferencia y las '
                    'ubicaciones de origen y destino del retorno.'
                ))

            if picking_type.code != 'internal':
                raise ValidationError(_(
                    'El retorno de cilindros del proveedor '
                    'debe utilizar un traslado interno.'
                ))

            if source == destination:
                raise ValidationError(_(
                    'Las ubicaciones de origen y destino '
                    'del retorno deben ser diferentes.'
                ))

            if source.usage != 'internal' or destination.usage != 'internal':
                raise ValidationError(_(
                    'Las ubicaciones del retorno deben ser internas.'
                ))

            if (
                    picking_type.company_id
                    and picking_type.company_id != rec.company_id
            ):
                raise ValidationError(_(
                    'El tipo de transferencia de retorno '
                    'pertenece a otra compañía.'
                ))

            for location in (source, destination):
                if (
                        location.company_id
                        and location.company_id != rec.company_id
                ):
                    raise ValidationError(_(
                        'Una ubicación del retorno pertenece '
                        'a otra compañía.'
                    ))