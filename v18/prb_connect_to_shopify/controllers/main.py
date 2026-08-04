# -*- coding: utf-8 -*-

import logging
import requests

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class ShopifyController(http.Controller):

    @http.route(
        "/shopify/callback",
        auth="public",
        type="http",
        methods=["GET"],
        csrf=False,
    )
    def shopify_callback(self, **kw):
        _logger.info("SHOPIFY CALLBACK PARAMS: %s", kw)

        shop = (kw.get("shop") or "").strip().lower()
        id_token = kw.get("id_token")
        state = kw.get("state")
        code = kw.get("code")

        # Flujo OAuth tradicional
        if code:
            if not state:
                return request.make_response(
                    "No llegó el parámetro state.",
                    status=400,
                )

            try:
                account_id = int(state)
            except (TypeError, ValueError):
                return request.make_response(
                    "El parámetro state no es válido.",
                    status=400,
                )

            account = request.env["shopify.account"].sudo().browse(
                account_id
            ).exists()

            if not account:
                return request.make_response(
                    "No existe la cuenta Shopify indicada.",
                    status=404,
                )

            request.env["shopify.service"].sudo().exchange_code_for_token(
                account,
                code,
            )

            return self._success_response(shop or account.shop)

        # Flujo moderno para app embebida
        if id_token and shop:
            account = request.env["shopify.account"].sudo().search([
                ("shop", "=", shop),
                ("active", "=", True),
            ], limit=1)

            if not account:
                return request.make_response(
                    "No existe una cuenta activa configurada para %s."
                    % shop,
                    status=404,
                )

            try:
                self._exchange_id_token(account, id_token)
            except Exception as error:
                _logger.exception(
                    "Error intercambiando el ID token de Shopify"
                )
                return request.make_response(
                    "No fue posible completar la conexión con Shopify: %s"
                    % str(error),
                    status=400,
                )

            return self._success_response(shop)

        return request.make_response(
            "No se recibió código OAuth ni ID token de Shopify.",
            status=400,
        )

    def _exchange_id_token(self, account, id_token):
        shop = account._get_shop_domain()

        url = "https://%s/admin/oauth/access_token" % shop

        payload = {
            "client_id": account.client_id,
            "client_secret": account.client_secret,
            "grant_type": (
                "urn:ietf:params:oauth:grant-type:token-exchange"
            ),
            "subject_token": id_token,
            "subject_token_type": (
                "urn:ietf:params:oauth:token-type:id_token"
            ),
            "requested_token_type": (
                "urn:shopify:params:oauth:token-type:"
                "offline-access-token"
            ),
        }

        response = requests.post(
            url,
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": (
                    "application/x-www-form-urlencoded"
                ),
            },
            timeout=30,
        )

        try:
            response_data = response.json()
        except ValueError:
            response_data = {}

        if response.status_code not in (200, 201):
            raise ValueError(
                response_data.get("error_description")
                or response_data.get("error")
                or response.text
                or "Shopify rechazó el intercambio del token"
            )

        access_token = response_data.get("access_token")

        if not access_token:
            raise ValueError(
                "Shopify no devolvió el access_token"
            )

        values = {
            "access_token": access_token,
            "scopes": response_data.get("scope") or account.scopes,
            "state": "connected",
        }

        if response_data.get("refresh_token"):
            values["refresh_token"] = response_data["refresh_token"]

        if response_data.get("expires_in"):
            values["token_expires_in"] = response_data["expires_in"]

        account.sudo().write(values)

        return response_data

    def _success_response(self, shop):
        return request.make_response(
            """
            <html>
                <body>
                    <h2>Shopify conectado correctamente</h2>
                    <p>Tienda: %s</p>
                    <p>Ya puede cerrar esta ventana y volver a Odoo.</p>
                </body>
            </html>
            """ % shop,
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )