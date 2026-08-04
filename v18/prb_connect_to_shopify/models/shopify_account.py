#from urllib.parse import urlencode

import logging
from datetime import timedelta
from urllib.parse import urlencode

from odoo import api, _, fields, models
from odoo.exceptions import UserError


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

    access_token = fields.Char(
        string="Access Token",
        readonly=True,
        copy=False,
    )
    refresh_token = fields.Char(
        string="Refresh Token",
        readonly=True,
        copy=False,
    )
    scopes = fields.Char(
        string="Scopes autorizados",
        readonly=True,
        copy=False,
    )

    token_expires_in = fields.Integer(
        string="Duración Access Token",
        readonly=True,
        copy=False,
    )
    token_expiration_date = fields.Datetime(
        string="Expiración Access Token",
        readonly=True,
        copy=False,
    )
    refresh_token_expiration_date = fields.Datetime(
        string="Expiración Refresh Token",
        readonly=True,
        copy=False,
    )
    last_token_refresh = fields.Datetime(
        string="Última renovación",
        readonly=True,
        copy=False,
    )
    token_error = fields.Text(
        string="Último error de token",
        readonly=True,
        copy=False,
    )

    state = fields.Selection(
        [
            ("draft", "No conectado"),
            ("connected", "Conectado"),
            ("reconnect", "Requiere reconexión"),
            ("error", "Error"),
        ],
        default="draft",
        readonly=True,
        copy=False,
    )

    order_limit = fields.Integer(
        string="Límite de órdenes",
        default=50,
    )

    last_order_sync = fields.Datetime(
        string="Última consulta de órdenes",
        readonly=True,
    )

    def _get_shop_domain(self):
        self.ensure_one()

        shop = (
            (self.shop or "")
            .replace("https://", "")
            .replace("http://", "")
            .strip("/")
            .lower()
        )

        if not shop:
            raise UserError(_("Debe configurar el dominio Shopify."))

        if not shop.endswith(".myshopify.com"):
            raise UserError(
                _(
                    "Debe utilizar el dominio permanente de Shopify.\n"
                    "Ejemplo: tienda.myshopify.com"
                )
            )

        return shop

    def action_connect_shopify(self):
        self.ensure_one()

        if not self.active:
            raise UserError(
                _("La cuenta Shopify está inactiva. Actívela antes de conectarla.")
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
            self._get_shop_domain(),
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

    @api.model
    def cron_refresh_tokens(self):
        renewal_limit = (
                fields.Datetime.now() + timedelta(minutes=20)
        )

        accounts = self.sudo().search([
            ("active", "=", True),
            ("state", "=", "connected"),
            ("refresh_token", "!=", False),
            "|",
            ("token_expiration_date", "=", False),
            ("token_expiration_date", "<=", renewal_limit),
        ])

        service = self.env["shopify.service"]

        for account in accounts:
            try:
                with self.env.cr.savepoint():
                    service.refresh_token(account)

            except Exception as error:
                _logger.exception(
                    "Error renovando el token Shopify para la cuenta %s",
                    account.display_name,
                )

                if account.state != "reconnect":
                    account.sudo().write({
                        "state": "error",
                        "token_error": str(error),
                    })

        return True