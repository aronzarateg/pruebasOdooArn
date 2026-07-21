# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

import logging
from datetime import timedelta

_logger = logging.getLogger(__name__)


class FalabellaAccount(models.Model):
    _name = "falabella.account"
    _description = "Cuenta Falabella Seller Center"
    active = fields.Boolean(string="Activo", default=True, copy=False, )

    image_1920 = fields.Image(string="Logo", max_width=1920, max_height=1920, )

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

    last_response = fields.Text(string="Última respuesta")
    last_order_sync = fields.Datetime(
        string="Última sincronización de órdenes",
        copy=False,
    )

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

    # Sincronizar ordenes
    def action_sync_orders(self):
        accounts = self.sudo().search([
            ("active", "=", True),
        ])
        if not accounts:
            _logger.info(
                "No existen cuentas Falabella activas para sincronizar."
            )
            return True
        result = self._sync_orders_saga()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Falabella"),
                "message": _(
                    "Órdenes sincronizadas. "
                    "Creadas: %(created)s | "
                    "Actualizadas: %(updated)s | "
                    "Errores: %(errors)s"
                ) % result,
                "type": "warning" if result["errors"] else "success",
                "sticky": bool(result["errors"]),
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

    @api.model
    def _cron_sync_orders(self):
        accounts = self.sudo().search([
            ("active", "=", True),
        ])

        if not accounts:
            _logger.info(
                "No existen cuentas Falabella activas para sincronizar."
            )
            return True

        result = accounts._sync_orders_saga()

        _logger.info(
            "Sincronización automática Falabella finalizada. "
            "Creadas: %s | Actualizadas: %s | Errores: %s",
            result["created"],
            result["updated"],
            result["errors"],
        )

        return True

    def _sync_orders_saga(self):
        total_created = 0
        total_updated = 0
        total_errors = 0

        FalabellaOrder = self.env["falabella.order"].sudo()

        for account in self:
            now = fields.Datetime.now()
            date_from = account.last_order_sync or (
                    now - timedelta(days=1)
            )

            account_has_errors = False

            try:
                response = self.env[
                    "falabella.api.service.orders"
                ].get_orders(
                    account,
                    extra_params={
                        "Status": "pending",
                        "CreatedAfter": date_from.strftime(
                            "%Y-%m-%dT%H:%M:%S"
                        ),
                        "CreatedBefore": now.strftime(
                            "%Y-%m-%dT%H:%M:%S"
                        ),
                        "Limit": 50,
                        "Offset": 0,
                    },
                )

                orders = account._extract_orders(response)

                _logger.info(
                    "Cuenta Falabella %s: se encontraron %s órdenes "
                    "entre %s y %s.",
                    account.display_name,
                    len(orders),
                    date_from,
                    now,
                )

                for order_data in orders:
                    try:
                        with account.env.cr.savepoint():
                            order_id = order_data.get("OrderId")

                            if not order_id:
                                _logger.warning(
                                    "Orden Falabella omitida porque "
                                    "no tiene OrderId."
                                )
                                continue

                            address_billing = (
                                    order_data.get("AddressBilling") or {}
                            )

                            statuses = order_data.get("Statuses") or []
                            status = False

                            if isinstance(statuses, list) and statuses:
                                first_status = statuses[0]

                                if isinstance(first_status, dict):
                                    status = first_status.get("Status")

                            vals = {
                                "account_id": account.id,
                                "order_id": order_id,
                                "order_number": order_data.get(
                                    "OrderNumber"
                                ),
                                "customer_name": order_data.get(
                                    "CustomerFirstName"
                                ),
                                "customer_lastname": order_data.get(
                                    "CustomerLastName"
                                ),
                                "customer_document": order_data.get(
                                    "NationalRegistrationNumber"
                                ),
                                "created_at": order_data.get("CreatedAt"),
                                "update_at": order_data.get("UpdatedAt"),

                                "address1": address_billing.get("Address1"),
                                "address2": address_billing.get("Address2"),
                                "address3": address_billing.get("Address3"),
                                "address4": address_billing.get("Address4"),
                                "address5": address_billing.get("Address5"),
                                "customerEmail": address_billing.get(
                                    "CustomerEmail"
                                ),
                                "city": address_billing.get("City"),
                                "ward": address_billing.get("Ward"),
                                "region": address_billing.get("Region"),
                                "postcode": address_billing.get("PostCode"),
                                "country": address_billing.get("Country"),
                                "phone": address_billing.get("Phone"),
                                "phone2": address_billing.get("Phone2"),
                                "status": status,
                                "grand_total": float(
                                    order_data.get("GrandTotal") or 0.0
                                ),
                            }

                            falabella_order = FalabellaOrder.search(
                                [
                                    ("account_id", "=", account.id),
                                    ("order_id", "=", order_id),
                                ],
                                limit=1,
                            )

                            is_new = not bool(falabella_order)

                            if falabella_order:
                                falabella_order.write(vals)
                            else:
                                falabella_order = FalabellaOrder.create(
                                    vals
                                )

                            falabella_order.action_sync_order_items()

                            if is_new:
                                total_created += 1
                            else:
                                total_updated += 1

                    except Exception:
                        account_has_errors = True
                        total_errors += 1

                        _logger.exception(
                            "Error sincronizando la orden Falabella %s "
                            "de la cuenta %s.",
                            order_data.get("OrderNumber")
                            or order_data.get("OrderId"),
                            account.display_name,
                        )

                if not account_has_errors:
                    account.write({
                        "last_order_sync": now,
                    })

            except Exception:
                total_errors += 1

                _logger.exception(
                    "Error obteniendo órdenes de la cuenta Falabella %s.",
                    account.display_name,
                )

        return {
            "created": total_created,
            "updated": total_updated,
            "errors": total_errors,
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
                print("result:", result)
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
