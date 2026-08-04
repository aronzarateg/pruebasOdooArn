import json

from odoo import fields, models
import logging


_logger = logging.getLogger(__name__)

class ShopifyNotification(models.Model):
    _name = "shopify.notification"
    _description = "Notificación Shopify"
    _order = "create_date desc"

    account_id = fields.Many2one(
        "shopify.account",
        string="Cuenta Shopify",
        ondelete="cascade",
        index=True,
    )

    webhook_id = fields.Char(
        string="Webhook ID",
        index=True,
        readonly=True,
    )
    topic = fields.Char(
        string="Tópico",
        index=True,
        readonly=True,
    )
    shop_domain = fields.Char(
        string="Tienda",
        index=True,
        readonly=True,
    )
    api_version = fields.Char(
        string="Versión API",
        readonly=True,
    )

    state = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("processing", "Procesando"),
            ("done", "Procesado"),
            ("error", "Error"),
            ("ignored", "Ignorado"),
        ],
        default="pending",
        required=True,
        index=True,
    )

    processing_attempts = fields.Integer(
        string="Intentos de procesamiento",
        default=0,
    )
    received_at = fields.Datetime(
        string="Recibido",
        default=fields.Datetime.now,
        readonly=True,
    )
    processed_at = fields.Datetime(
        string="Procesado",
        readonly=True,
    )
    error_message = fields.Text(
        string="Error",
        readonly=True,
    )
    payload = fields.Text(
        string="Payload",
        readonly=True,
    )

    _sql_constraints = [
        (
            "shopify_webhook_id_unique",
            "unique(webhook_id)",
            "Esta notificación Shopify ya fue registrada.",
        ),
    ]

    def cron_process_notifications(self, limit=50):
        notifications = self.sudo().search(
            [
                ("state", "in", ["pending", "error"]),
                ("processing_attempts", "<", 5),
            ],
            limit=limit,
            order="create_date asc, id asc",
        )

        for notification in notifications:
            try:
                with self.env.cr.savepoint():
                    notification.write({
                        "state": "processing",
                        "processing_attempts": (
                                notification.processing_attempts + 1
                        ),
                        "error_message": False,
                    })

                    result_state = (
                        notification._process_notification()
                    )

                    notification.write({
                        "state": result_state,
                        "processed_at": fields.Datetime.now(),
                        "error_message": False,
                    })

            except Exception as error:
                _logger.exception(
                    "Error procesando webhook Shopify %s, tópico %s",
                    notification.webhook_id,
                    notification.topic,
                )

                notification.write({
                    "state": "error",
                    "error_message": str(error),
                })

        return True

    def _process_notification(self):
        self.ensure_one()

        if not self.account_id:
            raise ValueError(
                "La notificación no tiene una cuenta Shopify."
            )

        payload = json.loads(self.payload or "{}")

        if self.topic in (
                "orders/create",
                "orders/updated",
                "orders/paid",
                "orders/cancelled",
                "orders/fulfilled",
        ):
            self._process_order(payload)
            return "done"

        if self.topic == "inventory_levels/update":
            self._process_inventory_level(payload)
            return "done"

        if self.topic in (
                "products/create",
                "products/update",
                "products/delete",
        ):
            self._process_product(payload)
            return "done"

        if self.topic == "app/uninstalled":
            self._process_app_uninstalled()
            return "done"

        return "ignored"

    def _process_order(self, payload):
        self.ensure_one()

        shopify_order_id = str(payload.get("id") or "")

        if not shopify_order_id:
            raise ValueError(
                "El webhook de orden no contiene el campo id."
            )

        return self.env[
            "shopify.order"
        ].sudo().create_or_update_from_shopify(
            self.account_id,
            payload,
        )
    