
from odoo import models, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def action_open_gas_purchase_wizard(self):
        self.ensure_one()

        if self.state not in ('draft', 'sent'):
            raise UserError(_(
                'Solo se pueden configurar recargas '
                'en solicitudes de cotización.'
            ))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Seleccionar gases por cilindro'),
            'res_model': 'gas.purchase.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_purchase_order_id': self.id,
            },
        }
