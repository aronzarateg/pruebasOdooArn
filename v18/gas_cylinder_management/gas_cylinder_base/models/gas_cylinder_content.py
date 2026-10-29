from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class GasCylinderContent(models.Model):
    _name = 'gas.cylinder.content'
    _description = 'Cylinder Gas Content (Ledger Projection)'
    _rec_name = 'cylinder_id'
    _order = 'cylinder_id, id'

    cylinder_id = fields.Many2one(
        'gas.cylinder',
        required=True,
        ondelete='restrict',
        index=True,
    )

    gas_product_id = fields.Many2one(
        'product.product',
        required=True,
        ondelete='restrict',
    )

    company_id = fields.Many2one(
        'res.company',
        related='cylinder_id.company_id',
        store=True,
        readonly=True,
    )

    quantity = fields.Float(
        string='Cantidad física (m³)',
        digits=(16, 3),
        default=0,
        readonly=True,
    )

    available_quantity = fields.Float(
        string='Cantidad disponible (m³)',
        digits=(16, 3),
        default=0,
        readonly=True,
    )

    uom_id = fields.Many2one(
        'uom.uom',
        related='gas_product_id.uom_id',
        readonly=True,
    )

    cylinder_capacity = fields.Float(
        string='Capacidad cilindro (m³)',
        related='cylinder_id.capacity',
        readonly=True,
    )

    cylinder_total_quantity = fields.Float(
        string='Contenido total (m³)',
        compute='_compute_cylinder_capacity_info',
        digits=(16, 3),
        readonly=True,
    )

    cylinder_free_capacity = fields.Float(
        string='Capacidad libre (m³)',
        compute='_compute_cylinder_capacity_info',
        digits=(16, 3),
        readonly=True,
    )

    cylinder_occupation_pct = fields.Float(
        string='Ocupación (%)',
        compute='_compute_cylinder_capacity_info',
        digits=(16, 2),
        readonly=True,
    )

    @api.depends(
        'quantity',
        'cylinder_id',
        'cylinder_id.capacity',
    )
    def _compute_cylinder_capacity_info(self):
        cylinder_ids = self.mapped('cylinder_id').ids

        totals = {}

        if cylinder_ids:
            self.env.cr.execute(
                """
                SELECT
                    cylinder_id,
                    COALESCE(SUM(quantity), 0)
                FROM gas_cylinder_content
                WHERE cylinder_id = ANY(%s)
                GROUP BY cylinder_id
                """,
                (cylinder_ids,),
            )

            totals = dict(self.env.cr.fetchall())

        for rec in self:
            capacity = rec.cylinder_id.capacity or 0.0
            total = totals.get(rec.cylinder_id.id, 0.0)

            rec.cylinder_total_quantity = total
            rec.cylinder_free_capacity = max(
                capacity - total,
                0.0,
            )
            rec.cylinder_occupation_pct = (
                (total / capacity) * 100.0
                if capacity > 0.0
                else 0.0
            )

    _sql_constraints = [
        (
            'cylinder_gas_unique',
            'unique(cylinder_id, gas_product_id)',
            'Only one balance per gas and cylinder is allowed.',
        ),
        (
            'nonnegative_content',
            'CHECK(quantity >= 0 '
            'AND available_quantity >= 0 '
            'AND available_quantity <= quantity)',
            'Invalid content balance.',
        ),
    ]

    @api.constrains('gas_product_id', 'cylinder_id')
    def _check_product(self):
        for rec in self:
            if (
                rec.gas_product_id.product_tmpl_id.gas_product_type
                != 'gas'
            ):
                raise ValidationError(_(
                    'Select a product classified as Gas.'
                ))

    def write(self, vals):
        protected = {
            'quantity',
            'available_quantity',
        }

        if protected.intersection(vals):
            if not self.env.context.get('gas_content_posting'):
                raise ValidationError(_(
                    'Los saldos de gas solo pueden modificarse '
                    'mediante contabilización autorizada.'
                ))

        return super().write(vals)