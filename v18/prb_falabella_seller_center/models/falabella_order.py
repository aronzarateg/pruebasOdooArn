# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import json

import logging
from markupsafe import Markup, escape
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class FalabellaOrder(models.Model):
    _name = "falabella.order"
    _description = "Orden Falabella"
    _rec_name = "order_number"

    account_id = fields.Many2one("falabella.account", required=True)
    sale_order_id = fields.Many2one("sale.order", string="Cotización/Venta")
    sale_order_count = fields.Integer(
        string="Cantidad de cotizaciones",
        compute="_compute_sale_order_count",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Pendiente"),
            ("sale_created", "Cotización creada"),
            # ("confirmed", "Venta confirmada"),
            # ("shipped", "Enviado"),
            ("canceled", "Cancelado"),
        ],
        string="Estado Odoo",
        default="draft",
        readonly=True,
        copy=False,
    )
    processing_error = fields.Text(
        string="Error de procesamiento",
        readonly=True,
        copy=False,
    )

    processing_attempts = fields.Integer(
        string="Intentos de procesamiento",
        readonly=True,
        copy=False,
    )

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

    @api.depends("sale_order_id")
    def _compute_sale_order_count(self):
        for order in self:
            order.sale_order_count = 1 if order.sale_order_id else 0

    def action_create_sale_order(self):
        self.ensure_one()

        if self.sale_order_id:
            raise UserError(
                _(
                    "La orden Falabella %s ya tiene relacionada la cotización %s."
                )
                % (
                    self.order_number or self.order_id,
                    self.sale_order_id.name,
                )
            )

        self._create_sale_order_from_falabella()

        return self.action_view_sale_order()

    def _get_or_create_partner(self):
        self.ensure_one()

        Partner = self.env["res.partner"].sudo()

        document = (self.customer_document or "").strip()

        if not document:
            raise ValidationError(
                _("Debe existir un número de documento para crear el cliente.")
            )

        partner = Partner.search(
            [
                ("vat", "=", document),
                ("parent_id", "=", False),
            ],
            limit=1,
        )

        partner_vals = self._prepare_partner_vals()
        if partner:
            partner.write(partner_vals)
        else:
            partner = Partner.create(partner_vals)

        return partner

    def _prepare_partner_vals(self):
        self.ensure_one()

        full_name = " ".join(
            filter(
                None,
                [
                    (self.customer_name or "").strip(),
                    (self.customer_lastname or "").strip(),
                ],
            )
        )

        street = self._join_address_parts(
            self.address1,
            self.address2,
        )

        street2 = self._join_address_parts(
            self.address3,
            self.address4,
            self.address5,
        )

        country = self._find_country()
        state = self._find_state(country)
        city = self._find_city(state, country)
        district = self._find_district(city)
        # print("state", district)
        # raise UserError('STOPPPP district')

        vals = {
            "name": full_name or self.customer_document,
            "it_name": full_name or self.customer_document,
            "vat": (self.customer_document or "").strip(),
            "email": (self.customerEmail or "").strip() or False,
            "phone": (self.phone or "").strip() or False,
            "mobile": (self.phone2 or "").strip() or False,
            "street": street or False,
            "street2": street2 or False,
            "zip": (self.postcode or "").strip() or False,
            "city": (self.city or "").strip() or False,
            "country_id": country.id if country else False,
            "state_id": state.id if state else False,
            "customer_rank": 1,
            "company_type": "person",
        }

        # En caso utilices l10n_latam_base.
        if "l10n_latam_identification_type_id" in self.env["res.partner"]._fields:
            identification_type = self._find_identification_type()

            if identification_type:
                vals["l10n_latam_identification_type_id"] = (
                    identification_type.id
                )

        # En caso utilices los campos de ubicación peruana.
        if city and "city_id" in self.env["res.partner"]._fields:
            vals["city_id"] = city.id
            vals.pop("city", None)

        # Campo estándar usado normalmente por l10n_pe.
        if district and "l10n_pe_district" in self.env["res.partner"]._fields:
            vals["l10n_pe_district"] = district.id

        return vals

    @staticmethod
    def _join_address_parts(*parts):
        clean_parts = [
            str(part).strip()
            for part in parts
            if part and str(part).strip()
        ]
        return " ".join(clean_parts)

    def _find_country(self):
        self.ensure_one()

        country_code = (self.country or "").strip().upper()

        if not country_code:
            return self.env["res.country"]

        country = self.env["res.country"].search(
            [("code", "=", country_code)],
            limit=1,
        )

        return country

    def _find_state(self, country):
        self.ensure_one()

        region_name = (self.region or "").strip()

        if not region_name:
            return self.env["res.country.state"]

        domain = [("name", "=ilike", region_name)]

        if country:
            domain.append(("country_id", "=", country.id))

        return self.env["res.country.state"].search(
            domain,
            limit=1,
        )

    def _find_city(self, state, country):
        """
        Busca res.city solamente cuando el modelo existe.
        Esto permite compatibilidad con instalaciones que no tienen
        configuradas las ubicaciones peruanas.
        """
        self.ensure_one()

        if "res.city" not in self.env:
            return False

        city_name = (self.city or "").strip()

        if not city_name:
            return False

        City = self.env["res.city"]

        domain = [("name", "=ilike", city_name)]

        if state and "state_id" in City._fields:
            domain.append(("state_id", "=", state.id))
        elif country and "country_id" in City._fields:
            domain.append(("country_id", "=", country.id))

        return City.search(domain, limit=1)

    def _find_district(self, city=False):
        self.ensure_one()

        district_name = (self.ward or "").strip()

        if not district_name:
            return self.env["l10n_pe.res.city.district"]

        District = self.env["l10n_pe.res.city.district"]

        domain = [
            ("name", "=ilike", district_name),
        ]

        # Dependiendo de la versión/localización, el distrito puede
        # estar relacionado con la ciudad mediante city_id.
        if city and "city_id" in District._fields:
            domain.append(("city_id", "=", city.id))

        district = District.search(domain, limit=1)

        if not district:
            district = District.search(
                [("name", "ilike", district_name)],
                limit=1,
            )

        return district

    def _find_identification_type(self):
        self.ensure_one()

        IdentificationType = self.env[
            "l10n_latam.identification.type"
        ]

        document = (self.customer_document or "").strip()

        # Perú:
        # DNI = 8 dígitos
        # RUC = 11 dígitos
        if len(document) == 8:
            code = "1"
        elif len(document) == 11:
            code = "6"
        else:
            return IdentificationType

        identification_type = IdentificationType.search(
            [
                ("l10n_pe_vat_code", "=", code),
            ],
            limit=1,
        )

        if not identification_type:
            identification_type = IdentificationType.search(
                [("name", "ilike", "DNI" if code == "1" else "RUC")],
                limit=1,
            )

        return identification_type

    def _prepare_sale_order_lines(self):
        self.ensure_one()

        Product = self.env["product.product"].sudo()
        sale_lines = []
        missing_skus = []

        for falabella_line in self.line_ids:
            sku = (falabella_line.seller_sku or "").strip()

            if not sku:
                missing_skus.append(
                    falabella_line.name or falabella_line.order_item_id
                )
                continue

            product = Product.search(
                [
                    ("default_code", "=", sku),
                    ("sale_ok", "=", True),
                ],
                limit=1,
            )

            if not product:
                missing_skus.append(sku)
                continue

            quantity = falabella_line.quantity or 1.0
            price_unit = falabella_line.unit_price or 0.0

            sale_lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "name": falabella_line.name
                                or product.get_product_multiline_description_sale(),
                        "product_uom_qty": quantity,
                        "product_uom": product.uom_id.id,
                        "price_unit": price_unit,
                    },
                )
            )

        if missing_skus:
            raise ValidationError(
                _(
                    "No se pudo crear la cotización porque los siguientes "
                    "productos no fueron encontrados por SKU:\n\n%s"
                )
                % "\n".join(
                    "- %s" % sku
                    for sku in missing_skus
                )
            )

        if not sale_lines:
            raise ValidationError(
                _("No existen productos válidos para crear la cotización.")
            )

        return sale_lines

    def action_view_sale_order(self):
        self.ensure_one()

        if not self.sale_order_id:
            raise UserError(
                _("La orden Falabella no tiene una cotización relacionada.")
            )

        return {
            "type": "ir.actions.act_window",
            "name": _("Cotización"),
            "res_model": "sale.order",
            "view_mode": "form",
            "res_id": self.sale_order_id.id,
            "target": "current",
        }

    def _create_sale_order_from_falabella(self):
        self.ensure_one()

        if self.sale_order_id:
            raise UserError(
                _("La orden Falabella ya tiene una cotización relacionada.")
            )

        if not self.customer_document:
            raise ValidationError(
                _("La orden no tiene número de documento del cliente.")
            )

        if not self.line_ids:
            raise ValidationError(
                _("La orden Falabella no tiene líneas para crear la cotización.")
            )

        partner = self._get_or_create_partner()
        sale_order_lines = self._prepare_sale_order_lines()

        note = _(
            "Cotización creada desde la orden Falabella:\n"
            "Número de orden: %(order_number)s\n"
            "ID Falabella: %(order_id)s"
        ) % {
                   "order_number": self.order_number or "",
                   "order_id": self.order_id or "",
               }

        sale_vals = {
            "partner_id": partner.id,
            "partner_invoice_id": partner.id,
            "partner_shipping_id": partner.id,
            "origin": self.order_number or self.order_id,
            "client_order_ref": self.order_number,
            "order_line": sale_order_lines,
            "note": note,
        }

        sale_order = self.env["sale.order"].create(sale_vals)

        message = Markup(
            "<p>"
            "<strong>Cotización creada desde la orden Falabella.</strong><br/>"
            "<b>Número de orden:</b> {}<br/>"
            "<b>ID Falabella:</b> {}"
            "</p>"
        ).format(
            escape(self.order_number or ""),
            escape(self.order_id or ""),
        )

        sale_order.message_post(
            body=message,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )

        self.write({
            "sale_order_id": sale_order.id,
            "state": "sale_created",
        })

        return sale_order

    @api.model
    def _cron_create_sale_orders(self, limit=50):
        orders = self.env["falabella.order"].sudo().search(
            [
                ("state", "=", "draft"),
                ("sale_order_id", "=", False),
                ("processing_attempts", "<", 5),
            ],
            order="created_at asc, id asc",
            limit=limit,
        )

        for order in orders:
            try:
                with self.env.cr.savepoint():
                    order._create_sale_order_from_falabella()

                    order.write({
                        "processing_error": False,
                    })

            except Exception as error:
                _logger.exception(
                    "Error procesando orden Falabella %s.",
                    order.order_number or order.order_id,
                )

                order.write({
                    "processing_attempts": order.processing_attempts + 1,
                    "processing_error": str(error),
                })

        return True

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
            # raise UserError('STOP LINE')
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

                    "paid_price": item.get("PaidPrice"),
                    "tax_amount": item.get("TaxAmount"),
                    "shipping_amount": item.get("ShippingAmount"),
                    "quantity": 1,
                    "status": item.get("Status"),
                    # "raw_response": json.dumps(item, indent=4, ensure_ascii=False),
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
