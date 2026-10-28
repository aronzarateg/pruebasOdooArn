from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class GasCylinderContent(models.Model):
    _name = 'gas.cylinder.content'
    _description = 'Cylinder Gas Content (Ledger Projection)'
    _rec_name = 'cylinder_id'
    _order = 'cylinder_id, id'

    cylinder_id = fields.Many2one('gas.cylinder', required=True, ondelete='restrict', index=True)
    gas_product_id = fields.Many2one('product.product', required=True, ondelete='restrict')
    company_id = fields.Many2one('res.company', related='cylinder_id.company_id', store=True, readonly=True)
    quantity = fields.Float(string='Physical Quantity (m3)', digits=(16, 3), default=0, readonly=True)
    available_quantity = fields.Float(string='Recognized Available (m3)', digits=(16, 3), default=0, readonly=True)
    uom_id = fields.Many2one('uom.uom', related='gas_product_id.uom_id', readonly=True)
    _sql_constraints = [
        ('cylinder_gas_unique', 'unique(cylinder_id, gas_product_id)', 'Only one balance per gas and cylinder is allowed.'),
        ('nonnegative_content', 'CHECK(quantity >= 0 AND available_quantity >= 0 AND available_quantity <= quantity)', 'Invalid content balance.'),
    ]

    @api.constrains('gas_product_id', 'cylinder_id')
    def _check_product(self):
        for rec in self:
            if rec.gas_product_id.product_tmpl_id.gas_product_type != 'gas':
                raise ValidationError(_('Select a product classified as Gas.'))

    def write(self, vals):
        protected = {'quantity', 'available_quantity'}

        if protected.intersection(vals):
            if not self.env.context.get('gas_content_posting'):
                raise ValidationError(_(
                    'Los saldos de gas solo pueden modificarse '
                    'mediante contabilización autorizada.'
                ))

        return super().write(vals)