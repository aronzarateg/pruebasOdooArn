# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, ValidationError, UserError

class FalabellaCategory(models.Model):
    _name = "falabella.category"
    _description = "Categoría Falabella"

    account_id = fields.Many2one("falabella.account", string="Cuenta", required=True, ondelete="cascade", )

    name = fields.Char(string="Nombre", required=True, )
    globalidentifier = fields.Char(string="Identificador unico", )
    category_id = fields.Integer(string="ID Categoría Falabella", required=True, index=True, )
    attributesetid = fields.Integer(string="ID AttributeSet", )



    parent_category_id_api = fields.Integer(string="ID Categoría Padre Falabella", )
    parent_id = fields.Many2one("falabella.category", string="Categoría Padre")
    child_ids = fields.One2many("falabella.category", "parent_id", string="Subcategorías")
    is_leaf = fields.Boolean(string="Categoría final", default=True)
    active = fields.Boolean(string="Activo", default=True, )

    attribute_ids = fields.One2many(
        "falabella.category.attribute",
        "category_id",
        string="Atributos"
    )

    allow_variations = fields.Boolean(
        string="Permite variaciones",
        compute="_compute_allow_variations",
        store=True,
    )
    _sql_constraints = [
        (
            "falabella_category_unique",
            "unique(account_id, category_id)",
            "La categoría ya existe para esta cuenta.",
        )
    ]

    def _compute_allow_variations(self):
        for category in self:
            attrs = category.attribute_ids.filtered(
                lambda a: (a.name or "").lower() in [
                    "variation",
                    "color",
                    "size",
                    "talla",
                ] or (a.attribute_type or "").lower() == "variation"
            )
            category.allow_variations = bool(attrs)

