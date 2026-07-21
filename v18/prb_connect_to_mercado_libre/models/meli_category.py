from odoo import models, fields


class MeliCategory(models.Model):
    _name = "meli.category"
    _description = "Categoría Mercado Libre"
    _rec_name = "path_from_root"

    name = fields.Char(required=True)
    meli_category_id = fields.Char(required=True, index=True)

    domain_id = fields.Char()
    domain_name = fields.Char()
    active = fields.Boolean(default=True)

    account_id = fields.Many2one(
        "meli.account",
        string="Cuenta MELI",
        required=True,
        ondelete="cascade",
    )

    parent_id = fields.Many2one(
        "meli.category",
        string="Categoría padre",
        ondelete="cascade",
    )

    child_ids = fields.One2many(
        "meli.category",
        "parent_id",
        string="Subcategorías",
    )

    odoo_category_id = fields.Many2one("product.category")

    is_leaf = fields.Boolean(string="Categoría final", default=False)
    path_from_root = fields.Char(string="Ruta categoría")

    attributes_synced = fields.Boolean(
        string="Atributos sincronizados",
        default=False,
    )

    last_attributes_sync = fields.Datetime(
        string="Última sincronización atributos",
    )

    brands_synced = fields.Boolean(
        string="Marcas sincronizadas",
        default=False,
    )

    last_brands_sync = fields.Datetime(
        string="Última sincronización marcas",
    )


class MeliAttribute(models.Model):
    _name = "meli.attribute"
    _description = "Atributo Mercado Libre"

    category_id = fields.Many2one(
        "meli.category",
        required=True,
        ondelete="cascade",
    )

    meli_attribute_id = fields.Char(required=True, index=True)
    name = fields.Char(required=True)
    required = fields.Boolean()
    value_type = fields.Char()


class MeliBrand(models.Model):
    _name = "meli.brand"
    _description = "Marca Mercado Libre"

    name = fields.Char(required=True)
    meli_id = fields.Char(index=True)
    domain_id = fields.Char(index=True)

    category_id = fields.Many2one(
        "meli.category",
        string="Categoría",
        ondelete="cascade",
    )

    active = fields.Boolean(default=True)