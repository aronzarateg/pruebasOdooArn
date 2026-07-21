# -*- coding: utf-8 -*-

from odoo import models, fields
import json


class FalabellaOrder(models.Model):
    _name = "falabella.order"
    _description = "Orden Falabella"
    _rec_name = "order_number"

    account_id = fields.Many2one("falabella.account", required=True)
    sale_order_id = fields.Many2one("sale.order", string="Cotización/Venta")

    order_id = fields.Char(string="Order ID", required=True)
    order_number = fields.Char(string="Order Number")
    customer_name = fields.Char(string="Cliente")
    customer_document = fields.Char(string="Documento")
    status = fields.Char(string="Estado")
    grand_total = fields.Float(string="Total")
    created_at = fields.Datetime(string="Fecha creación")
    raw_response = fields.Text(string="Respuesta API")
    line_ids = fields.One2many(
        "falabella.order.line",
        "order_id",
        string="Líneas"
    )
    _sql_constraints = [
        (
            "falabella_order_unique",
            "unique(account_id, order_id)",
            "La orden de Falabella ya existe para esta cuenta.",
        )
    ]
    def action_sync_order_items(self):
        Line = self.env["falabella.order.line"].sudo()

        for order in self:
            response = self.env["falabella.api.service"].get_order_items(
                order.account_id,
                order.order_id
            )

            items = order._extract_order_items(response)
            #print("items", items)
            for item in items:
                order_item_id = item.get("OrderItemId")
                if not order_item_id:
                    continue

                vals = {
                    "order_id": order.id,
                    "order_item_id": order_item_id,
                    "seller_sku": item.get("SellerSku"),
                    "name": item.get("Name"),
                    "status": item.get("Status"),
                    "quantity": 1,
                    "unit_price": float(item.get("ItemPrice") or item.get("PaidPrice") or 0.0),
                    "raw_response": json.dumps(item, indent=4, ensure_ascii=False),
                }

                line = Line.search([
                    ("order_id", "=", order.id),
                    ("order_item_id", "=", order_item_id),
                ], limit=1)

                if line:
                    line.write(vals)
                else:
                    Line.create(vals)

    def _extract_order_items(self, response):
        body = response.get("SuccessResponse", {}).get("Body", {})
        items_data = body.get("OrderItems", {})

        items = []

        if isinstance(items_data, dict):
            item_data = items_data.get("OrderItem", [])

            if isinstance(item_data, dict):
                items.append(item_data)
            elif isinstance(item_data, list):
                items.extend(item_data)

        elif isinstance(items_data, list):
            for item in items_data:
                if isinstance(item, dict):
                    item_data = item.get("OrderItem", item)

                    if isinstance(item_data, dict):
                        items.append(item_data)
                    elif isinstance(item_data, list):
                        items.extend(item_data)

        return items