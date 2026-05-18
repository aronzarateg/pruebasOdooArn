# -*- coding: utf-8 -*-

from odoo import models, fields


class FalabellaBrand(models.Model):
    _name = "falabella.brand"
    _description = "Marca Falabella"
    _rec_name = "name"

    account_id = fields.Many2one(
        "falabella.account",
        string="Cuenta Falabella",
        required=True,
        ondelete="cascade",
    )

    brand_id = fields.Integer(
        string="Brand ID",
        index=True,
    )

    name = fields.Char(
        string="Nombre",
        required=True,
        index=True,
    )

    global_identifier = fields.Char(
        string="Global Identifier",
    )

    raw_xml = fields.Text(
        string="XML / Respuesta original",
    )

    active = fields.Boolean(
        string="Activo",
        default=True,
    )

    _sql_constraints = [
        (
            "unique_brand_account",
            "unique(account_id, brand_id)",
            "La marca ya existe para esta cuenta.",
        )
    ]