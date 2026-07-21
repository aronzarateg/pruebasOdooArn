# -*- coding: utf-8 -*-

from odoo import models, fields
import json

from odoo.odoo.exceptions import UserError


class FalabellaOrder(models.Model):
    _name = "falabella.order"
    _description = "Orden Falabella"
    _rec_name = "order_number"

    account_id = fields.Many2one("falabella.account", required=True)
    sale_order_id = fields.Many2one("sale.order", string="Cotización/Venta")

    order_id = fields.Char(string="Orden Id", required=True,
                           help="Identificador de este pedido asignado por el Falabella Seller Center")
    order_number = fields.Char(string="Número Orden", help="El número de pedido")
    status = fields.Char(string="Estado")
    grand_total = fields.Float(string="Total")
    created_at = fields.Datetime(string="Fecha creación")
    update_at = fields.Datetime(string="Fecha actualización")

    customer_name = fields.Char(string="Cliente")
    customer_lastname = fields.Char(string="Cliente apellidos")
    customer_document = fields.Char(string="N° documento")
    address1 = fields.Char(string="Dirección 1")
    address2 = fields.Char(string="Dirección 2")
    address3 = fields.Char(string="Dirección 3")
    address4 = fields.Char(string="Dirección 4")
    address5 = fields.Char(string="Dirección 5")
    customerEmail = fields.Char(string="Correo")
    city = fields.Char(string="Ciudad")
    ward = fields.Char(string="Ward")
    region = fields.Char(string="Región")
    postcode = fields.Char(string="Codigo postal")
    country = fields.Char(string="Pais")
    phone = fields.Char(string="Telefono")
    phone2 = fields.Char(string="Telefono 2")

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
            print("account_id", order.account_id)
            print("order_id", order.order_id)
            print("order_number", order.order_number)
            response = self.env["falabella.api.service.orders"].get_order_items(
                order.account_id,
                order.order_id
            )

            items = order._extract_order_items(response)
            print("items", items)
            #raise UserError('STOP LINE')
            for item in items:

                '''
                Items de ordenes 
                
                OrderNumber	- String - Número de pedido mostrado al cliente final
                OrderItemId - String - Identificador único para cada artículo del pedido
                ShopId - String - Identificador único de la tienda que vendió el artículo (Falabella o Sodimac)
                OrderId - String - El mismo ID de pedido al que pertenece el artículo
                Name - String - Nombre del producto
                Sku	String - Stock-keeping Unit del producto
                Variation - String - Variaciones del producto (como tamaño, color, etc.)
                ShopSku	String - SKU específico de la tienda para el producto
                ShippingType - String - Método de envío utilizado, puede tener dos valores Dropshipping (Fulfiillment by Seller) y Fulfillment (FulFillment by Falabella)
                Currency - String - Moneda utilizada para la transacción. Depende de país Chile: CLP, Perú: PEN, Colombia: COP
                VoucherCode - String - Código de cupón aplicado al artículo (solo si aplica)
                Status - String - Estado actual del artículo del pedido, posibles valores: pending, ready_to_ship, shipped, delivered, canceled, failed_delivery, return_shipped_by_customer, return_waiting_for_approval, return_rejected, returned
                isProcessable - String - Indica si el artículo puede ser procesado (0 o 1)
                ShipmentProvider - String - Nombre del proveedor de envío
                IsDigital - String - Indica si el artículo es un producto digital (0 o 1)
                DigitalDeliveryInfo - String - Información sobre el método de entrega digital (si aplica)
                TrackingCode - String - Código de seguimiento para rastreo del envío
                TrackingCodePre - String - Código de seguimiento pre-generado antes de iniciar el envío
                Reason - String - Motivo de cancelación o devolución (si aplica)
                ReasonDetail - String - Razón detallada para la cancelación o devolución (si aplica)
                PurchaseOrderId - String - ID de orden de compra generado por la plataforma
                PurchaseOrderNumber - String - Número de orden de compra proporcionado al vendedor
                PackageId - String - ID de paquete único que contiene los artículos
                PromisedShippingTime - String - Corresponde a la fecha en que la orden debe ser entregada al operador logístico. Esfundamental cumplir con este plazo para evitar adelantos o retrasos en el envío, ya que cualquier desviación podría generar penalizaciones.
                ExtraAttributes - String - Atributos adicionales relacionados con el artículo del pedido
                ShippingProviderType - String - indica el nivel de servicio según la velocidad de entrega. Los valores posibles son: Same day, Direct, Click & Collect, Next Day, Home Delivery y Regular.
                CreatedAt - String - Marca de tiempo cuando se creó el artículo del pedido (formato ISO)
                UpdatedAt - String - Marca de tiempo cuando se actualizó por última vez el artículo del pedido (formato ISO)
                Vouchers - String - Lista de cupones aplicados al artículo
                SalesType - String - Tipo de venta, por ahora solo puede tener valor TDR.
                ReturnStatus - String - Estado de la solicitud de devolución, si la hay (por ejemplo, Pendiente, Aprobada)
                WalletCredits - String - Cantidad de créditos de billetera utilizados para este pedido
                ItemPrice - String - Precio original del artículo antes de descuentos o cupones
                PaidPrice - String - Precio pagado por el cliente final después de descuentos
                TaxAmount - String - Importe del impuesto aplicado al artículo
                CodCollectableAmount - String - Monto a cobrar en caso de pago contra entrega (COD)
                ShippingAmount - String - Importe total de envío cobrado por el artículo
                ShippingServiceCost - String - Costo real del servicio de envío
                ShippingTax - String - Importe del impuesto cobrado sobre el envío
                VoucherAmount - String - Descuento total aplicado a través de cupones
                '''
                order_item_id = item.get("OrderItemId")
                if not order_item_id:
                    continue
                vals = {
                    "order_id": order.id,
                    "order_item_id": order_item_id,
                    "name": item.get("Name"),
                    "seller_sku": item.get("Sku"),
                    "shop_sku": item.get("ShopSku"),
                    "unit_price": float(item.get("ItemPrice") or item.get("PaidPrice") or 0.0),

                    "paidPrice": item.get("PaidPrice"),
                    "taxAmount": item.get("TaxAmount"),
                    "shippingAmount": item.get("ShippingAmount"),
                    "quantity": 1,
                    "status": item.get("Status"),
                    #"raw_response": json.dumps(item, indent=4, ensure_ascii=False),
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
