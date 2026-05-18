# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import RedirectWarning, UserError, ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    date_credit_start = fields.Date(string="Fecha Crédito inicio", default=fields.Datetime.now)
    date_credit_end = fields.Date(string="Fecha Crédito fin")
    amount_credit = fields.Float(string="Monto Crédito")
    desc_credito = fields.Char(compute='_compute_amount_credito')
    is_credit = fields.Boolean(string="Credito")

    def view_info(self):
        print("view_info")

    def _compute_amount_credito(self):
        for rec in self:
            concat=""
            date_credit_start = self.date_credit_start or ""
            date_credit_end = self.date_credit_end or ""
            amount_credit = self.amount_credit or ""
            concat += f" Inicio: {date_credit_start or ''}"
            concat += f" Fin: {date_credit_end or ''}"
            concat += f" Monto: {amount_credit or ''}"
            rec.desc_credito= f" {concat}"
