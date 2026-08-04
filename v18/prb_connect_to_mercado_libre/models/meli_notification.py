from odoo import models, fields

import logging

_logger = logging.getLogger(__name__)


class MeliNotification(models.Model):
    _name = "meli.notification"
    _description = "Notificación Mercado Libre"
    _order = "create_date desc"

    topic = fields.Char(index=True)
    resource = fields.Char(index=True)
    user_id = fields.Char(index=True)
    application_id = fields.Char(index=True)

    delivery_attempts = fields.Integer(
        string="Intentos Mercado Libre",
    )
    processing_attempts = fields.Integer(
        string="Intentos de procesamiento",
        default=0,
    )

    sent = fields.Datetime()
    received = fields.Datetime(
        default=fields.Datetime.now,
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

    processed = fields.Boolean(
        default=False,
        readonly=True,
    )
    processed_at = fields.Datetime(readonly=True)

    error_message = fields.Text(readonly=True)
    payload = fields.Text(readonly=True)

    def cron_process_notifications(self, limit=50):
        notifications = self.sudo().search(
            [
                ("processed", "=", False),
            ],
            limit=limit,
            order="create_date asc, id asc",
        )

        for notif in notifications:
            try:
                with self.env.cr.savepoint():
                    account = self.env["meli.account"].sudo().search([
                        ("meli_user_id", "=", notif.user_id),
                        ("active", "=", True),
                    ], limit=1)

                    if not account:
                        raise ValueError(
                            "No se encontró una cuenta activa para "
                            "MELI user_id %s."
                            % notif.user_id
                        )

                    if notif.topic in ("orders", "orders_v2"):
                        order_data = self.env["meli.service"].get(
                            account,
                            notif.resource,
                        )

                        self.env[
                            "meli.order"
                        ].sudo().create_or_update_from_meli(
                            account,
                            order_data,
                        )

                    notif.write({
                        "processed": True,
                        "processed_at": fields.Datetime.now(),
                    })

            except Exception:
                _logger.exception(
                    "Error procesando notificación MELI %s",
                    notif.id,
                )

        return True

    def _process_notification(self):
        self.ensure_one()

        account = self.env["meli.account"].sudo().search([
            ("meli_user_id", "=", self.user_id),
            ("active", "=", True),
        ], limit=1)

        if not account:
            raise ValueError(
                "No existe una cuenta activa para MELI user_id %s."
                % self.user_id
            )

        if self.topic in ("orders", "orders_v2"):
            self._process_order_notification(account)
            return "done"

        if self.topic == "items":
            self._process_item_notification(account)
            return "done"

        if self.topic in ("shipments", "shipments_v2"):
            self._process_shipment_notification(account)
            return "done"

        return "ignored"

    def _process_order_notification(self, account):
        self.ensure_one()

        order_data = self.env["meli.service"].get(
            account,
            self.resource,
        )

        if not order_data:
            raise ValueError(
                "Mercado Libre no devolvió información para %s."
                % self.resource
            )

        return self.env[
            "meli.order"
        ].sudo().create_or_update_from_meli(
            account,
            order_data,
        )
