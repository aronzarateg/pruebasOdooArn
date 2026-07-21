from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class MeliCategoryService(models.AbstractModel):
    _name = "meli.category.service"
    _description = "Mercado Libre Category Service"

    def sync_categories(self, account):
        site_id = account.site_id or "MPE"

        categories = self.env["meli.service"].get(
            account,
            f"/sites/{site_id}/categories",
        ) or []

        total_created = 0
        total_updated = 0

        for cat in categories:
            result = self.sync_category_tree(
                account,
                cat.get("id"),
                parent=False,
            )

            total_created += result.get("created", 0)
            total_updated += result.get("updated", 0)

        return {
            "created": total_created,
            "updated": total_updated,
            "total": total_created + total_updated,
        }

    def sync_category_tree(self, account, category_id, parent=False):
        if not category_id:
            return {
                "created": 0,
                "updated": 0,
            }

        data = self.env["meli.service"].get(
            account,
            f"/categories/{category_id}",
        ) or {}

        category, created = self._create_or_update_category(
            account,
            data,
            parent=parent,
        )

        if not category:
            return {
                "created": 0,
                "updated": 0,
            }

        total_created = 1 if created else 0
        total_updated = 0 if created else 1

        for child in data.get("children_categories", []):
            result = self.sync_category_tree(
                account,
                child.get("id"),
                parent=category,
            )

            total_created += result.get("created", 0)
            total_updated += result.get("updated", 0)

        return {
            "created": total_created,
            "updated": total_updated,
        }

    def sync_all_category_attributes(self, account, limit=50):
        categories = self.env["meli.category"].sudo().search([
            ("account_id", "=", account.id),
            ("is_leaf", "=", True),
            ("attributes_synced", "=", False),
        ], limit=limit)

        total_attributes = 0
        total_categories = 0

        for category in categories:
            try:
                total_attributes += self.sync_category_attributes(account, category)

                category.write({
                    "attributes_synced": True,
                    "last_attributes_sync": fields.Datetime.now(),
                })

                total_categories += 1

                self.env.cr.commit()

            except Exception as e:
                self.env.cr.rollback()
                _logger.exception(
                    "Error sincronizando atributos MELI categoría %s: %s",
                    category.meli_category_id,
                    e,
                )

        return {
            "attributes": total_attributes,
            "categories": total_categories,
        }

    def sync_category_attributes(self, account, category):
        attrs = self._meli_get_category_attributes(account, category)

        total = 0

        for attr in attrs:
            self._create_or_update_attribute(category, attr)
            total += 1

        return total

    def sync_all_brands(self, account, limit=50):
        categories = self.env["meli.category"].sudo().search([
            ("account_id", "=", account.id),
            ("is_leaf", "=", True),
            ("attributes_synced", "=", True),
            ("brands_synced", "=", False),
        ], limit=limit)

        total_brands = 0
        total_categories = 0

        for category in categories:
            try:
                brand_attr = self.env["meli.attribute"].sudo().search([
                    ("category_id", "=", category.id),
                    ("meli_attribute_id", "=", "BRAND"),
                ], limit=1)

                if brand_attr:
                    total_brands += self._sync_brand_attribute_values(
                        account,
                        category,
                        brand_attr,
                    )

                category.write({
                    "brands_synced": True,
                    "last_brands_sync": fields.Datetime.now(),
                })

                total_categories += 1

                self.env.cr.commit()

            except Exception as e:
                self.env.cr.rollback()
                _logger.exception(
                    "Error sincronizando marcas MELI categoría %s: %s",
                    category.meli_category_id,
                    e,
                )

        return {
            "brands": total_brands,
            "categories": total_categories,
        }

    def _meli_get_category_attributes(self, account, category):
        return self.env["meli.service"].get(
            account,
            f"/categories/{category.meli_category_id}/attributes",
        ) or []

    def _meli_discover_domain(self, account, category):
        site_id = account.site_id or "MPE"

        category_data = self.env["meli.service"].get(
            account,
            f"/sites/{site_id}/domain_discovery/search?q={category.name}",
        ) or []

        if category_data:
            return category_data[0].get("domain_id")

        return False

    def _meli_get_brand_top_values(self, account, domain_id):
        try:
            return self.env["meli.service"].post(
                account,
                f"/catalog_domains/{domain_id}/attributes/BRAND/top_values",
                {
                    "known_attributes": [],
                },
            ) or []
        except Exception as e:
            _logger.exception("Error obteniendo top brands MELI: %s", e)
            return []

    def _sync_brand_attribute_values(self, account, category, brand_attr):
        total = 0

        total += self._sync_brand_values_from_attribute(category, brand_attr)

        domain_id = self._meli_discover_domain(account, category)

        if not domain_id:
            return total

        brands = self._meli_get_brand_top_values(account, domain_id)

        for brand in brands:
            created_or_updated = self._create_or_update_brand(
                category,
                brand,
                domain_id,
            )

            if created_or_updated:
                total += 1

        return total

    def _sync_brand_values_from_attribute(self, category, brand_attr):
        total = 0

        values = []

        if hasattr(brand_attr, "raw_values"):
            values = brand_attr.raw_values or []

        for value in values:
            created_or_updated = self._create_or_update_brand(
                category,
                {
                    "id": value.get("id"),
                    "name": value.get("name"),
                },
                domain_id=False,
            )

            if created_or_updated:
                total += 1

        return total

    def _create_or_update_category(self, account, data, parent=False):
        meli_category_id = data.get("id")
        name = data.get("name")

        if not meli_category_id:
            return False, False

        Category = self.env["meli.category"].sudo()

        existing = Category.search([
            ("account_id", "=", account.id),
            ("meli_category_id", "=", meli_category_id),
        ], limit=1)

        vals = {
            "account_id": account.id,
            "meli_category_id": meli_category_id,
            "name": name,
            "parent_id": parent.id if parent else False,
            "is_leaf": data.get("settings", {}).get("leaf", False),
            "path_from_root": " / ".join([
                x.get("name", "")
                for x in data.get("path_from_root", [])
                if x.get("name")
            ]),
        }

        if existing:
            existing.write(vals)
            return existing, False

        return Category.create(vals), True

    def _create_or_update_attribute(self, category, attr):
        tags = attr.get("tags") or {}

        Attribute = self.env["meli.attribute"].sudo()

        existing = Attribute.search([
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

        if existing:
            existing.write(vals)
            return existing

        return Attribute.create(vals)

    def _create_or_update_brand(self, category, brand, domain_id=False):
        if not brand.get("name"):
            return False

        Brand = self.env["meli.brand"].sudo()

        if brand.get("id"):
            domain = [
                ("category_id", "=", category.id),
                ("meli_id", "=", brand.get("id")),
            ]
        else:
            domain = [
                ("category_id", "=", category.id),
                ("name", "=", brand.get("name")),
            ]

        existing = Brand.search(domain, limit=1)

        vals = {
            "name": brand.get("name"),
            "meli_id": brand.get("id") or False,
            "domain_id": domain_id or False,
            "category_id": category.id,
        }

        if existing:
            existing.write(vals)
            return existing

        return Brand.create(vals)