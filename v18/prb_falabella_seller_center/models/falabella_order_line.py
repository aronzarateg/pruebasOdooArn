# -*- coding: utf-8 -*-

from odoo import models, fields


class FalabellaOrderLine(models.Model):
    _name = "falabella.order.line"
    _description = "Línea Orden Falabella"

    order_id = fields.Many2one("falabella.order", required=True, ondelete="cascade")
    order_item_id = fields.Char(string="Order Item ID")
    seller_sku = fields.Char(string="Seller SKU")
    name = fields.Char(string="Producto")
    status = fields.Char(string="Estado")
    quantity = fields.Float(string="Cantidad", default=1)
    unit_price = fields.Float(string="Precio unitario")
    raw_response = fields.Text(string="Respuesta API")
    _sql_constraints = [
        (
            "falabella_order_line_unique",
            "unique(order_id, order_item_id)",
            "La línea de Falabella ya existe para esta orden.",
        )
    ]