from odoo import models, fields
from urllib.parse import urlencode
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MeliPublication(models.Model):
    _name = "meli.publication"
    _description = "Publicación Mercado Libre"

    name = fields.Char(string="Título")
    product_tmpl_id = fields.Many2one("product.template", required=True)
    account_id = fields.Many2one("meli.account", string="Cuenta Mercado Libre", required=True)
    category_id = fields.Many2one(
        "meli.category",
        string="Categoría Mercado Libre",
        required=True,
        domain="[('account_id', '=', account_id), ('is_leaf', '=', True)]",
    )
    attribute_ids = fields.One2many(
        "meli.publication.attribute",
        "publication_id",
        string="Atributos"
    )

    meli_item_id = fields.Char(readonly=True)
    status = fields.Selection([
        ("draft", "Borrador"),
        ("active", "Activo"),
        ("paused", "Pausado"),
        ("closed", "Cerrado"),
        ("error", "Error"),
    ], default="draft")

    listing_type_id = fields.Char(string="Tipo de Publicación", default="gold_special")
    buying_mode = fields.Char(default="buy_it_now")
    condition = fields.Selection([
        ("new", "Nuevo"),
        ("used", "Usado"),
    ], default="new", string="Condición")

    price = fields.Float(string="Precio")
    available_quantity = fields.Integer(string="Stock Disponible")
    currency_id = fields.Char(default="PEN")
    description = fields.Text()

    last_error = fields.Text(readonly=True)

    # método para cargar atributos requeridos
    def action_load_required_attributes(self):
        for rec in self:
            if not rec.category_id:
                raise UserError(_("Debe seleccionar una categoría."))

            rec.attribute_ids.unlink()

            attrs = self.env["meli.attribute"].sudo().search([
                ("category_id", "=", rec.category_id.id),
                ("required", "=", True),
            ])

            lines = []
            for attr in attrs:
                lines.append((0, 0, {
                    "attribute_id": attr.id,
                }))

            rec.attribute_ids = lines

    # método que arma atributos
    def _prepare_meli_attributes(self):
        self.ensure_one()

        attributes = []

        for line in self.attribute_ids:
            if not line.value_name and not line.value_id:
                raise UserError(_("Falta valor para el atributo: %s") % line.attribute_id.name)

            vals = {
                "id": line.attribute_id.meli_attribute_id,
            }

            if line.value_id:
                vals["value_id"] = line.value_id
            else:
                vals["value_name"] = line.value_name

            attributes.append(vals)

        product = self.product_tmpl_id

        if product.default_code:
            attributes.append({
                "id": "SELLER_SKU",
                "value_name": product.default_code,
            })

        return attributes

    # Método para imágenes
    def _prepare_meli_pictures(self):
        self.ensure_one()

        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")

        if not self.product_tmpl_id.image_1920:
            return []

        return [{
            "source": "%s/web/image/product.template/%s/image_1920" % (
                base_url,
                self.product_tmpl_id.id,
            )
        }]

    # Método para payload
    def _prepare_meli_payload(self):
        self.ensure_one()

        self._validate_before_publish()

        payload = {
            "title": self.name or self.product_tmpl_id.name,
            "category_id": self.category_id.meli_category_id,
            "price": self.price,
            "currency_id": self.currency_id or "PEN",
            "available_quantity": self.available_quantity,
            "buying_mode": self.buying_mode or "buy_it_now",
            "condition": self.condition or "new",
            "listing_type_id": self.listing_type_id or "gold_special",
            "attributes": self._prepare_meli_attributes(),
            "pictures": self._prepare_meli_pictures(),
        }

        return payload

    def _validate_before_publish(self):
        self.ensure_one()
        category_info = self.env["meli.service"].get(
            self.account_id,
            f"/categories/{self.category_id.meli_category_id}"
        )

        if not category_info.get("settings", {}).get("leaf"):
            raise UserError(_(
                "La categoría seleccionada no es una categoría final. "
                "Debe seleccionar una subcategoría hoja para publicar."
            ))
        if not self.account_id:
            raise UserError(_("Debe seleccionar una cuenta de Mercado Libre."))

        if not self.category_id:
            raise UserError(_("Debe seleccionar una categoría."))

        if not self.price or self.price <= 0:
            raise UserError(_("El precio debe ser mayor a cero."))

        if not self.available_quantity or self.available_quantity <= 0:
            raise UserError(_("La cantidad disponible debe ser mayor a cero."))

        if not self.attribute_ids:
            raise UserError(_("Debe cargar los atributos de la publicación."))

    # Metodo para publicar
    def action_publish_meli(self):
        for rec in self:
            if rec.meli_item_id:
                raise UserError(_("Este producto ya fue publicado en Mercado Libre."))

            payload = rec._prepare_meli_payload()
            print("payload", payload)
            try:
                response = self.env["meli.service"].post(
                    rec.account_id,
                    "/items",
                    payload
                )

                rec.write({
                    "meli_item_id": response.get("id"),
                    "status": response.get("status") or "active",
                    "last_error": False,
                })

            except Exception as e:
                rec.write({
                    "status": "error",
                    "last_error": str(e),
                })
                raise

        return True


class MeliPublicationAttribute(models.Model):
    _name = "meli.publication.attribute"
    _description = "Atributos Publicación Mercado Libre"

    publication_id = fields.Many2one(
        "meli.publication",
        required=True,
        ondelete="cascade"
    )

    attribute_id = fields.Many2one(
        "meli.attribute",
        required=True
    )

    value_name = fields.Char()
    value_id = fields.Char()
