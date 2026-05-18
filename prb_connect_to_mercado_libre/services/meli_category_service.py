# services/meli_category_service.py
from odoo import models
from odoo.exceptions import UserError


class MeliCategoryService(models.AbstractModel):
    _name = "meli.category.service"
    _description = "Mercado Libre Category Service"

    def predict_category(self, account, product_name):
        data = self.env["meli.service"].get(
            account,
            "/sites/MPE/domain_discovery/search",
            params={"q": product_name},
        )

        if not data:
            raise UserError("Mercado Libre no encontró categoría para este producto.")

        item = data[0]

        category = self.env["meli.category"].sudo().search([
            ("meli_category_id", "=", item.get("category_id"))
        ], limit=1)

        vals = {
            "name": item.get("category_name"),
            "meli_category_id": item.get("category_id"),
            "domain_id": item.get("domain_id"),
            "domain_name": item.get("domain_name"),
            "site_id": "MPE",
        }

        if category:
            category.write(vals)
        else:
            category = self.env["meli.category"].sudo().create(vals)

        return category

    def sync_category_attributes(self, account, category):
        attrs = self.env["meli.service"].get(
            account,
            f"/categories/{category.meli_category_id}/attributes",
        )

        for attr in attrs:
            tags = attr.get("tags") or {}

            existing = self.env["meli.attribute"].sudo().search([
                ("category_id", "=", category.id),
                ("meli_attribute_id", "=", attr.get("id")),
            ], limit=1)

            vals = {
                "category_id": category.id,
                "meli_attribute_id": attr.get("id"),
                "name": attr.get("name"),
                "required": bool(tags.get("required")),
                "value_type": attr.get("value_type"),
            }
            print("sync_category_attributes")
            print("vals", vals)

            if existing:
                existing.write(vals)
            else:
                self.env["meli.attribute"].sudo().create(vals)