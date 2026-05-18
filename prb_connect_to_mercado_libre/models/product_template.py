from odoo import models, fields
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = "product.template"
    meli_category_id = fields.Many2one("meli.category", string="Categoría Mercado Libre")
    meli_brand = fields.Char(string="Marca Mercado Libre")
    meli_model = fields.Char(string="Modelo Mercado Libre")

    def action_publish_meli(self):
        self.ensure_one()

        account = self.env["meli.account"].search([], limit=1)

        if not account:
            raise UserError("Configura primero una cuenta Mercado Libre.")

        response = self.env["meli.product.service"].publish_product(
            account,
            self
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Mercado Libre",
                "message": f"Producto publicado: {response.get('id')}",
                "type": "success",
                "sticky": False,
            },
        }
