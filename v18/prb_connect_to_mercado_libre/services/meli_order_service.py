from odoo import models, fields
from odoo.exceptions import UserError
from datetime import timedelta,datetime



class MeliOrderService(models.AbstractModel):
    _name = "meli.order.service"
    _description = "Mercado Libre Order Service"

    def sync_orders(self, account, date_from=None, date_to=None):
        """
        Sincroniza órdenes de una cuenta.

        Si no se envían fechas:
        - date_to será la fecha actual.
        - date_from será last_order_sync.
        - Si nunca sincronizó, se consulta un día hacia atrás.
        """
        account.ensure_one()

        now = fields.Datetime.now()

        date_to = date_to or now
        date_from = (
            date_from
            or account.last_order_sync
            or datetime(2019, 1, 1, 0, 0, 0)
            #or now - timedelta(days=1)
        )

        params = {
            "seller": account.meli_user_id,
            "order.date_last_updated.from": self._format_meli_datetime(
                date_from
            ),
            "order.date_last_updated.to": self._format_meli_datetime(
                date_to
            ),
            "sort": "date_asc",
            "limit": 50,
            "offset": 0,
        }
        api = self.env["meli.service"]

        total_processed = 0

        while True:
            #data = api.get(
            #    account,
            #    "/orders/search",
            #    params=params,
            #)
            #---------------------------------------- OPCIONAL PARA REVISAR  ----------------------------
            # 1. Obtener el usuario propietario del access token
            user_data = api.get(
                account,
                "/users/me",
            )

            token_user_id = str(user_data.get("id") or "")
            stored_user_id = str(account.meli_user_id or "")
            print("token_user_id", token_user_id)
            print("token_user_nickname", user_data.get("nickname"))
            print("token_user_site_id", user_data.get("site_id"))
            print("stored_user_id", stored_user_id)

            data = api.get(
                account,
                "/orders/search",
                params={
                    "seller": account.meli_user_id,
                    "sort": "date_desc",
                    "limit": 50,
                },
            )
            items_data = api.get(
                account,
                "/users/{}/items/search".format(account.meli_user_id),
                params={
                    "status": "active",
                    "limit": 50,
                },
            )

            print("PUBLICACIONES", items_data)
            #----------------------------------------------------------------------------

            print("data", data)
            results = data.get("results", [])

            print("results", results)
            raise UserError('STOPPPP')
            for order_data in results:
                self._process_order(account, order_data)
                total_processed += 1

            paging = data.get("paging", {})
            total = paging.get("total", 0)
            offset = paging.get("offset", params["offset"])
            limit = paging.get("limit", params["limit"])

            next_offset = offset + limit

            if not results or next_offset >= total:
                break

            params["offset"] = next_offset

        account.sudo().write({
            "last_order_sync": date_to,
        })

        return {
            "total_processed": total_processed,
            "date_from": date_from,
            "date_to": date_to,
        }

    def _process_order(self, account, order_data):
        """
        Crear o actualizar la orden local.
        """
        order_id = str(order_data.get("id") or "")

        if not order_id:
            return False

        order = self.env["meli.order"].search([
            ("account_id", "=", account.id),
            ("meli_order_id", "=", order_id),
        ], limit=1)

        vals = self._prepare_order_vals(
            account=account,
            order_data=order_data,
        )

        if order:
            order.write(vals)
        else:
            order = self.env["meli.order"].create(vals)

        return order

    def _prepare_order_vals(self, account, order_data):
        return {
            "account_id": account.id,
            "meli_order_id": str(order_data.get("id") or ""),
            "status": order_data.get("status"),
            "date_created": order_data.get("date_created"),
            "date_last_updated": order_data.get("last_updated"),
            "total_amount": order_data.get("total_amount", 0.0),
        }

    def _format_meli_datetime(self, value):
        """
        Convierte datetime de Odoo al formato ISO solicitado por Mercado Libre.

        Ejemplo:
        2026-07-22T10:30:00.000-05:00
        """
        value = fields.Datetime.to_datetime(value)

        return value.strftime("%Y-%m-%dT%H:%M:%S.000-00:00")