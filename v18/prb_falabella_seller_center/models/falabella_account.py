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
            account.last_response = str(response)

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

    def action_get_brands(self):
        for account in self:
            response = self.env["falabella.api.service"].get_brands(account)
            account.last_response = str(response)