import logging
import pytz
from datetime import timedelta
from urllib.parse import urlencode
from odoo import api, _, fields, models
from odoo.exceptions import UserError
from datetime import datetime, time, timedelta

_logger = logging.getLogger(__name__)


class ShopifyAccount(models.Model):
    _name = "shopify.account"
    _description = "Cuenta Shopify"
    active = fields.Boolean(string="Activo", default=True)
    image_1920 = fields.Image(string="Logo")
    name = fields.Char(required=True)
    shop = fields.Char(string="Shop URL", required=True, help="Ejemplo: odoo-test-store-gluyislg.myshopify.com")
    client_id = fields.Char(string="Client ID / API Key", required=True)
    client_secret = fields.Char(required=True)
    redirect_uri = fields.Char(required=True)
    access_token = fields.Char(string="Access Token")
    refresh_token = fields.Char(string="Refresh Token")
    scopes = fields.Char(string="Scopes autorizados")
    token_expires_in = fields.Integer(string="Duración Access Token")
    token_expiration_date = fields.Datetime(string="Expiración Access Token")
    refresh_token_expiration_date = fields.Datetime(string="Expiración Refresh Token")
    last_token_refresh = fields.Datetime(string="Última renovación")
    token_error = fields.Text(string="Último error de token")
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
    tienda = fields.Selection(
        [
            ("kuzler", "Kuzler"),
            ("dudu", "Dudu"),
        ],
        required=True,
    )

    last_order_sync = fields.Datetime(string="Última consulta de órdenes")
    webhook_callback_url = fields.Char(
        string="URL de Webhooks",
        help=(
            "URL pública donde Shopify enviará las notificaciones. "
            "Ejemplo: https://dominio.com/shopify/webhooks"
        ),

    )
    webhook_last_sync = fields.Datetime(string="Última sincronización de webhooks")
    webhook_sync_message = fields.Text(string="Resultado de sincronización")

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

    # CONECCION
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
                "read_locations,"
                "read_orders,write_orders,"
                "read_products,write_products,"
                "read_assigned_fulfillment_orders,"
                "write_assigned_fulfillment_orders"
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

    def _check_shopify_connection(self):
        self.ensure_one()
        if not self.active:
            raise UserError(_("La cuenta Shopify está inactiva."))
        if self.state != "connected":
            raise UserError(_("La cuenta Shopify no está conectada."))
        if not self.access_token:
            raise UserError(_("La cuenta Shopify no tiene Access Token."))
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

    # obtener ordenes
    def action_get_shopify_orders(self):
        self.ensure_one()
        limit = 250
        if limit > 250:
            raise UserError(
                _("El límite máximo permitido para el botón es 250.")
            )
        today = fields.Date.context_today(self)
        yesterday = today - timedelta(days=1)
        orders = self._sync_shopify_orders(date_from=yesterday, date_to=yesterday, max_orders=limit, )
        print("orders:", orders)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Órdenes Shopify"),
                "message": _(
                    "Se sincronizaron %s órdenes."
                ) % len(orders),
                "type": "success",
                "sticky": False,
            },
        }

    def _get_shopify_orders_query(self):
        return """
            query GetOrders(
                $first: Int!,
                $after: String,
                $query: String!
            ) {
                orders(
                    first: $first,
                    after: $after,
                    query: $query,
                    sortKey: CREATED_AT,
                    reverse: false
                ) {
                    nodes {
                        id
                        legacyResourceId
                        name
                        createdAt
                        updatedAt
                        cancelledAt
                        displayFinancialStatus
                        displayFulfillmentStatus
                        email

                        customAttributes {
                            key
                            value
                        }

                        orderDocumentNumber: metafield(
                            namespace: "custom"
                            key: "document_number"
                        ) {
                            value
                        }

                        orderDocumentType: metafield(
                            namespace: "custom"
                            key: "document_type"
                        ) {
                            value
                        }

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

                            customerDocumentNumber: metafield(
                                namespace: "custom"
                                key: "document_number"
                            ) {
                                value
                            }

                            customerDocumentType: metafield(
                                namespace: "custom"
                                key: "document_type"
                            ) {
                                value
                            }
                        }

                        billingAddress {
                            firstName
                            lastName
                            company
                            address1
                            address2
                            city
                            province
                            provinceCode
                            zip
                            country
                            countryCodeV2
                            phone
                        }

                        shippingAddress {
                            firstName
                            lastName
                            company
                            address1
                            address2
                            city
                            province
                            provinceCode
                            zip
                            country
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

                            pageInfo {
                                hasNextPage
                                endCursor
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

    def _sync_shopify_orders(self, date_from=None, date_to=None, max_orders=None, ):
        self.ensure_one()
        self._check_shopify_connection()
        utc_date_from, utc_date_to = (self._prepare_shopify_order_date_range(date_from=date_from, date_to=date_to))

        query_filter = (
                "created_at:>='%s' created_at:<'%s'"
                % (
                    utc_date_from.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    utc_date_to.strftime("%Y-%m-%dT%H:%M:%SZ"),
                )
        )
        print("query_filter", query_filter)

        if max_orders is not None and max_orders < 1:
            raise UserError(
                _("El límite debe ser mayor que cero.")
            )

        graphql_query = self._get_shopify_orders_query()
        order_model = self.env["shopify.order"]

        cursor = None
        processed_orders = self.env["shopify.order"]
        fetched_count = 0

        while True:
            if max_orders:
                remaining = max_orders - fetched_count

                if remaining <= 0:
                    break

                page_size = min(remaining, 250)
            else:
                page_size = 250

            response = self.env["shopify.service"].graphql(
                account=self,
                query=graphql_query,
                variables={
                    "first": page_size,
                    "after": cursor,
                    "query": query_filter,
                },
            )
            errors = response.get("errors")
            if errors:
                raise UserError(
                    _("Shopify devolvió errores:\n%s") % errors
                )
            orders_data = (response.get("data", {}).get("orders", {}))
            print("orders_data", orders_data)

            orders = orders_data.get("nodes", [])
            page_info = orders_data.get("pageInfo", {})

            for order_data in orders:
                order = order_model.create_or_update_from_shopify(account=self, data=order_data)
                processed_orders |= order

            fetched_count += len(orders)

            has_next_page = page_info.get("hasNextPage")
            cursor = page_info.get("endCursor")

            if not has_next_page or not cursor:
                break

            if not orders:
                break

        self.sudo().write({
            "last_order_sync": fields.Datetime.now(),
        })

        '''
        _logger.info(
            (
                "Shopify: se sincronizaron %s órdenes para la cuenta "
                "%s. Rango UTC: %s - %s"
            ),
            len(processed_orders),
            self.display_name,
            utc_date_from,
            utc_date_to,
        )
        '''

        return processed_orders

    def _prepare_shopify_order_date_range(self, date_from=None, date_to=None):
        self.ensure_one()

        today = fields.Date.context_today(self)
        yesterday = today - timedelta(days=1)

        date_from = fields.Date.to_date(date_from) if date_from else yesterday
        date_to = fields.Date.to_date(date_to) if date_to else yesterday

        if date_from > date_to:
            raise UserError(
                _("La fecha inicial no puede ser mayor que la fecha final.")
            )

        timezone_name = self.env.user.tz or "UTC"
        timezone = pytz.timezone(timezone_name)

        local_date_from = timezone.localize(
            datetime.combine(date_from, time.min)
        )

        local_date_to_exclusive = timezone.localize(
            datetime.combine(
                date_to + timedelta(days=1),
                time.min,
            )
        )

        utc_date_from = local_date_from.astimezone(pytz.UTC)
        utc_date_to_exclusive = local_date_to_exclusive.astimezone(pytz.UTC)

        return utc_date_from, utc_date_to_exclusive

    def action_sync_webhooks(self):
        self.ensure_one()

        if not self.access_token:
            raise UserError(
                _("Primero debe conectar la cuenta Shopify.")
            )

        callback_url = (
                self.webhook_callback_url or ""
        ).strip().rstrip("/")

        if not callback_url:
            raise UserError(
                _("Debe ingresar la URL de webhooks.")
            )

        if not callback_url.startswith("https://"):
            raise UserError(
                _("La URL de webhooks debe utilizar HTTPS.")
            )

        service = self.env["shopify.service"]

        topics = [
            "ORDERS_CREATE",
            "ORDERS_UPDATED",
            "ORDERS_PAID",
            "ORDERS_CANCELLED",
            "FULFILLMENTS_CREATE",
            "FULFILLMENTS_UPDATE",
            "INVENTORY_LEVELS_UPDATE",
            "PRODUCTS_UPDATE",
            "APP_UNINSTALLED",
        ]

        existing_webhooks = service.list_webhooks(self)

        existing_by_topic = {}

        for webhook in existing_webhooks:
            topic = webhook.get("topic")

            if topic:
                existing_by_topic.setdefault(topic, []).append(webhook)

        created = []
        updated = []
        unchanged = []

        for topic in topics:
            topic_webhooks = existing_by_topic.get(topic, [])

            if not topic_webhooks:
                webhook = service.register_webhook(
                    self,
                    topic,
                    callback_url,
                )
                created.append(topic)
                continue

            # Se utiliza la primera suscripción del tópico.
            webhook = topic_webhooks[0]

            current_uri = (
                    webhook.get("uri") or ""
            ).strip().rstrip("/")

            if current_uri != callback_url:
                service.update_webhook(
                    self,
                    webhook.get("id"),
                    callback_url,
                )
                updated.append(topic)
            else:
                unchanged.append(topic)

        message = (
                "Webhooks sincronizados.\n"
                "Creados: %s\n"
                "Actualizados: %s\n"
                "Sin cambios: %s"
                % (
                    ", ".join(created) or "Ninguno",
                    ", ".join(updated) or "Ninguno",
                    ", ".join(unchanged) or "Ninguno",
                )
        )

        self.write({
            "webhook_last_sync": fields.Datetime.now(),
            "webhook_sync_message": message,
        })

        return {
            "effect": {
                "fadeout": "slow",
                "message": _("Webhooks sincronizados correctamente."),
                "type": "rainbow_man",
            }
        }

    # CRONS
    @api.model
    def cron_sync_shopify_orders(self):
        today = fields.Date.context_today(self)
        yesterday = today - timedelta(days=1)

        accounts = self.sudo().search([
            ("active", "=", True),
            ("state", "=", "connected"),
            ("access_token", "!=", False),
        ])
        print("accounts", accounts)
        for account in accounts:
            print("account", account)
            try:
                with self.env.cr.savepoint():
                    account._sync_shopify_orders(
                        date_from=yesterday, date_to=yesterday,
                        max_orders=None,
                    )

            except Exception:
                _logger.exception(
                    (
                        "Error sincronizando órdenes Shopify "
                        "para la cuenta %s"
                    ),
                    account.display_name,
                )

        return True

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
