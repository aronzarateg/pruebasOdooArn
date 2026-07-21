# -*- coding: utf-8 -*-

from odoo import models, fields


class FalabellaCategoryAttribute(models.Model):
    _name = "falabella.category.attribute"
    _description = "Atributo de Categoría Falabella"

    account_id = fields.Many2one("falabella.account", required=True)
    category_id = fields.Many2one("falabella.category", required=True, ondelete="cascade")

    name = fields.Char(required=True)
    label = fields.Char()
    is_mandatory = fields.Boolean()
    attribute_type = fields.Char()
    input_type = fields.Char()
class ProductFalabellaAttributeValue(models.Model):
    _name = "product.falabella.attribute.value"
    _description = "Valor atributo Falabella por producto"

    product_tmpl_id = fields.Many2one(
        "product.template",
        required=True,
        ondelete="cascade"
    )

    attribute_id = fields.Many2one(
        "falabella.category.attribute",
        required=True
    )

    name = fields.Char(related="attribute_id.name", store=True)
    label = fields.Char(related="attribute_id.label", store=True)
    is_mandatory = fields.Boolean(related="attribute_id.is_mandatory", store=True)

    value = fields.Char(string="Valor")
