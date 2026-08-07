from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
import json
import logging
from datetime import datetime
import pytz

_logger = logging.getLogger(__name__)


class ShopifyOrder(models.Model):
    _name = "shopify.order"
    _description = "Orden Shopify"

    account_id = fields.Many2one("shopify.account", required=True, ondelete="cascade", )
    shopify_order_id = fields.Char(required=True, index=True, )
    name = fields.Char()
    financial_status = fields.Char()
    fulfillment_status = fields.Char()
    document_type = fields.Selection(
        [
            ("DNI", "DNI"),
            ("RUC", "RUC"),
            ("CE", "Carné de extranjería"),
            ("PASSPORT", "Pasaporte"),
        ],
        string="Tipo de documento",
    )

    document_number = fields.Char(
        string="Número de documento",
        index=True,
    )

    shopify_created_at = fields.Datetime(string="Fecha de creación Shopify")
    shopify_updated_at = fields.Datetime(string="Fecha de actualización Shopify")
    processed_at = fields.Datetime(string="Fecha de procesamiento Shopify")
    cancelled_at = fields.Datetime(string="Fecha de cancelación")
    # Cliente
    customer_shopify_id = fields.Char(string="ID cliente Shopify", index=True)
    customer_email = fields.Char()
    customer_phone = fields.Char()
    customer_first_name = fields.Char()
    customer_last_name = fields.Char()

    # Moneda y totales
    currency = fields.Char()
    amount_total = fields.Float()
    amount_tax = fields.Float()
    amount_untaxed = fields.Float()
    amount_discount = fields.Float()

    # Facturación
    billing_name = fields.Char()
    billing_first_name = fields.Char()
    billing_last_name = fields.Char()
    billing_company = fields.Char()
    billing_phone = fields.Char()
    billing_address1 = fields.Char()
    billing_address2 = fields.Char()
    billing_city = fields.Char()
    billing_zip = fields.Char()
    billing_province = fields.Char()
    billing_province_code = fields.Char()
    billing_country = fields.Char()
    billing_country_code = fields.Char()

    # Envío
    shipping_name = fields.Char()
    shipping_first_name = fields.Char()
    shipping_last_name = fields.Char()
    shipping_company = fields.Char()
    shipping_phone = fields.Char()
    shipping_address1 = fields.Char()
    shipping_address2 = fields.Char()
    shipping_city = fields.Char()
    shipping_zip = fields.Char()
    shipping_province = fields.Char()
    shipping_province_code = fields.Char()
    shipping_country = fields.Char()
    shipping_country_code = fields.Char()

    # Información adicional
    note = fields.Text()
    tags = fields.Char()
    source_name = fields.Char()
    payload = fields.Text()

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Pedido de venta",
        readonly=True,
        copy=False,
    )

    state = fields.Selection(
        [
            ("draft", "Pendiente"),
            ("sale_created", "Pedido creado"),
            ("error", "Error"),
            ("cancelled", "Cancelado"),
        ],
        default="draft",
    )

    line_ids = fields.One2many(
        "shopify.order.line",
        "order_id",
        string="Líneas Shopify",
        copy=False,
    )

    error_message = fields.Text(copy=False)

    _sql_constraints = [
        (
            "shopify_order_account_unique",
            "unique(account_id, shopify_order_id)",
            "La orden Shopify ya existe para esta cuenta.",
        ),
    ]

    @api.model
    def create_or_update_from_shopify(self, account, data):
        order_id = str(
            data.get("legacyResourceId")
            or data.get("id")
            or ""
        )
        print("order_id", order_id)

        if not order_id:
            raise ValidationError(
                _("Shopify no devolvió el ID de la orden.")
            )

        vals = self._prepare_shopify_order_vals(account, data, )
        print("vals", vals)

        order = self.sudo().search([
            ("account_id", "=", account.id),
            ("shopify_order_id", "=", order_id),
        ], limit=1)

        if order:
            order.write(vals)
        else:
            order = self.sudo().create(vals)

        order._create_or_update_shopify_order_lines(data)

        return order

    def _prepare_shopify_order_vals(self, account, data):

        order_id = str(
            data.get("legacyResourceId")
            or data.get("id")
            or ""
        )

        customer = data.get("customer") or {}
        print("customer:", customer)
        billing_address = data.get("billingAddress") or {}
        print("billing_address:", billing_address)
        shipping_address = data.get("shippingAddress") or {}
        print("shipping_address:", shipping_address)
        print("shipping_add:", shipping_address.get("address1"))
        total_price = data.get("totalPriceSet") or {}
        subtotal_price = data.get("subtotalPriceSet") or {}
        total_tax = data.get("totalTaxSet") or {}
        total_discounts = data.get("totalDiscountsSet") or {}

        total_price_money = total_price.get("shopMoney") or {}
        subtotal_price_money = subtotal_price.get("shopMoney") or {}
        total_tax_money = total_tax.get("shopMoney") or {}
        total_discounts_money = total_discounts.get("shopMoney") or {}
        document_type, document_number = (
            self._get_shopify_customer_document(data)
        )
        vals = {
            "name": data.get("name"),
            "account_id": account.id,
            "shopify_order_id": order_id,
            "document_type": document_type,
            "document_number": document_number,
            # Estados
            "financial_status": data.get(
                "displayFinancialStatus"
            ),
            "fulfillment_status": data.get(
                "displayFulfillmentStatus"
            ),

            # Fechas
            "shopify_created_at": self._parse_shopify_datetime(
                data.get("createdAt")
            ),
            "shopify_updated_at": self._parse_shopify_datetime(
                data.get("updatedAt")
            ),
            "processed_at": self._parse_shopify_datetime(
                data.get("processedAt")
            ),
            "cancelled_at": self._parse_shopify_datetime(
                data.get("cancelledAt")
            ),

            # Cliente
            "customer_shopify_id": str(
                customer.get("legacyResourceId")
                or customer.get("id")
                or ""
            ),
            "customer_email": (
                    customer.get("email")
                    or data.get("email")
            ),
            "customer_phone": (
                    customer.get("phone")
                    or shipping_address.get("phone")
                    or billing_address.get("phone")
            ),
            "customer_first_name": customer.get("firstName"),
            "customer_last_name": customer.get("lastName"),

            # Moneda y totales
            "currency": (
                    total_price_money.get("currencyCode")
                    or data.get("currencyCode")
            ),
            "amount_untaxed": float(
                subtotal_price_money.get("amount") or 0.0
            ),
            "amount_tax": float(
                total_tax_money.get("amount") or 0.0
            ),
            "amount_discount": float(
                total_discounts_money.get("amount") or 0.0
            ),
            "amount_total": float(
                total_price_money.get("amount") or 0.0
            ),

            # Facturación
            "billing_name": billing_address.get("name"),
            "billing_first_name": billing_address.get("firstName"),
            "billing_last_name": billing_address.get("lastName"),
            "billing_company": billing_address.get("company"),
            "billing_phone": billing_address.get("phone"),
            "billing_address1": billing_address.get("address1"),
            "billing_address2": billing_address.get("address2"),
            "billing_city": billing_address.get("city"),
            "billing_zip": billing_address.get("zip"),
            "billing_province": billing_address.get("province"),
            "billing_province_code": billing_address.get(
                "provinceCode"
            ),
            "billing_country": billing_address.get("country"),
            "billing_country_code": billing_address.get(
                "countryCodeV2"
            ),

            # Envío
            "shipping_name": shipping_address.get("name"),
            "shipping_first_name": shipping_address.get("firstName"),
            "shipping_last_name": shipping_address.get("lastName"),
            "shipping_company": shipping_address.get("company"),
            "shipping_phone": shipping_address.get("phone"),
            "shipping_address1": shipping_address.get("address1"),
            "shipping_address2": shipping_address.get("address2"),
            "shipping_city": shipping_address.get("city"),
            "shipping_zip": shipping_address.get("zip"),
            "shipping_province": shipping_address.get("province"),
            "shipping_province_code": shipping_address.get(
                "provinceCode"
            ),
            "shipping_country": shipping_address.get("country"),
            "shipping_country_code": shipping_address.get(
                "countryCodeV2"
            ),

            # Información adicional
            "note": data.get("note"),
            "tags": data.get("tags"),
            "source_name": data.get("sourceName"),

            # Respaldo completo
            "payload": json.dumps(
                data,
                ensure_ascii=False,
                default=str,
            ),
        }
        # print("vals:",vals)

        return vals

    def _get_shopify_customer_document(self, data):
        customer = data.get("customer") or {}

        document_number = (
                (customer.get("customerDocumentNumber") or {}).get("value")
                or (data.get("orderDocumentNumber") or {}).get("value")
        )

        document_type = (
                (customer.get("customerDocumentType") or {}).get("value")
                or (data.get("orderDocumentType") or {}).get("value")
        )

        custom_attributes = {
            str(attribute.get("key") or "").strip().lower():
                str(attribute.get("value") or "").strip()
            for attribute in data.get("customAttributes") or []
        }

        document_number = (
                document_number
                or custom_attributes.get("numero de documento")
                or custom_attributes.get("número de documento")
                or custom_attributes.get("document_number")
                or custom_attributes.get("dni")
                or custom_attributes.get("ruc")
        )

        document_type = (
                document_type
                or custom_attributes.get("tipo de documento")
                or custom_attributes.get("document_type")
                or custom_attributes.get("tipo_documento")
        )

        if document_number:
            document_number = str(document_number).strip()

        if document_type:
            document_type = str(document_type).strip().upper()

        if document_number and not document_type:
            numeric_document = "".join(
                character
                for character in document_number
                if character.isdigit()
            )

            if len(numeric_document) == 8:
                document_type = "DNI"
            elif len(numeric_document) == 11:
                document_type = "RUC"

        return document_type or False, document_number or False

    def _create_or_update_shopify_order(self, account, data):
        self.ensure_one()

        order_id = str(
            data.get("legacyResourceId")
            or data.get("id")
            or ""
        )

        if not order_id:
            raise UserError(
                _("La orden de Shopify no contiene un identificador.")
            )

        vals = self._prepare_shopify_order_vals(
            account=account,
            data=data,
        )

        order = self.sudo().search([
            ("account_id", "=", account.id),
            ("shopify_order_id", "=", order_id),
        ], limit=1)

        if order:
            order.write(vals)
        else:
            order = self.sudo().create(vals)

        order._create_or_update_shopify_order_lines(data)

        return order

    def _create_or_update_shopify_order_lines(self, data):
        self.ensure_one()

        line_nodes = (
            data.get("lineItems", {})
            .get("nodes", [])
        )

        existing_lines = {
            line.shopify_line_id: line
            for line in self.line_ids
            if line.shopify_line_id
        }

        received_line_ids = set()

        for line_data in line_nodes:
            line_id = str(
                line_data.get("legacyResourceId")
                or line_data.get("id")
                or ""
            )

            received_line_ids.add(line_id)

            variant = line_data.get("variant") or {}
            product = variant.get("product") or {}

            original_unit_price = (
                line_data.get("originalUnitPriceSet", {})
                .get("shopMoney", {})
            )

            discounted_total = (
                line_data.get("discountedTotalSet", {})
                .get("shopMoney", {})
            )

            quantity = float(
                line_data.get("quantity") or 0.0
            )

            total_discount = sum(
                float(
                    allocation.get("allocatedAmountSet", {})
                    .get("shopMoney", {})
                    .get("amount")
                    or 0.0
                )
                for allocation in (
                        line_data.get("discountAllocations") or []
                )
            )

            line_vals = {
                "order_id": self.id,
                "shopify_line_id": line_id,
                "shopify_product_id": str(
                    product.get("legacyResourceId")
                    or product.get("id")
                    or ""
                ),
                "shopify_variant_id": str(
                    variant.get("legacyResourceId")
                    or variant.get("id")
                    or ""
                ),
                "sku": line_data.get("sku") or variant.get("sku"),
                "barcode": variant.get("barcode"),
                "name": line_data.get("name"),
                "quantity": quantity,
                "price_unit": float(
                    original_unit_price.get("amount") or 0.0
                ),
                "discount_amount": total_discount,
                "payload": json.dumps(
                    line_data,
                    ensure_ascii=False,
                    default=str,
                ),
            }

            existing_line = existing_lines.get(line_id)

            if existing_line:
                existing_line.write(line_vals)
            else:
                self.env["shopify.order.line"].sudo().create(
                    line_vals
                )

        obsolete_lines = self.line_ids.filtered(
            lambda line: (
                    line.shopify_line_id
                    and line.shopify_line_id not in received_line_ids
            )
        )

        obsolete_lines.unlink()

    def _prepare_sale_order_vals(self, partner, shipping_partner):
        self.ensure_one()

        return {
            "partner_id": partner.id,
            "partner_invoice_id": partner.id,
            "partner_shipping_id": shipping_partner.id,
            "company_id": self.account_id.company_id.id,
            "currency_id": self.currency_id.id,
            "client_order_ref": self.name,
            "origin": self.name,
            "note": self.note,
            "shopify_order_id": self.shopify_order_id,
            "shopify_account_id": self.account_id.id,
        }

    def _prepare_sale_order_line_vals(self, line, sale_order):
        self.ensure_one()

        return {
            "order_id": sale_order.id,
            "product_id": line.product_id.id,
            "name": line.name,
            "product_uom_qty": line.quantity,
            "product_uom": line.product_id.uom_id.id,
            "price_unit": line.price_unit,
            "discount": self._get_line_discount_percentage(line),
            "shopify_line_id": line.shopify_line_id,
        }

    @api.model
    def _parse_shopify_datetime(self, value):
        if not value:
            return False

        try:
            value = value.replace("Z", "+00:00")
            parsed_date = datetime.fromisoformat(value)

            if parsed_date.tzinfo:
                parsed_date = parsed_date.astimezone(
                    pytz.UTC
                ).replace(tzinfo=None)

            return fields.Datetime.to_string(parsed_date)

        except (TypeError, ValueError):
            _logger.warning(
                "Fecha Shopify no válida: %s",
                value,
            )
            return False

    def _process_inventory_level(self, payload):
        self.ensure_one()
        inventory_item_id = str(payload.get("inventory_item_id") or "")
        location_id = str(payload.get("location_id") or "")
        available = payload.get("available")

        if not inventory_item_id or not location_id:
            raise ValueError(
                "La notificación de inventario no contiene "
                "inventory_item_id o location_id."
            )

        product = self.env["product.product"].sudo().search([
            (
                "shopify_inventory_item_id",
                "=",
                inventory_item_id,
            ),
        ], limit=1)

        if not product:
            raise ValueError(
                "No existe un producto Odoo asociado al "
                "inventory_item_id %s."
                % inventory_item_id
            )

        location_mapping = self.env[
            "shopify.location"
        ].sudo().search([
            ("account_id", "=", self.account_id.id),
            ("shopify_location_id", "=", location_id),
        ], limit=1)

        if not location_mapping:
            raise ValueError(
                "No existe una ubicación Odoo asociada a la "
                "Location Shopify %s."
                % location_id
            )

        # Aquí debes decidir si Shopify o Odoo será el maestro del stock.
        product.with_context(skip_shopify_stock_sync=True, )._apply_shopify_stock_quantity(location_mapping,
                                                                                           available, )

        return True


class ShopifyOrderLine(models.Model):
    _name = "shopify.order.line"
    _description = "Línea de orden Shopify"

    order_id = fields.Many2one(
        "shopify.order",
        required=True,
        ondelete="cascade",
    )
    shopify_line_id = fields.Char(index=True)
    shopify_product_id = fields.Char(index=True)
    shopify_variant_id = fields.Char(index=True)

    sku = fields.Char()
    barcode = fields.Char()
    name = fields.Char()
    quantity = fields.Float()
    price_unit = fields.Float()
    discount_amount = fields.Float()
    tax_amount = fields.Float()

    product_id = fields.Many2one("product.product")
    payload = fields.Text()
