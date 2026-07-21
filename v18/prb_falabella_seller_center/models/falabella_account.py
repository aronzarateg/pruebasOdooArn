# -*- coding: utf-8 -*-

from odoo import models, fields, _
from odoo.exceptions import UserError
import json
from datetime import timedelta
from odoo import fields


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

    # Sincronizar ordenes
    def action_sync_orders(self):
        total_created = 0
        total_updated = 0
        today = fields.Datetime.now()
        yesterday = today - timedelta(days=1)

        FalabellaOrder = self.env["falabella.order"].sudo()
        print("today:", today)
        print("yesterday:", yesterday)
        for account in self:
            response = self.env["falabella.api.service.orders"].get_orders(
                account,
                extra_params={
                    "Status": "pending",
                    "CreatedAfter": yesterday.strftime("%Y-%m-%dT%H:%M:%S"),
                    "CreatedBefore": today.strftime("%Y-%m-%dT%H:%M:%S"),
                    "Limit": 50,
                    "Offset": 0,
                }
            )
            orders = self._extract_orders(response)
            print("orders", orders)
            for order in orders:
                '''
                OrderId - string - Identificador de este pedido asignado por el Falabella Seller Center
                CustomerFirstName - string - El nombre del cliente
                CustomerLastName - string - El apellido del cliente
                OrderNumber - string - El número de pedido
                PaymentMethod - string - La forma de pago
                DeliveryInfo - string - Información sobre la entrega de ese pedido
                Price - Float - El importe total de este pedido
                GiftOption - Boolean - 1 si el artículo es un regalo, 0 si no lo es
                GiftMessage - string - Mensaje de regalo según lo especificado por el cliente
                CreatedAt - DateTime - Fecha y hora en que se realizó el pedido
                UpdatedAt - DateTime - Fecha y hora de la última modificación de la orden
                AddressBilling - Subsection-objeto - Nodo que contiene nodos adicionales, que conforman la dirección de facturación: Nombre, Apellido, Teléfono, Teléfono2, Dirección1, Dirección2, Ciudad, Código postal, País
                AddressShipping - Subsection-objeto - Nodo que contiene nodos adicionales, que conforman la dirección de envío: Nombre, Apellido, Teléfono, Teléfono2, Dirección1, Dirección2, Ciudad, Código postal, País
                NationalRegistrationNumber - string - Se requiere en algunos países
                ItemsCount - Integer - Número de artículos en orden
                Statuses - Array - Estados únicos de los artículos del pedido. (pista: puede encontrar todos los diferentes códigos de estado en el ejemplo de respuesta)
                PromisedShippingTime - DateTime - Corresponde a la fecha en que la orden debe ser entregada al operador logístico. Esfundamental cumplir con este plazo para evitar adelantos o retrasos en el envío, ya que cualquier desviación podría generar penalizaciones.
                ExtraAttributes - String-objeto  - Atributos extra que fueron pasados a Falabella Seller Center en la llamada getMarketPlaceOrders. Es una cadena JSON que el cliente debe analizar.
                ExtraBillingAttributes - String-objeto - Nodo que contiene información adicional para facturación: LegalId FiscalPerson, DocumentType, ReceiverRegion, ReceiverAddress, ReceiverPostcode, ReceiverLegalName, ReceiverMunicipality, ReceiverTypeRegimen, CustomerVerifierDigit
                ShippingType - String - Modalidad de fulfillment y de delivery de la orden
                InvoiceRequired - Boolean - Entrega valor True(“Factura empresa” en Colombia) si el documento es factura, y valor False si este es una boleta (“Factura persona natural” en Colombia).
                SellerWarehouseId - String - ID único de bodega asignado por el Seller.
                FacilityId - String - ID único de bodega asignado por Falabella.
                '''

                order_id = order.get("OrderId")

                AddressBilling = order.get("AddressBilling")
                if not order_id:
                    continue
                vals = {
                    "account_id": account.id,
                    "order_id": order_id,
                    "order_number": order.get("OrderNumber"),
                    "customer_name": order.get("CustomerFirstName"),
                    "customer_lastname": order.get("CustomerLastName"),
                    "customer_document": order.get("NationalRegistrationNumber"),
                    "created_at": order.get("CreatedAt"),
                    "update_at": order.get("UpdatedAt"),

                    "address1": AddressBilling.get("Address1"),
                    "address2": AddressBilling.get("Address2"),
                    "address3": AddressBilling.get("Address3"),
                    "address4": AddressBilling.get("Address4"),
                    "address5": AddressBilling.get("Address5"),
                    "customerEmail": AddressBilling.get("CustomerEmail"),
                    "city": AddressBilling.get("City"),
                    "ward": AddressBilling.get("Ward"),
                    "region": AddressBilling.get("Region"),
                    "postcode": AddressBilling.get("PostCode"),
                    "country": AddressBilling.get("Country"),
                    "phone": AddressBilling.get("Phone"),
                    "phone2": AddressBilling.get("Phone2"),

                    "status": order.get("Statuses", [{}])[0].get("Status")
                    if isinstance(order.get("Statuses"), list) else False,
                    "grand_total": float(order.get("GrandTotal") or 0.0),
                    #"raw_response": json.dumps(order, indent=4, ensure_ascii=False),
                }

                print("vals", vals)
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

            #account.last_response = json.dumps(response, indent=4, ensure_ascii=False)

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
