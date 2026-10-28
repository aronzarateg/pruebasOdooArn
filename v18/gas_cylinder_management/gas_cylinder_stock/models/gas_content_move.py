from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class GasContentMove(models.Model):
    _name = 'gas.cylinder.content.move'
    _description = 'Gas Content Movement Audit Ledger'
    _order = 'id desc'

    date = fields.Datetime(default=fields.Datetime.now, required=True)
    cylinder_id = fields.Many2one('gas.cylinder', required=True, ondelete='restrict')
    gas_product_id = fields.Many2one('product.product', required=True, ondelete='restrict')
    company_id = fields.Many2one('res.company', related='cylinder_id.company_id', store=True)
    operation_id = fields.Many2one('gas.cylinder.operation', ondelete='restrict')
    stock_move_id = fields.Many2one('stock.move', ondelete='restrict')
    quantity_delta = fields.Float(string='Physical Delta (m3)', digits=(16, 3), required=True)
    available_delta = fields.Float(string='Available Delta (m3)', digits=(16, 3), required=True)
    note = fields.Char()

    @api.model_create_multi
    def create(self, vals_list):
        raise UserError(_('Ledger posting is disabled until stock integration is implemented.'))

    def write(self, vals):
        raise UserError(_('Ledger entries are immutable.'))

    def unlink(self):
        raise UserError(_('Ledger entries cannot be deleted.'))
