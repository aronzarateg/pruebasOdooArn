from odoo import models, fields
import json


class MeliOrder(models.Model):
    _name = "meli.order"
    _description = "Orden Mercado Libre"
    _rec_name = "meli_order_id"

    account_id = fields.Many2one("meli.account", string="Cuenta", required=True)
    meli_order_id = fields.Char(string="Orden ML", index=True, required=True)
    status = fields.Char(string="Estado")
    buyer_nickname = fields.Char(string="Comprador")
    total_amount = fields.Float(string="Total")
    raw_data = fields.Text(string="JSON Original")

    def create_or_update_from_meli(self, account, data):
        order_id = str(data.get("id"))

        vals = {
            "account_id": account.id,
            "meli_order_id": order_id,
            "status": data.get("status"),
            "buyer_nickname": data.get("buyer", {}).get("nickname"),
            "total_amount": data.get("total_amount") or 0.0,
            "raw_data": json.dumps(data, indent=2),
        }

        order = self.search([
            ("meli_order_id", "=", order_id),
            ("account_id", "=", account.id),
        ], limit=1)

        if order:
            order.write(vals)
            return order

        return self.create(vals)