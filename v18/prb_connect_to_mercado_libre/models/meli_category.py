from odoo import models, fields


class MeliCategory(models.Model):
    _name = "meli.category"
    _description = "Categoría Mercado Libre"

    name = fields.Char(required=True)
    meli_category_id = fields.Char(required=True, index=True)
    domain_id = fields.Char()
    domain_name = fields.Char()
    site_id = fields.Char(default="MPE")
    odoo_category_id = fields.Many2one("product.category")
class MeliAttribute(models.Model):
    _name = "meli.attribute"
    _description = "Atributo Mercado Libre"

    category_id = fields.Many2one("meli.category", required=True)
    meli_attribute_id = fields.Char(required=True)
    name = fields.Char(required=True)
    required = fields.Boolean()
    value_type = fields.Char()