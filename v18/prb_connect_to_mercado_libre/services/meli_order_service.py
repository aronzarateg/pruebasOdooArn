from odoo import models


class MeliOrderService(models.AbstractModel):
    _name = "meli.order.service"
    _description = "Mercado Libre Order Service"

    def sync_orders(self, account):
        api = self.env["meli.service"]

        data = api.get(
            account,
            "/orders/search",
            params={
                "seller": account.meli_user_id,
            },
        )

        for result in data.get("results", []):
            order_id = str(result.get("id"))
            detail = api.get(account, f"/orders/{order_id}")

            self.env["meli.order"].sudo().create_or_update_from_meli(
                account,
                detail
            )

        return data