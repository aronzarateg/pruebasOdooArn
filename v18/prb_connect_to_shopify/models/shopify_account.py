from urllib.parse import urlencode

from odoo import _, models, fields
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)

class ShopifyAccount(models.Model):
    _name = "shopify.account"
    _description = "Cuenta Shopify"
    active = fields.Boolean(
        string="Activo",
        default=True,
    )

    image_1920 = fields.Image(
        string="Logo",
    )
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
    order_limit = fields.Integer(
        string="Límite de órdenes",
        default=50,
    )

    last_order_sync = fields.Datetime(
        string="Última consulta de órdenes",
        readonly=True,
    )

    def action_connect_shopify(self):
        self.ensure_one()

        if not self.active:
            raise UserError(
                _("La cuenta Shopify está inactiva. Actívela antes de conectarla.")
            )

        shop = (
            self.shop
            .replace("https://", "")
            .replace("http://", "")
            .strip("/")
        )

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

        if not self.active:
            raise UserError(
                _("La cuenta Shopify está inactiva.")
            )

        data = self.env["shopify.service"].get(self, "/shop.json")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Shopify conectado"),
                "message": _("Tienda: %s") % data.get("shop", {}).get("name"),
                "type": "success",
                "sticky": False,
            },
        }


    #obtener ordenes
    def _check_shopify_connection(self):
        self.ensure_one()

        if not self.active:
            raise UserError(
                _("La cuenta Shopify está inactiva.")
            )

        if self.state != "connected":
            raise UserError(
                _("La cuenta Shopify no está conectada.")
            )

        if not self.access_token:
            raise UserError(
                _("La cuenta Shopify no tiene Access Token.")
            )

        granted_scopes = {
            scope.strip()
            for scope in (self.scopes or "").split(",")
            if scope.strip()
        }

        if not {"read_orders", "write_orders"} & granted_scopes:
            raise UserError(
                _(
                    "La cuenta no tiene permiso para consultar órdenes.\n\n"
                    "Se requiere read_orders o write_orders."
                )
            )

        return True

    def action_get_shopify_orders(self):
        self.ensure_one()
        self._check_shopify_connection()

        limit = self.order_limit or 50

        if limit < 1:
            raise UserError(
                _("El límite debe ser mayor que cero.")
            )

        if limit > 250:
            raise UserError(
                _("El límite máximo permitido es 250.")
            )

        query = """
               query GetOrders($first: Int!) {
                   orders(first: $first, sortKey: CREATED_AT, reverse: true) {
                       nodes {
                           id
                           legacyResourceId
                           name
                           createdAt
                           updatedAt
                           displayFinancialStatus
                           displayFulfillmentStatus
                           email
                           totalPriceSet {
                               shopMoney {
                                   amount
                                   currencyCode
                               }
                           }
                           customer {
                               id
                               firstName
                               lastName
                               email
                               phone
                           }
                           shippingAddress {
                               firstName
                               lastName
                               address1
                               address2
                               city
                               province
                               zip
                               countryCodeV2
                               phone
                           }
                           lineItems(first: 100) {
                               nodes {
                                   id
                                   name
                                   sku
                                   quantity
                                   currentQuantity
                                   originalUnitPriceSet {
                                       shopMoney {
                                           amount
                                           currencyCode
                                       }
                                   }
                               }
                           }
                       }
                       pageInfo {
                           hasNextPage
                           endCursor
                       }
                   }
               }
           """

        response = self.env["shopify.service"].graphql(
            account=self,
            query=query,
            variables={
                "first": limit,
            },
        )

        errors = response.get("errors")

        if errors:
            raise UserError(
                _("Shopify devolvió errores:\n%s") % errors
            )

        orders = (
            response
            .get("data", {})
            .get("orders", {})
            .get("nodes", [])
        )
        print("orders", orders)
        raise UserError('STOOOPPPP')
        self.last_order_sync = fields.Datetime.now()

        _logger.info(
            "Shopify: se consultaron %s órdenes para la cuenta %s",
            len(orders),
            self.display_name,
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Órdenes Shopify"),
                "message": _(
                    "Se encontraron %s órdenes."
                ) % len(orders),
                "type": "success",
                "sticky": False,
            },
        }