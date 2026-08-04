from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    meli_buyer_id = fields.Char(
        string="ID comprador Mercado Libre",
        index=True,
        copy=False,
    )