# -*- coding: utf-8 -*-

from odoo import models, fields


class FalabellaOrderLine(models.Model):
    _name = "falabella.order.line"
    _description = "Línea Orden Falabella"

    order_id = fields.Many2one("falabella.order", required=True, ondelete="cascade")
    order_item_id = fields.Char(string="Order Item ID")
    name = fields.Char(string="Producto")
    seller_sku = fields.Char(string="SKU", help="Stock-keeping Unit del producto")
    shop_sku = fields.Char(string="SKU tienda", help="SKU específico de la tienda para el producto")

    unit_price = fields.Char(string="Precio", help="Precio original del artículo antes de descuentos o cupones")

    paid_price = fields.Char(string="Precio pagado", help="Precio pagado por el cliente final después de descuentos")
    tax_amount = fields.Char(string="Importe impuesto", help="Importe del impuesto aplicado al artículo")
    shipping_amount = fields.Char(string="Importe envío", help="Importe total de envío cobrado por el artículo")



    status = fields.Char(string="Estado")
    quantity = fields.Float(string="Cantidad", default=1)
    raw_response = fields.Text(string="Respuesta API")
    _sql_constraints = [
        (
            "falabella_order_line_unique",
            "unique(order_id, order_item_id)",
            "La línea de Falabella ya existe para esta orden.",
        )
    ]