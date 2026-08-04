from odoo import models, fields


class MeliOrderPayment(models.Model):
    _name = "meli.order.payment"
    _description = "Pago de orden Mercado Libre"

    order_id = fields.Many2one("meli.order", string="Orden", required=True, ondelete="cascade", index=True)
    payment_id = fields.Char(string="ID pago", required=True, index=True)
    status = fields.Char(string="Estado")
    status_detail = fields.Char(string="Detalle del estado")
    payment_method_id = fields.Char(string="Método de pago")
    payment_type = fields.Char(string="Tipo de pago")
    currency_code = fields.Char(string="Moneda", size=3)
    transaction_amount = fields.Float(string="Monto de transacción")
    total_paid_amount = fields.Float(string="Total pagado")
    coupon_amount = fields.Float(string="Cupón")
    shipping_cost = fields.Float(string="Costo de envío")
    installments = fields.Integer(string="Cuotas")
    authorization_code = fields.Char(string="Código de autorización")
    date_created = fields.Datetime(string="Fecha de creación")
    date_approved = fields.Datetime(string="Fecha de aprobación")

    _sql_constraints = [
        (
            "meli_payment_order_unique",
            "unique(payment_id, order_id)",
            "El pago ya está registrado en esta orden.",
        ),
    ]
