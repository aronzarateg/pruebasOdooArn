# -*- coding: utf-8 -*-

from odoo import models, fields, _
from odoo.exceptions import UserError
import json


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
            print("result", result)

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

    def action_sync_category_attributes(self):
        total_created = 0
        total_updated = 0
        total = 0

        for account in self:
            categories = self.env["falabella.category"].sudo().search([
                ("account_id", "=", account.id),
                ("is_leaf", "=", True),
            ])

            for category in categories:
                result = self.env["falabella.api.service"].sync_category_attributes(
                    account,
                    category
                )
                print("result:",result)
                total_created += result.get("created", 0)
                total_updated += result.get("updated", 0)
                total += result.get("total", 0)

            account.last_response = _(
                "Sincronización de atributos finalizada.\n"
                "Categorías procesadas: %s\n"
                "Total atributos: %s\n"
                "Creados: %s\n"
                "Actualizados: %s"
            ) % (
                                        len(categories),
                                        total,
                                        total_created,
                                        total_updated,
                                    )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Falabella"),
                "message": _(
                    "Atributos sincronizados. Total: %s | Creados: %s | Actualizados: %s"
                ) % (total, total_created, total_updated),
                "type": "success",
                "sticky": False,
            },
        }

    def _extract_attributes_from_response(self, response):
        body = response.get("SuccessResponse", {}).get("Body", {})
        attributes_data = body.get("Attributes", {}).get("Attribute", [])

        if isinstance(attributes_data, dict):
            attributes_data = [attributes_data]

        return attributes_data or []

    def action_sync_categories(self):
        total_created = 0
        total_updated = 0
        total = 0

        for account in self:
            result = self.env["falabella.api.service"].sync_categories_falabella(account)

            total_created += result.get("created", 0)
            total_updated += result.get("updated", 0)
            total += result.get("total", 0)

            account.last_response = _(
                "Sincronización de categorías finalizada.\n"
                "Total API: %s\n"
                "Creadas: %s\n"
                "Actualizadas: %s"
            ) % (
                                        result.get("total", 0),
                                        result.get("created", 0),
                                        result.get("updated", 0),
                                    )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Falabella"),
                "message": _(
                    "Categorías sincronizadas. Total: %s | Creadas: %s | Actualizadas: %s"
                ) % (total, total_created, total_updated),
                "type": "success",
                "sticky": False,
            },
        }

    def action_sync_orders(self):
        total_created = 0
        total_updated = 0

        FalabellaOrder = self.env["falabella.order"].sudo()

        for account in self:
            response = self.env["falabella.api.service"].get_orders(
                account,
                extra_params={
                    "Status": "pending",
                    "Limit": 50,
                    "Offset": 0,
                }
            )

            orders = self._extract_orders(response)
            print("orders", orders)
            for order in orders:
                order_id = order.get("OrderId")
                if not order_id:
                    continue

                shipping = order.get("AddressShipping") or {}

                vals = {
                    "account_id": account.id,
                    "order_id": order_id,
                    "order_number": order.get("OrderNumber"),
                    "customer_name": "%s %s" % (
                        order.get("CustomerFirstName") or "",
                        order.get("CustomerLastName") or "",
                    ),
                    "customer_document": order.get("NationalRegistrationNumber"),
                    "status": order.get("Statuses", [{}])[0].get("Status")
                    if isinstance(order.get("Statuses"), list) else False,
                    "grand_total": float(order.get("GrandTotal") or 0.0),
                    "raw_response": json.dumps(order, indent=4, ensure_ascii=False),
                }

                falabella_order = FalabellaOrder.search([
                    ("account_id", "=", account.id),
                    ("order_id", "=", order_id),
                ], limit=1)

                if falabella_order:
                    falabella_order.write(vals)
                    total_updated += 1
                else:
                    falabella_order = FalabellaOrder.create(vals)
                    total_created += 1

                falabella_order.action_sync_order_items()

            account.last_response = json.dumps(response, indent=4, ensure_ascii=False)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Falabella"),
                "message": _("Órdenes sincronizadas. Creadas: %s | Actualizadas: %s") % (
                    total_created,
                    total_updated,
                ),
                "type": "success",
                "sticky": False,
            },
        }

    def _extract_orders(self, response):
        body = response.get("SuccessResponse", {}).get("Body", {})
        orders_data = body.get("Orders", {})

        orders = []

        if isinstance(orders_data, dict):
            order_data = orders_data.get("Order", [])

            if isinstance(order_data, dict):
                orders.append(order_data)
            elif isinstance(order_data, list):
                orders.extend(order_data)

        elif isinstance(orders_data, list):
            for item in orders_data:
                if isinstance(item, dict):
                    order_data = item.get("Order", item)

                    if isinstance(order_data, dict):
                        orders.append(order_data)
                    elif isinstance(order_data, list):
                        orders.extend(order_data)

        return orders
