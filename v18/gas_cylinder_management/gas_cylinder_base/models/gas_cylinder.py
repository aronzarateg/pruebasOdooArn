from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class GasCylinder(models.Model):
    _name = 'gas.cylinder'
    _description = 'Physical Gas Cylinder'
    _order = 'id desc'
    _rec_name = 'serial_number'

    active = fields.Boolean(default=True)
    serial_number = fields.Char(string='Physical Serial', required=True, index=True)
    product_id = fields.Many2one('product.product', string='Cylinder Product', required=True, ondelete='restrict')
    lot_id = fields.Many2one('stock.lot', string='Odoo Serial/Lot', ondelete='restrict', copy=False)
    ownership_type = fields.Selection(
        [('own', 'Company-owned'), ('third_party', 'Third-party owned')],
        required=True, default='own', string='Ownership',
    )
    owner_id = fields.Many2one('res.partner', string='External Owner', ondelete='restrict')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    capacity = fields.Float(string='Capacity (m3)', digits=(16, 3), required=True)
    notes = fields.Text()

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id and self.product_id.product_tmpl_id.gas_product_type == 'cylinder':
            self.capacity = self.product_id.product_tmpl_id.cylinder_capacity

    @api.onchange('lot_id')
    def _onchange_lot_id(self):
        if self.lot_id:
            self.serial_number = self.lot_id.name
            self.product_id = self.lot_id.product_id

    @api.constrains('capacity', 'product_id', 'lot_id', 'serial_number', 'ownership_type', 'owner_id', 'company_id')
    def _check_cylinder(self):
        for rec in self:
            if rec.capacity <= 0:
                raise ValidationError(_('Cylinder capacity must be positive.'))
            if rec.product_id.product_tmpl_id.gas_product_type != 'cylinder':
                raise ValidationError(_('The selected product must be classified as Cylinder.'))
            if rec.product_id.tracking != 'serial':
                raise ValidationError(_('The cylinder product must use serial tracking.'))
            if rec.ownership_type == 'own' and not rec.lot_id:
                raise ValidationError(_('Company-owned cylinders require an Odoo serial/lot.'))
            if rec.ownership_type == 'third_party' and not rec.owner_id:
                raise ValidationError(_('Third-party cylinders require an external owner.'))
            if rec.lot_id:
                #if rec.lot_id.product_id != rec.product_id or rec.lot_id.company_id != rec.company_id:
                if rec.lot_id.product_id != rec.product_id:
                    raise ValidationError(_('Lot product and company must match the cylinder.'))
                if rec.serial_number != rec.lot_id.name:
                    raise ValidationError(_('Physical serial must match the Odoo serial.'))
                if self.search_count([('id', '!=', rec.id), ('lot_id', '=', rec.lot_id.id)]):
                    raise ValidationError(_('This Odoo serial is already linked to another cylinder.'))
            if self.search_count([
                ('id', '!=', rec.id), ('company_id', '=', rec.company_id.id),
                ('product_id', '=', rec.product_id.id), ('serial_number', '=', rec.serial_number),
                ('ownership_type', '=', rec.ownership_type),
                ('owner_id', '=', rec.owner_id.id if rec.ownership_type == 'third_party' else False),
            ]):
                raise ValidationError(_('Duplicate physical cylinder identity.'))
