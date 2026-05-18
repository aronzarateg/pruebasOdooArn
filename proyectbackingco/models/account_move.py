# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import RedirectWarning, UserError, ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        print("AccountMove action_post")
        if self.partner_id.is_credit:
            self.env.cr.execute(
                """select account_move.id, account_move.name, account_move.amount_total, res_partner.amount_credit
                   from account_move
                            inner join
                        res_partner on res_partner.id = account_move.partner_id
                   where account_move.partner_id = %s
                     and account_move.state = 'posted'
                     and account_move.invoice_date BETWEEN %s AND %s  """,
                (self.partner_id.id, self.partner_id.date_credit_start, self.partner_id.date_credit_end,)
                )
            detail_account = self.env.cr.dictfetchall()
            print("detail_account", detail_account)
            vfl_total = 0.0
            vfl_credito = 0.0
            for detail in detail_account:
                vfl_total += detail['amount_total']
                vfl_credito = detail['amount_credit']
            if vfl_total > vfl_credito:
                print("el total es mayor al credito", vfl_total)
                raise ValidationError(
                    _("Las facturas confirmadas para: %r exceden su crédito: %r.", self.partner_id.name, vfl_credito))
        res = super(AccountMove, self).action_post()
        return res
