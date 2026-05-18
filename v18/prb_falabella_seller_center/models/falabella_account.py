# -*- coding: utf-8 -*-

from odoo import models, fields, _
from odoo.exceptions import UserError


class FalabellaAccount(models.Model):
    _name = "falabella.account"
    _description = "Cuenta Falabella Seller Center"

    name = fields.Char(string="Nombre", required=True)
    user_id_api = fields.Char(string="User ID", required=True)
    api_key = fields.Char(string="API Key", required=True)
    api_url = fields.Char(
        string="URL API",
        default="https://sellercenter-api.falabella.com/",
        required=True,
    )
    version = fields.Char(string="Versión", default="1.0", required=True)
    format = fields.Selection(
        [
            ("JSON", "JSON"),
            ("XML", "XML"),
        ],
        string="Formato",
        default="JSON",
        required=True,
    )
    active = fields.Boolean(default=True)

    last_response = fields.Text(string="Última respuesta")

    def action_test_connection(self):
        for account in self:
            response = self.env["falabella.api.service"].get_brands(account)


        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Falabella"),
                "message": _("Conexión ejecutada correctamente."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_sync_brands(self):
        total_created = 0
        total_updated = 0
        total = 0

        for account in self:
            print("action_sync_brands")
            result = self.env["falabella.api.service"].sync_brands(account)
            print("result",result)

            total_created += result.get("created", 0)
            total_updated += result.get("updated", 0)
            total += result.get("total", 0)

            account.last_response = _(
                "Sincronización de marcas finalizada.\n"
                "Total API: %s\n"
                "Creadas: %s\n"
                "Actualizadas: %s"
            ) % (result.get("total", 0), result.get("created", 0), result.get("updated", 0))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Falabella"),
                "message": _(
                    "Marcas sincronizadas. Total: %s | Creadas: %s | Actualizadas: %s"
                ) % (total, total_created, total_updated),
                "type": "success",
                "sticky": False,
            },
        }