from odoo import models, fields
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = "product.template"
    meli_publication_ids = fields.One2many(
        "meli.publication",
        "product_tmpl_id",
        string="Publicaciones ML"
    )

    publication_count = fields.Integer(
        compute="_compute_publication_count"
    )

    def _compute_publication_count(self):
        for rec in self:
            rec.publication_count = len(rec.meli_publication_ids)

    def action_open_meli_publications(self):
        self.ensure_one()

        return {
            "type": "ir.actions.act_window",
            "name": "Publicaciones Mercado Libre",
            "res_model": "meli.publication",
            "view_mode": "list,form",
            "domain": [
                ("product_tmpl_id", "=", self.id)
            ],
            "context": {
                "default_product_tmpl_id": self.id,
            }
        }

    def action_create_meli_publication(self):
        self.ensure_one()

        return {
            "type": "ir.actions.act_window",
            "name": "Crear Publicación ML",
            "res_model": "meli.publication",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_name": self.name,
                "default_product_tmpl_id": self.id,
            },
        }