from odoo import api, fields, models
from odoo.exceptions import ValidationError
import json

class ShopifyOrder(models.Model):
    _name = "shopify.order"
    _description = "Orden Shopify"

    account_id = fields.Many2one(
        "shopify.account",
        required=True,
        ondelete="cascade",
    )
    shopify_order_id = fields.Char(
        required=True,
        index=True,
    )

    name = fields.Char()
    financial_status = fields.Char()
    fulfillment_status = fields.Char()
    cancelled_at = fields.Datetime()
    shopify_updated_at = fields.Datetime()
    payload = fields.Text()

    _sql_constraints = [
        (
            "shopify_order_account_unique",
            "unique(account_id, shopify_order_id)",
            "La orden Shopify ya existe para esta cuenta.",
        ),
    ]

    @api.model
    def create_or_update_from_shopify(
        self,
        account,
        data,
    ):
        order_id = str(data.get("id") or "")

        if not order_id:
            raise ValidationError(
                "Shopify no devolvió el ID de la orden."
            )

        vals = {
            "name": data.get("name"),
            "financial_status": data.get("financial_status"),
            "fulfillment_status": data.get(
                "fulfillment_status"
            ),
            "cancelled_at": data.get("cancelled_at") or False,
            "shopify_updated_at": (
                data.get("updated_at") or False
            ),
            "payload": json.dumps(
                data,
                ensure_ascii=False,
                default=str,
            ),
        }

        order = self.sudo().search([
            ("account_id", "=", account.id),
            ("shopify_order_id", "=", order_id),
        ], limit=1)

        if order:
            order.write(vals)
            return order

        vals.update({
            "account_id": account.id,
            "shopify_order_id": order_id,
        })

        return self.sudo().create(vals)

    def _process_inventory_level(self, payload):
        self.ensure_one()

        inventory_item_id = str(
            payload.get("inventory_item_id") or ""
        )
        location_id = str(
            payload.get("location_id") or ""
        )

        available = payload.get("available")

        if not inventory_item_id or not location_id:
            raise ValueError(
                "La notificación de inventario no contiene "
                "inventory_item_id o location_id."
            )

        product = self.env["product.product"].sudo().search([
            (
                "shopify_inventory_item_id",
                "=",
                inventory_item_id,
            ),
        ], limit=1)

        if not product:
            raise ValueError(
                "No existe un producto Odoo asociado al "
                "inventory_item_id %s."
                % inventory_item_id
            )

        location_mapping = self.env[
            "shopify.location"
        ].sudo().search([
            ("account_id", "=", self.account_id.id),
            ("shopify_location_id", "=", location_id),
        ], limit=1)

        if not location_mapping:
            raise ValueError(
                "No existe una ubicación Odoo asociada a la "
                "Location Shopify %s."
                % location_id
            )

        # Aquí debes decidir si Shopify o Odoo será el maestro del stock.
        product.with_context(
            skip_shopify_stock_sync=True,
        )._apply_shopify_stock_quantity(
            location_mapping,
            available,
        )

        return True
