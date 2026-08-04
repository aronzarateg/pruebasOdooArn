from odoo import models, fields
from odoo.exceptions import UserError
from datetime import timedelta, datetime
import json
from datetime import timezone
from dateutil import parser


class MeliOrderService(models.AbstractModel):
    _name = "meli.order.service"
    _description = "Mercado Libre Order Service"

    def sync_orders(self, account, date_from=None, date_to=None):
        account.ensure_one()
        now = fields.Datetime.now()
        date_to = date_to or now
        date_from = (
                date_from
                or account.last_order_sync
                # or datetime(2019, 1, 1, 0, 0, 0)
                or now - timedelta(days=1)
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
        print("params", params)
        api = self.env["meli.service"]

        total_processed = 0

        while True:
            data = api.get(
                account,
                "/orders/search",
                params=params,
            )
            '''
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
            '''
            print("data", data)
            results = data.get("results", [])

            print("results", results)

            for order_data in results:
                print("order_data", order_data)

                self._process_order(account, order_data)
                # raise UserError('STOPPPP')
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

    '''
            {
                "payments": [
                    {
                        "reason": "Amazon Echo Dot 5th Gen Asistente Virtual Alexa Negro 2022 Charcoal",
                        "status_code": null,
                        "total_paid_amount": 194,
                        "operation_type": "regular_payment",
                        "transaction_amount": 219,
                        "transaction_amount_refunded": 0,
                        "date_approved": "2026-07-13T01:38:27.000-04:00",
                        "collector": {
                            "id": 1140139223
                        },
                        "coupon_id": null,
                        "installments": 1,
                        "authorization_code": "038681",
                        "taxes_amount": 0,
                        "id": 167683316369,
                        "date_last_modified": "2026-07-13T01:38:27.000-04:00",
                        "coupon_amount": 25,
                        "available_actions": [
                            "refund"
                        ],
                        "shipping_cost": 0,
                        "installment_amount": 194,
                        "date_created": "2026-07-13T01:38:24.000-04:00",
                        "activation_uri": null,
                        "overpaid_amount": 0,
                        "card_id": null,
                        "status_detail": "accredited",
                        "issuer_id": "12759",
                        "payment_method_id": "yape",
                        "payment_type": "debit_card",
                        "deferred_period": null,
                        "atm_transfer_reference": {
                            "transaction_id": "996261948057876",
                            "company_id": null
                        },
                        "site_id": "MPE",
                        "payer_id": 3534861700,
                        "order_id": 2000017388104330,
                        "currency_id": "PEN",
                        "status": "approved",
                        "transaction_order_id": null
                    }
                ],
                "fulfilled": true,
                "taxes": {
                    "amount": null,
                    "currency_id": null,
                    "id": null
                },
                "order_request": {
                    "change": null,
                    "return": null
                },
                "expiration_date": "2026-08-03T01:38:27.000-04:00",
                "feedback": {
                    "purchase": {
                        "date_created": "2026-07-14T04:13:13.000-04:00",
                        "fulfilled": true,
                        "rating": "positive",
                        "id": 9042103244167,
                        "status": "active"
                    },
                    "buyer": {
                        "id": 9042103244167
                    },
                    "seller": null
                },
                "shipping": {
                    "id": 47510758866
                },
                "date_closed": "2026-07-13T01:38:27.000-04:00",
                "id": 2000017388104330,
                "manufacturing_ending_date": null,
                "order_items": [
                    {
                        "item": {
                            "id": "MPE624445085",
                            "title": "Amazon Echo Dot 5th Gen Asistente Virtual Alexa Negro 2022 Charcoal",
                            "category_id": "MPE409415",
                            "variation_id": null,
                            "seller_custom_field": null,
                            "global_price": null,
                            "net_weight": null,
                            "variation_attributes": [
                                {
                                    "name": "Color",
                                    "id": "COLOR",
                                    "value_id": "2790167",
                                    "value_name": "Charcoal"
                                }
                            ],
                            "warranty": "Garantía de fábrica: 12 meses",
                            "condition": "new",
                            "seller_sku": "2021956-15"
                        },
                        "quantity": 1,
                        "unit_price": 219,
                        "gross_price": 299,
                        "currency_id": "PEN",
                        "manufacturing_days": null,
                        "picked_quantity": null,
                        "requested_quantity": {
                            "measure": "unit",
                            "value": 1
                        },
                        "sale_fee": 21.9,
                        "listing_type_id": "bronze",
                        "base_exchange_rate": null,
                        "base_currency_id": null,
                        "bundle": null,
                        "element_id": 1,
                        "stock": {
                            "node_id": "PEP11401392231",
                            "store_id": null
                        }
                    }
                ],
                "date_last_updated": "2026-08-03T17:41:52+00:00",
                "last_updated": "2026-08-03T01:50:55.000-04:00",
                "comment": null,
                "pack_id": null,
                "coupon": {
                    "amount": 25,
                    "id": null
                },
                "shipping_cost": null,
                "date_created": "2026-07-13T01:38:24.000-04:00",
                "date_created_ttl": null,
                "pickup_id": null,
                "status_detail": null,
                "tags": [
                    "order_has_discount",
                    "new_buyer_free_shipping",
                    "paid",
                    "delivered"
                ],
                "static_tags": [],
                "buyer": {
                    "id": 3534861700,
                    "nickname": "JB20260710153628"
                },
                "seller": {
                    "id": 1140139223,
                    "nickname": "KUZLER STORE"
                },
                "total_amount": 219,
                "paid_amount": 219,
                "currency_id": "PEN",
                "status": "paid",
                "context": {
                    "application": null,
                    "product_id": null,
                    "channel": "marketplace",
                    "site": "MPE",
                    "flows": [
                        "new_buyer_free_shipping"
                    ]
                }
            }
            '''

    def _process_order(self, account, order_data):
        """
        Crea o actualiza la orden local junto con sus productos y pagos.
        """
        order_id = str(order_data.get("id") or "")

        if not order_id:
            return False

        order = self.env["meli.order"].search([
            ("account_id", "=", account.id),
            ("meli_order_id", "=", order_id),
        ], limit=1)

        vals = self._prepare_order_vals(account=account, order_data=order_data, )

        line_commands = [(5, 0, 0)]

        for order_item in order_data.get("order_items") or []:
            line_vals = self._prepare_order_line_vals(order_item)

            if line_vals.get("item_id"):
                line_commands.append((0, 0, line_vals))

        payment_commands = [(5, 0, 0)]

        for payment_data in order_data.get("payments") or []:
            payment_vals = self._prepare_payment_vals(payment_data)

            if payment_vals.get("payment_id"):
                payment_commands.append((0, 0, payment_vals))

        vals.update({
            "line_ids": line_commands,
            "payment_ids": payment_commands,
        })

        if order:
            order.write(vals)
        else:
            order = self.env["meli.order"].create(vals)

        return order

    def _prepare_order_vals(self, account, order_data):
        buyer_data = order_data.get("buyer") or {}
        seller_data = order_data.get("seller") or {}
        shipping_data = order_data.get("shipping") or {}
        coupon_data = order_data.get("coupon") or {}

        tags = order_data.get("tags") or []

        billing_info_data = buyer_data.get("billing_info") or {}

        print("account:", account)
        return {
            "account_id": account.id,
            "meli_order_id": str(order_data.get("id") or ""),
            "status": order_data.get("status"),
            "status_detail": order_data.get("status_detail"),

            "buyer_id": str(buyer_data.get("id") or ""),
            "buyer_nickname": buyer_data.get("nickname"),
            "billing_info_id": str(
                billing_info_data.get("id") or ""
            ),
            #"site_id": account.site_id,

            "seller_id": str(seller_data.get("id") or ""),
            "seller_nickname": seller_data.get("nickname"),

            "currency_code": order_data.get("currency_id"),

            "total_amount": order_data.get("total_amount") or 0.0,
            "paid_amount": order_data.get("paid_amount") or 0.0,
            "coupon_amount": coupon_data.get("amount") or 0.0,
            "shipping_cost": order_data.get("shipping_cost") or 0.0,

            "fulfilled": bool(order_data.get("fulfilled")),
            "shipping_id": str(shipping_data.get("id") or ""),

            "date_created": self._parse_meli_datetime(
                order_data.get("date_created")
            ),
            "date_closed": self._parse_meli_datetime(
                order_data.get("date_closed")
            ),
            "date_last_updated": self._parse_meli_datetime(
                order_data.get("last_updated")
                or order_data.get("date_last_updated")
            ),
            "expiration_date": self._parse_meli_datetime(
                order_data.get("expiration_date")
            ),

            "tag_names": ", ".join(tags),

            "raw_data": json.dumps(
                order_data,
                ensure_ascii=False,
                indent=4,
            ),
        }

    def _prepare_order_line_vals(self, order_item):
        item_data = order_item.get("item") or {}
        variation_attributes = item_data.get("variation_attributes") or []

        variation_parts = []

        for attribute in variation_attributes:
            name = attribute.get("name")
            value = attribute.get("value_name")

            if name and value:
                variation_parts.append("%s: %s" % (name, value))

        return {
            "item_id": str(item_data.get("id") or ""),
            "seller_sku": item_data.get("seller_sku"),
            "title": item_data.get("title"),
            "category_id": item_data.get("category_id"),
            "variation_id": (
                str(item_data.get("variation_id"))
                if item_data.get("variation_id")
                else False
            ),
            "variation_description": ", ".join(variation_parts),
            "condition": item_data.get("condition"),
            "warranty": item_data.get("warranty"),

            "quantity": order_item.get("quantity") or 0.0,
            "unit_price": order_item.get("unit_price") or 0.0,
            "gross_price": order_item.get("gross_price") or 0.0,
            "sale_fee": order_item.get("sale_fee") or 0.0,
            "currency_code": order_item.get("currency_id"),
        }

    def _prepare_payment_vals(self, payment_data):
        return {
            "payment_id": str(payment_data.get("id") or ""),
            "status": payment_data.get("status"),
            "status_detail": payment_data.get("status_detail"),
            "payment_method_id": payment_data.get("payment_method_id"),
            "payment_type": payment_data.get("payment_type"),
            "currency_code": payment_data.get("currency_id"),

            "transaction_amount": (
                    payment_data.get("transaction_amount") or 0.0
            ),
            "total_paid_amount": (
                    payment_data.get("total_paid_amount") or 0.0
            ),
            "coupon_amount": payment_data.get("coupon_amount") or 0.0,
            "shipping_cost": payment_data.get("shipping_cost") or 0.0,

            "installments": payment_data.get("installments") or 0,
            "authorization_code": payment_data.get("authorization_code"),

            "date_created": self._parse_meli_datetime(
                payment_data.get("date_created")
            ),
            "date_approved": self._parse_meli_datetime(
                payment_data.get("date_approved")
            ),
        }

    def _parse_meli_datetime(self, value):
        if not value:
            return False

        try:
            parsed_date = parser.isoparse(value)

            if parsed_date.tzinfo:
                parsed_date = parsed_date.astimezone(
                    timezone.utc
                ).replace(tzinfo=None)

            return fields.Datetime.to_string(parsed_date)
        except (ValueError, TypeError):
            return False

    def _format_meli_datetime(self, value):
        """
        Convierte datetime de Odoo al formato ISO solicitado por Mercado Libre.

        Ejemplo:
        2026-07-22T10:30:00.000-05:00
        """
        value = fields.Datetime.to_datetime(value)

        return value.strftime("%Y-%m-%dT%H:%M:%S.000-00:00")
