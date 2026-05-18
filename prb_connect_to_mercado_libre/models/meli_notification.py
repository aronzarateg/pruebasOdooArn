from odoo import models, fields


class MeliNotification(models.Model):
    _name = "meli.notification"
    _description = "Notificación Mercado Libre"
    _order = "create_date desc"

    topic = fields.Char()
    resource = fields.Char()
    user_id = fields.Char()
    application_id = fields.Char()
    attempts = fields.Integer()
    sent = fields.Datetime()
    received = fields.Datetime(default=fields.Datetime.now)
    processed = fields.Boolean(default=False)
    payload = fields.Text()

    def cron_process_notifications(self):
        notifications = self.search([("processed", "=", False)], limit=50)

        for notif in notifications:
            account = self.env["meli.account"].search([
                ("meli_user_id", "=", notif.user_id)
            ], limit=1)

            if not account:
                continue

            if notif.topic == "orders_v2":
                order_data = self.env["meli.service"].get(account, notif.resource)
                self.env["meli.order"].create_or_update_from_meli(account, order_data)

            notif.processed = True