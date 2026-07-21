from odoo import models, fields
from odoo.exceptions import UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)

class MeliProductService(models.AbstractModel):
    _name = "meli.product.service"
    _description = "Mercado Libre Product Service"

    def publish_product(self, account, product_template):
        self._validate_basic_data(account, product_template)

        product_variant = product_template.product_variant_id
        print("product_variant", product_variant)
        category = self._get_or_predict_category(account, product_template)
        print("category", category)

        self.env["meli.category.service"].sync_category_attributes(account, category)

        self._validate_required_attributes(product_template, category)
        self._validate_price(product_template, category)

        payload = self._prepare_item_payload(account, product_template, category)
        print("payload", payload)
        _logger.info("Payload Mercado Libre /items: %s", payload)

        response = self.env["meli.service"].post(
            account,
            "/items",
            data=payload,
        )

        self._create_or_update_meli_product(
            account,
            product_variant,
            response,
        )

        return response

    def _validate_basic_data(self, account, product_template):
        if not account:
            raise UserError("No existe cuenta Mercado Libre configurada.")

        if not account.access_token:
            raise UserError("La cuenta Mercado Libre no tiene access token.")

        if not product_template.list_price or product_template.list_price <= 0:
            raise UserError("El producto no tiene precio válido.")

        if product_template.qty_available <= 0:
            raise UserError("El producto no tiene stock disponible.")

        if not product_template.product_variant_id:
            raise UserError("El producto no tiene variante principal.")

    def _get_or_predict_category(self, account, product_template):
        if product_template.meli_category_id:
            return product_template.meli_category_id

        category = self.env["meli.category.service"].predict_category(
            account,
            product_template.name,
        )

        product_template.sudo().write({
            "meli_category_id": category.id,
        })

        return category

    def _validate_price(self, product_template, category):
        # Por ahora validación simple.
        # Luego puedes guardar min_price en meli.category.
        if category.meli_category_id == "MPE127757" and product_template.list_price < 2:
            raise UserError(
                "El precio no es válido para Mercado Libre.\n\n"
                "La categoría exige precio mínimo de S/ 2.00."
            )

    def _validate_required_attributes(self, product_template, category):
        missing = []

        required_attributes = self.env["meli.attribute"].sudo().search([
            ("category_id", "=", category.id),
            ("required", "=", True),
        ])
        print("required_attributes", required_attributes)
        for attr in required_attributes:
            print("product_template", product_template)
            print("attr", attr)
            value = self._get_product_attribute_value(product_template, attr)

            print("value", value)
            if not value:
                missing.append(attr.name)

        if missing:
            raise UserError(
                "Faltan atributos obligatorios para publicar en Mercado Libre:\n\n- "
                + "\n- ".join(missing)
                + "\n\nComplete estos datos en la pestaña Mercado Libre del producto."
            )

    def _get_product_attribute_value(self, product_template, attr):
        print("_get_product_attribute_value")
        attr_id = attr.meli_attribute_id
        print("attr_id:",attr_id)
        mapping = {
            "BRAND": product_template.meli_brand,
            "MODEL": product_template.meli_model or product_template.default_code,
            "COLOR": getattr(product_template, "meli_color", False),
            "BACKPACK_TYPE": getattr(product_template, "meli_backpack_type", False),
        }
        print("mapping:",mapping)

        return mapping.get(attr_id)

    def _prepare_item_payload(self, account, product_template, category):
        attributes = self._prepare_attributes(product_template, category)

        payload = {
            "title": product_template.name[:60],
            "category_id": category.meli_category_id,
            "price": product_template.list_price,
            "currency_id": "PEN",
            "available_quantity": int(product_template.qty_available),
            "buying_mode": "buy_it_now",
            "listing_type_id": "gold_special",
            "condition": "new",
            "pictures": self._prepare_pictures(product_template),
            "attributes": attributes,
        }

        return payload

    def _prepare_attributes(self, product_template, category):
        attributes = []

        category_attributes = self.env["meli.attribute"].sudo().search([
            ("category_id", "=", category.id),
        ])

        for attr in category_attributes:
            value = self._get_product_attribute_value(product_template, attr)

            if value:
                attributes.append({
                    "id": attr.meli_attribute_id,
                    "value_name": value,
                })

        return attributes

    def _prepare_pictures(self, product_template):
        pictures = []

        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")

        if product_template.image_1920:
            pictures.append({
                "source": f"{base_url}/web/image/product.template/{product_template.id}/image_1920"
            })

        return pictures

    def _create_or_update_meli_product(self, account, product_variant, response):
        existing = self.env["meli.product"].sudo().search([
            ("account_id", "=", account.id),
            ("product_id", "=", product_variant.id),
        ], limit=1)

        vals = {
            "product_id": product_variant.id,
            "account_id": account.id,
            "meli_item_id": response.get("id"),
            "status": response.get("status"),
            "title": response.get("title"),
            "price": response.get("price"),
            "available_quantity": response.get("available_quantity"),
            "permalink": response.get("permalink"),
            "last_sync": fields.Datetime.now(),
        }

        if existing:
            existing.write(vals)
        else:
            self.env["meli.product"].sudo().create(vals)

    def sync_items(self, account):
        api = self.env["meli.service"]

        data = api.get(
            account,
            f"/users/{account.meli_user_id}/items/search",
        )

        item_ids = data.get("results", [])

        for item_id in item_ids:
            item_data = api.get(account, f"/items/{item_id}")

            self.env["meli.product"].sudo().create_or_update_from_meli(
                account,
                item_data,
            )

        return data