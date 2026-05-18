import json
from odoo import models, fields


class MeliProduct(models.Model):
    _name = "meli.product"
    _description = "Producto Mercado Libre"
    _rec_name = "meli_item_id"

    product_id = fields.Many2one("product.product")
    account_id = fields.Many2one("meli.account")

    meli_item_id = fields.Char(index=True)
    title = fields.Char()
    status = fields.Char()
    price = fields.Float()
    available_quantity = fields.Integer()
    permalink = fields.Char()
    raw_data = fields.Text()

    last_sync = fields.Datetime()
    sync_error = fields.Text()

    def create_or_update_from_meli(self, account, data):
        item_id = data.get("id")

        vals = {
            "account_id": account.id,
            "meli_item_id": item_id,
            "title": data.get("title"),
            "status": data.get("status"),
            "price": data.get("price") or 0.0,
            "available_quantity": data.get("available_quantity") or 0,
            "permalink": data.get("permalink"),
            "raw_data": json.dumps(data, indent=2),
            "last_sync": fields.Datetime.now(),
        }

        item = self.search([
            ("meli_item_id", "=", item_id),
            ("account_id", "=", account.id),
        ], limit=1)

        if item:
            item.write(vals)
            return item

        return self.create(vals)