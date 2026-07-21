import json
from odoo import models, fields, _
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    falabella_brand_id = fields.Many2one("falabella.brand", string="Marca Falabella")
    falabella_category_id = fields.Many2one("falabella.category", string="Categoría Falabella")
    falabella_account_id = fields.Many2one(
        "falabella.account",
        string="Cuenta Falabella",
    )
    falabella_status = fields.Selection([
        ("draft", "Borrador"),
        ("published", "Publicado"),
        ("error", "Error"),
    ], default="draft", string="Estado Falabella")

    falabella_item_id = fields.Char(string="Item ID Falabella")
    falabella_request_id = fields.Char("Request ID")
    falabella_response = fields.Text(string="Respuesta Falabella")
    falabella_operator_code = fields.Selection([
        ("fape", "Falabella Perú"),
        ("facl", "Falabella Chile"),
        ("faco", "Falabella Colombia"),
    ], string="Operator Code", default="fape")

    falabella_package_height = fields.Float(string="Alto paquete cm", default=10)
    falabella_package_width = fields.Float(string="Ancho paquete cm", default=10)
    falabella_package_length = fields.Float(string="Largo paquete cm", default=10)
    falabella_package_weight = fields.Float(string="Peso paquete kg", default=1)
    falabella_attribute_value_ids = fields.One2many(
        "product.falabella.attribute.value",
        "product_tmpl_id",
        string="Atributos Falabella"
    )
    def action_publish_falabella(self):
        for product in self:
            if not product.falabella_account_id:
                raise UserError(_("Debe seleccionar una cuenta Falabella."))

            result = self.env["falabella.api.service"].publish_product(product)

            product.write({
                "falabella_status": "draft" if result.get("success") else "error",
                "falabella_response": json.dumps(result, indent=4, ensure_ascii=False),
                "falabella_request_id": result.get("request_id"),
                "falabella_item_id": False,
            })

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Falabella"),
                "message": _("Producto enviado a Falabella."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_check_falabella_feed(self):
        for product in self:
            if not product.falabella_account_id:
                raise UserError(_("Debe seleccionar una cuenta Falabella."))

            if not product.falabella_request_id:
                raise UserError(_("No existe Request ID / Feed ID para consultar."))

            response = self.env["falabella.api.service"].get_feed_status(
                product.falabella_account_id,
                product.falabella_request_id,
            )

            product.falabella_response = json.dumps(
                response,
                indent=4,
                ensure_ascii=False,
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Falabella"),
                "message": _("Estado del feed consultado."),
                "type": "success",
                "sticky": False,
            },
        }
    def action_sync_falabella_attributes(self):
        for product in self:
            if not product.falabella_account_id:
                raise UserError(_("Debe seleccionar una cuenta Falabella."))

            if not product.falabella_category_id:
                raise UserError(_("Debe seleccionar una categoría Falabella."))

            self.env["falabella.api.service"].sync_category_attributes(
                product.falabella_account_id,
                product.falabella_category_id
            )