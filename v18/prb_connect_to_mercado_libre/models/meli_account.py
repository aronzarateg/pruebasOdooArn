from odoo import models, fields
from urllib.parse import urlencode
import logging
_logger = logging.getLogger(__name__)

class MeliAccount(models.Model):
    _name = "meli.account"
    _description = "Cuenta Mercado Libre"

    name = fields.Char(required=True)
    client_id = fields.Char(string="Client ID / App ID", required=True)
    client_secret = fields.Char(required=True)
    redirect_uri = fields.Char(required=True)

    access_token = fields.Char(readonly=True)
    refresh_token = fields.Char(readonly=True)
    meli_user_id = fields.Char(readonly=True)
    token_expires_in = fields.Integer(readonly=True)

    def action_connect_meli(self):
        self.ensure_one()

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
        }

        url = "https://auth.mercadolibre.com.pe/authorization?" + urlencode(params)

        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }

    def action_test_connection(self):
        self.ensure_one()
        service = self.env["meli.service"]
        data = service.get(self, "/users/me")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Mercado Libre conectado",
                "message": f"Usuario Mercado Libre: {data.get('nickname')}",
                "type": "success",
                "sticky": False,
            },
        }

    def cron_refresh_tokens(self):

        accounts = self.search([
            ('refresh_token', '!=', False)
        ])

        service = self.env['meli.service']

        for account in accounts:
            try:
                service.refresh_token(account)
            except Exception as e:
                _logger.exception(e)

    def action_sync_orders(self):
        self.ensure_one()

        self.env["meli.order.service"].sync_orders(self)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Mercado Libre",
                "message": "Órdenes sincronizadas correctamente.",
                "type": "success",
                "sticky": False,
            },
        }

    def action_sync_items(self):
        self.ensure_one()

        data = self.env["meli.product.service"].sync_items(self)
        total = len(data.get("results", []))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Mercado Libre",
                "message": f"Items encontrados: {total}",
                "type": "success",
                "sticky": False,
            },
        }