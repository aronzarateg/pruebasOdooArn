from odoo import models, fields
from urllib.parse import urlencode


class ShopifyAccount(models.Model):
    _name = "shopify.account"
    _description = "Cuenta Shopify"

    name = fields.Char(required=True)
    shop = fields.Char(
        string="Shop URL",
        required=True,
        help="Ejemplo: odoo-test-store-gluyislg.myshopify.com",
    )
    client_id = fields.Char(string="Client ID / API Key", required=True)
    client_secret = fields.Char(required=True)
    redirect_uri = fields.Char(required=True)

    access_token = fields.Char(readonly=True)
    scopes = fields.Char(readonly=True)

    state = fields.Selection([
        ("draft", "No conectado"),
        ("connected", "Conectado"),
    ], default="draft", readonly=True)

    def action_connect_shopify(self):
        self.ensure_one()

        shop = self.shop.replace("https://", "").replace("http://", "").strip("/")

        params = {
            "client_id": self.client_id,
            "scope": (
                "read_customers,write_customers,"
                "read_fulfillments,write_fulfillments,"
                "read_inventory,write_inventory,"
                "read_orders,write_orders,"
                "read_products,write_products"
            ),
            "redirect_uri": self.redirect_uri,
            "state": str(self.id),
        }

        url = "https://%s/admin/oauth/authorize?%s" % (
            shop,
            urlencode(params),
        )

        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }

    def action_test_connection(self):
        self.ensure_one()

        data = self.env["shopify.service"].get(self, "/shop.json")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Shopify conectado",
                "message": "Tienda: %s" % data.get("shop", {}).get("name"),
                "type": "success",
                "sticky": False,
            },
        }