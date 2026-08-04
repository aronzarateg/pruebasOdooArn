from odoo import models, fields, _
from odoo.exceptions import UserError
from urllib.parse import urlencode
import logging
from datetime import timedelta

_logger = logging.getLogger(__name__)


class MeliAccount(models.Model):
    _name = "meli.account"
    _description = "Cuenta Mercado Libre"
    _order = "active desc, name"

    name = fields.Char(required=True)

    active = fields.Boolean(string="Activo", default=True,
                            help="Permite activar o desactivar esta cuenta de Mercado Libre.", )

    image_1920 = fields.Image(string="Logo", max_width=1920, max_height=1920, )
    client_id = fields.Char(string="Client ID / App ID", required=True, help="Client ID / App ID")
    client_secret = fields.Char(required=True, string="Client Secret", help="Client Secret")
    redirect_uri = fields.Char(required=True, string="Redirect URIs", help="Redirect URI")

    access_token = fields.Char(readonly=True)
    refresh_token = fields.Char(readonly=True)
    token_type = fields.Char(
        string="Tipo de token",
        readonly=True,
        copy=False,
    )
    token_scope = fields.Text(
        string="Alcances del token",
        readonly=True,
        copy=False,
    )
    meli_user_id = fields.Char(readonly=True)
    token_expires_in = fields.Integer(readonly=True)
    token_expiration_date = fields.Datetime(string="Fecha de expiración del token", readonly=True, )
    token_last_update = fields.Datetime(string="Última actualización del token", readonly=True, copy=False, )
    token_response = fields.Json(
        string="Respuesta OAuth",
        readonly=True,
        copy=False,
        groups="base.group_system",
    )
    site_id = fields.Selection([
        ("MPE", "Perú"),
        ("MLA", "Argentina"),
        ("MLB", "Brasil"),
        ("MLC", "Chile"),
        ("MCO", "Colombia"),
        ("MLM", "México"),
    ], string="Site MELI", default="MPE", required=True)
    last_order_sync = fields.Datetime(
        string="Última sincronización de órdenes",
        readonly=True,
        copy=False,
    )

    def _check_active_account(self):
        self.ensure_one()

        if not self.active:
            raise UserError(
                _(
                    "La cuenta de Mercado Libre '%s' se encuentra inactiva."
                )
                % self.display_name
            )

    def action_connect_meli(self):
        self.ensure_one()
        self._check_active_account()

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "state": str(self.id),
        }

        url = "https://auth.mercadolibre.com.pe/authorization?" + urlencode(params)

        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }

    def action_test_connection(self):
        self.ensure_one()
        self._check_active_account()

        data = self.env["meli.service"].get(self, "/users/me")

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

    def action_sync_orders(self):

        self.ensure_one()
        self._check_active_account()

        result = self._sync_orders()

        total = result.get("total_processed", 0)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Mercado Libre",
                "message": (
                    f"Órdenes sincronizadas correctamente. "
                    f"Registros procesados: {total}"
                ),
                "type": "success",
                "sticky": False,
            },
        }

    def _sync_orders(self, date_from=None, date_to=None):
        self.ensure_one()
        self._check_active_account()

        return self.env["meli.order.service"].sync_orders(
            account=self,
            date_from=date_from,
            date_to=date_to,
        )

    def _cron_sync_orders(self):
        accounts = self.search([
            ("active", "=", True),
            ("access_token", "!=", False),
            ("meli_user_id", "!=", False),
        ])
        print("accounts", accounts)
        for account in accounts:
            try:
                with self.env.cr.savepoint():
                    account._sync_orders()

            except Exception:
                _logger.exception(
                    "Error sincronizando órdenes para la cuenta %s",
                    account.display_name,
                )

        return True

    # CRONS
    def cron_refresh_tokens(self):
        renewal_limit = (
                fields.Datetime.now() + timedelta(minutes=90)
        )
        accounts = self.sudo().search([
            ("active", "=", True),
            ("refresh_token", "!=", False),
            "|",
            ("token_expiration_date", "=", False),
            ("token_expiration_date", "<=", renewal_limit),
        ])
        print("accounts", accounts)
        service = self.env["meli.service"]
        for account in accounts:
            try:
                with self.env.cr.savepoint():
                    service.refresh_token(account)
            except Exception:
                _logger.exception(
                    "Error renovando token de Mercado Libre "
                    "para la cuenta %s",
                    account.display_name,
                )
        return True

    '''
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
    def action_sync_meli_categories(self):
        self.ensure_one()

        result = self.env["meli.category.service"].sync_categories(self)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Mercado Libre",
                "message": "Categorías sincronizadas. Creadas: %s | Actualizadas: %s" % (
                    result.get("created", 0),
                    result.get("updated", 0),
                ),
                "type": "success",
                "sticky": False,
            },
        }

    def action_sync_meli_category_attributes(self):
        self.ensure_one()

        result = self.env["meli.category.service"].sync_all_category_attributes(
            self,
            limit=50,
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Mercado Libre",
                "message": "Categorías procesadas: %s | Atributos sincronizados: %s" % (
                    result.get("categories", 0),
                    result.get("attributes", 0),
                ),
                "type": "success",
                "sticky": False,
            },
        }

    
    def action_sync_meli_brands(self):
        self.ensure_one()

        result = self.env["meli.category.service"].sync_all_brands(
            self,
            limit=50,
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Mercado Libre",
                "message": "Categorías procesadas: %s | Marcas sincronizadas: %s" % (
                    result.get("categories", 0),
                    result.get("brands", 0),
                ),
                "type": "success",
                "sticky": False,
            },
        }
    
    def cron_sync_meli_category_attributes(self):
        accounts = self.sudo().search([
            ("access_token", "!=", False),
        ])

        for account in accounts:
            self.env["meli.category.service"].sync_all_category_attributes(
                account,
                limit=30,
            )

    def cron_sync_meli_brands(self):
        accounts = self.sudo().search([
            ("access_token", "!=", False),
        ])

        for account in accounts:
            self.env["meli.category.service"].sync_all_brands(
                account,
                limit=30,
            )
    '''
