from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    gas_product_type = fields.Selection(
        [('none', 'Not managed'), ('cylinder', 'Cylinder'), ('gas', 'Gas')],
        string='Gas Management Type', default='none', required=True, copy=False,
    )
    cylinder_capacity = fields.Float(
        string='Default Cylinder Capacity (m3)', digits=(16, 3), copy=False,
    )

    @api.constrains('gas_product_type', 'cylinder_capacity', 'tracking', 'uom_id')
    def _check_gas_classification(self):
        for record in self:
            if record.gas_product_type == 'cylinder':
                if record.tracking != 'serial':
                    raise ValidationError(_('Cylinder products must use serial tracking.'))
                if record.cylinder_capacity <= 0:
                    raise ValidationError(_('Cylinder capacity must be greater than zero.'))
                if record.uom_id.category_id != self.env.ref('uom.product_uom_categ_unit'):
                    raise ValidationError(_('Cylinder products must use the Units UoM category.'))
            elif record.gas_product_type == 'gas':
                if record.tracking != 'none':
                    raise ValidationError(_('Gas products must have no lot/serial tracking.'))
                # Exact m3 UoM is configured by the administrator; avoid assuming XML IDs.
