
from odoo import models, _
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)


class FalabellaApiService(models.AbstractModel):
    _name = "falabella.api.service.orders"
    _description = "Servicio API Falabella Seller Center Ordenes"

    def get_orders(self, account, extra_params=None):
        return self.env["falabella.api.service"]._call_api(
            account=account,
            action="GetOrders",
            method="GET",
            extra_params=extra_params or {},
        )


    def get_order_items(self, account, order_id):
        return self.env["falabella.api.service"]._call_api(
            account=account,
            action="GetOrderItems",
            method="GET",
            extra_params={
                "OrderId": order_id,
            },
        )