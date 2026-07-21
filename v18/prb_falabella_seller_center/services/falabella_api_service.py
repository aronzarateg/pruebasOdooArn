# -*- coding: utf-8 -*-

import hmac
import json
import hashlib
import logging
import requests

from datetime import datetime, timezone
from urllib.parse import urlencode

from odoo import models, _
from odoo.exceptions import UserError
from xml.sax.saxutils import escape

_logger = logging.getLogger(__name__)


class FalabellaApiService(models.AbstractModel):
    _name = "falabella.api.service"
    _description = "Servicio API Falabella Seller Center"

    def _get_timestamp(self):
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")

    def _generate_signature(self, params, api_key):
        """
        Genera firma HMAC-SHA256.
        Importante:
        - No incluir Signature.
        - Ordenar params alfabéticamente.
        - Usar URL encoding.
        """
        params_to_sign = {
            key: value
            for key, value in params.items()
            if key != "Signature"
        }

        query_string = urlencode(sorted(params_to_sign.items()))

        signature = hmac.new(
            api_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return signature

    def _build_params(self, account, action, extra_params=None):
        params = {
            "Action": action,
            "Format": account.format or "JSON",
            "Timestamp": self._get_timestamp(),
            "UserID": account.user_id_api,
            "Version": account.version or "1.0",
        }

        if extra_params:
            params.update(extra_params)

        params["Signature"] = self._generate_signature(
            params,
            account.api_key,
        )

        return params

    def _call_api(self, account, action, method="GET", extra_params=None, payload=None):
        params = self._build_params(account, action, extra_params)

        headers = {
            "Accept": "application/json",
        }

        try:
            if method == "GET":
                response = requests.get(
                    account.api_url,
                    params=params,
                    headers=headers,
                    timeout=60,
                )
            elif method == "POST":
                headers["Content-Type"] = "application/xml"
                response = requests.post(
                    account.api_url,
                    params=params,
                    data=payload,
                    headers=headers,
                    timeout=60,
                )
            else:
                raise UserError(_("Método HTTP no soportado: %s") % method)

        except requests.exceptions.RequestException as e:
            raise UserError(_("Error conectando con Falabella: %s") % e)

        _logger.info("Falabella URL: %s", response.url)
        _logger.info("Falabella Response: %s", response.text)

        if response.status_code not in [200, 201]:
            raise UserError(_("Error HTTP Falabella: %s") % response.text)

        if account.format == "JSON":
            try:
                data = response.json()
            except Exception:
                raise UserError(_("Respuesta JSON inválida: %s") % response.text)

            if data.get("ErrorResponse"):
                error = data["ErrorResponse"]["Head"].get("ErrorMessage")
                raise UserError(_("Error Falabella: %s") % error)

            return data

        return response.text

    def _extract_brands_from_response(self, response):
        body = response.get("SuccessResponse", {}).get("Body", {})
        brands_data = body.get("Brands", [])

        brands = []

        if isinstance(brands_data, list):
            for item in brands_data:
                if isinstance(item, dict) and item.get("Brand"):
                    brands.append(item.get("Brand"))

        elif isinstance(brands_data, dict):
            brand_data = brands_data.get("Brand", [])
            if isinstance(brand_data, list):
                brands = brand_data
            elif isinstance(brand_data, dict):
                brands = [brand_data]

        return brands

    def sync_brands(self, account):
        print("sync_brands")
        response = self.get_brands(account)

        raw_response = json.dumps(response, indent=4, ensure_ascii=False)

        brands = self._extract_brands_from_response(response)

        Brand = self.env["falabella.brand"].sudo()

        created = 0
        updated = 0

        for item in brands:
            brand_id = int(item.get("BrandId") or 0)
            name = item.get("Name")
            global_identifier = item.get("GlobalIdentifier")

            if not brand_id or not name:
                continue

            vals = {
                "account_id": account.id,
                "brand_id": brand_id,
                "name": name,
                "global_identifier": global_identifier,
                # "raw_xml": raw_response,
            }
            print("vals:", vals)
            brand = Brand.search([
                ("account_id", "=", account.id),
                ("brand_id", "=", brand_id),
            ], limit=1)

            if brand:
                brand.write(vals)
                updated += 1
            else:
                print("vals", vals)
                Brand.create(vals)
                created += 1

        return {
            "created": created,
            "updated": updated,
            "total": len(brands),
        }

    def get_brands(self, account):
        return self._call_api(
            account=account,
            action="GetBrands",
            method="GET",
        )

    def sync_category_attributes(self, account, category):
        response = self.get_category_attributes(account, category.category_id)

        print("response:", response)
        attributes = self._extract_attributes_from_response(response)

        Attribute = self.env["falabella.category.attribute"].sudo()

        created = 0
        updated = 0

        for item in attributes:
            attribute_name = item.get("Name")
            label = item.get("Label") or attribute_name
            is_mandatory = item.get("IsMandatory") in [True, "true", "1", 1]

            if not attribute_name:
                continue

            vals = {
                "account_id": account.id,
                "category_id": category.id,
                "name": attribute_name,
                "label": label,
                "is_mandatory": is_mandatory,
                "attribute_type": item.get("AttributeType"),
                "input_type": item.get("InputType"),
            }

            attribute = Attribute.search([
                ("account_id", "=", account.id),
                ("category_id", "=", category.id),
                ("name", "=", attribute_name),
            ], limit=1)

            if attribute:
                attribute.write(vals)
                updated += 1
            else:
                Attribute.create(vals)
                created += 1

        return {
            "created": created,
            "updated": updated,
            "total": len(attributes),
        }

    def get_category_attributes(self, account, category_id):
        return self._call_api(
            account=account,
            action="GetCategoryAttributes",
            method="GET",
            extra_params={
                "PrimaryCategory": category_id,
            },
        )

    def _extract_categories_from_response(self, response):
        categories = []

        def walk_category(item, parent_category_id=False):
            category_id = int(item.get("CategoryId") or 0)

            categories.append({
                "Name": item.get("Name"),
                "CategoryId": category_id,
                "GlobalIdentifier": item.get("GlobalIdentifier"),
                "AttributeSetId": int(item.get("AttributeSetId") or 0),
                "ParentCategoryId": parent_category_id or 0,
            })

            children = item.get("Children")

            if isinstance(children, dict):
                child_data = children.get("Category")

                if isinstance(child_data, dict):
                    child_data = [child_data]

                if isinstance(child_data, list):
                    for child in child_data:
                        walk_category(child, category_id)

        root = response.get("SuccessResponse", {}) \
            .get("Body", {}) \
            .get("Categories", {}) \
            .get("Category", [])

        if isinstance(root, dict):
            root = [root]

        for item in root:
            walk_category(item, False)

        return categories

    def publish_product(self, product):
        self._validate_product_before_publish(product)

        payload = self._build_product_xml_payload(product)

        response = self._call_api(
            account=product.falabella_account_id,
            action="ProductCreate",
            method="POST",
            payload=payload,
        )
        print("response:", response)
        head = response.get("SuccessResponse", {}).get("Head", {})
        request_id = head.get("RequestId")

        return {
            "success": True if request_id else False,
            "request_id": request_id,
            "item_id": False,
            "response": response,
        }

    def _validate_product_before_publish(self, product):
        if not product.default_code:
            raise UserError(_("El producto debe tener referencia interna / SKU."))

        if not product.falabella_account_id:
            raise UserError(_("Debe seleccionar una cuenta Falabella."))

        if not product.falabella_brand_id:
            raise UserError(_("Debe seleccionar una marca Falabella."))

        if not product.falabella_category_id:
            raise UserError(_("Debe seleccionar una categoría Falabella."))

        if not product.falabella_category_id.attributesetid:
            raise UserError(_("La categoría seleccionada no tiene AttributeSetId."))

        if not product.list_price:
            raise UserError(_("El producto debe tener precio de venta."))

        mandatory_without_value = product.falabella_attribute_value_ids.filtered(
            lambda l: l.is_mandatory and not l.value
        )

        if mandatory_without_value:
            raise UserError(_(
                "Existen atributos obligatorios sin valor:\n%s"
            ) % "\n".join(mandatory_without_value.mapped("label")))

    def _build_product_payload(self, product):
        return {
            "SellerSku": product.default_code,
            "Name": product.name,
            "PrimaryCategory": product.falabella_category_id.category_id,
            "Brand": product.falabella_brand_id.name,
            "Price": product.list_price,
            "Quantity": int(product.qty_available),
            "Description": product.description_sale or product.name,
        }

    def _build_product_xml_payload(self, product):
        sku = product.default_code or ""
        parent_sku = sku
        name = product.name or ""
        desc = product.description_sale or product.name or ""
        brand = product.falabella_brand_id.name or ""
        category = product.falabella_category_id.category_id
        product_id = product.barcode or ""  # mejor que product.id
        price = product.list_price or 0.0
        qty = int(product.qty_available or 0)

        product_data = []

        product_data.append(self._xml_tag("ConditionType", "Nuevo"))
        product_data.append(self._xml_tag("PackageHeight", product.falabella_package_height or 10))
        product_data.append(self._xml_tag("PackageWidth", product.falabella_package_width or 10))
        product_data.append(self._xml_tag("PackageLength", product.falabella_package_length or 10))
        product_data.append(self._xml_tag("PackageWeight", product.falabella_package_weight or 1))

        # Atributo obligatorio solicitado por Falabella
        if not any(line.attribute_id.name == "AnoFabricacion" and line.value for line in
                   product.falabella_attribute_value_ids):
            product_data.append(self._xml_tag("AnoFabricacion", "2026"))
        for line in product.falabella_attribute_value_ids:
            if line.attribute_id and line.value:
                product_data.append(
                    self._xml_tag(line.attribute_id.name, line.value)
                )

        return f"""<?xml version="1.0" encoding="UTF-8"?>
    <Request>
        <Product>
            {self._xml_tag("SellerSku", sku)}
            {self._xml_tag("ParentSku", parent_sku)}
            {self._xml_tag("Name", name)}
            {self._xml_tag("PrimaryCategory", category)}
            {self._xml_tag("Description", desc, cdata=True)}
            {self._xml_tag("Brand", brand)}
            {self._xml_tag("ProductId", product_id)}

            <BusinessUnits>
                <BusinessUnit>
                    {self._xml_tag("OperatorCode", product.falabella_operator_code or "fape")}
                    {self._xml_tag("Price", price)}
                    {self._xml_tag("Stock", qty)}
                    {self._xml_tag("Status", "active")}
                </BusinessUnit>
            </BusinessUnits>

            <ProductData>
                {''.join(product_data)}
            </ProductData>
        </Product>
    </Request>"""

    def _xml_tag(self, tag, value, cdata=False):
        tag = (tag or "").strip()
        value = "" if value is False or value is None else str(value)

        if cdata:
            return f"<{tag}><![CDATA[{value}]]></{tag}>"

        return f"<{tag}>{escape(value)}</{tag}>"

    def get_feed_status(self, account, feed_id):
        return self._call_api(
            account=account,
            action="FeedStatus",
            method="GET",
            extra_params={
                "FeedID": feed_id,
            },
        )

    def sync_categories_falabella(self, account):
        response = self.get_category_tree(account)

        categories = self._extract_categories_from_response(response)

        Category = self.env["falabella.category"].sudo()

        created = 0
        updated = 0

        for item in categories:
            print("item", item)
            name = item.get("Name")
            category_id = int(item.get("CategoryId") or 0)
            globalidentifier = item.get("GlobalIdentifier") or ''
            parent_id_api = int(item.get("ParentCategoryId") or 0)

            if not category_id or not name:
                continue

            vals = {
                "account_id": account.id,
                "name": name,
                "category_id": category_id,
                "globalidentifier": globalidentifier,
                "attributesetid": int(item.get("AttributeSetId") or 0),
                "parent_category_id_api": parent_id_api,
            }

            category = Category.search([
                ("account_id", "=", account.id),
                ("category_id", "=", category_id),
            ], limit=1)

            if category:
                category.write(vals)
                updated += 1
            else:
                Category.create(vals)
                created += 1

        # Enlazar padres
        all_categories = Category.search([
            ("account_id", "=", account.id)
        ])

        for category in all_categories:
            parent = False

            if category.parent_category_id_api:
                parent = Category.search([
                    ("account_id", "=", account.id),
                    ("category_id", "=", category.parent_category_id_api),
                ], limit=1)

            category.parent_id = parent.id if parent else False

        # Marcar categorías hoja
        all_categories.write({"is_leaf": True})

        parent_categories = Category.search([
            ("account_id", "=", account.id),
            ("child_ids", "!=", False),
        ])

        parent_categories.write({"is_leaf": False})

        return {
            "created": created,
            "updated": updated,
            "total": len(categories),
        }

    def get_category_tree(self, account):
        return self._call_api(
            account=account,
            action="GetCategoryTree",
            method="GET",
        )

    def _extract_attributes_from_response(self, response):
        body = response.get("SuccessResponse", {}).get("Body", {})

        attributes_data = body.get("Attributes", {}).get("Attribute", [])

        if isinstance(attributes_data, dict):
            attributes_data = [attributes_data]

        if not isinstance(attributes_data, list):
            attributes_data = []

        return attributes_data

    def get_products(self, account, extra_params=None):
        return self._call_api(
            account=account,
            action="GetProducts",
            method="GET",
            extra_params=extra_params,
        )

    def send_product(self, account, payload):
        return self._call_api(
            account=account,
            action="CreateProduct",
            method="POST",
            payload=payload,
        )


