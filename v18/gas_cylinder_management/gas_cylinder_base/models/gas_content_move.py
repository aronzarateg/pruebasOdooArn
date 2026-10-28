from odoo import api, fields, models, _
from odoo.exceptions import UserError


class GasContentMove(models.Model):
    _name = 'gas.cylinder.content.move'
    _description = 'Gas Content Movement Audit Ledger'
    _order = 'id desc'

    date = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
    )

    cylinder_id = fields.Many2one(
        'gas.cylinder',
        required=True,
        ondelete='restrict',
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
    )

    stock_move_id = fields.Many2one(
        'stock.move',
        ondelete='restrict',
    )

    quantity_delta = fields.Float(
        string='Physical Delta (m3)',
        digits=(16, 3),
        required=True,
    )

    available_delta = fields.Float(
        string='Available Delta (m3)',
        digits=(16, 3),
        required=True,
    )

    note = fields.Char()

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('gas_content_posting'):
            raise UserError(_(
                'Los movimientos de contenido deben '
                'generarse desde una operación autorizada.'
            ))

        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_('Ledger entries are immutable.'))

    def unlink(self):
        raise UserError(_('Ledger entries cannot be deleted.'))