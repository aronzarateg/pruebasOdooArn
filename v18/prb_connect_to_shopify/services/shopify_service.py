import logging
from datetime import timedelta

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class ShopifyService(models.AbstractModel):
    _name = "shopify.service"
    _description = "Servicio API Shopify"

    API_VERSION = "2026-04"
    TIMEOUT = 30

    # ---------------------------------------------------------
    # Utilidades
    # ---------------------------------------------------------

    def _get_shop_domain(self, account):
        account.ensure_one()
        return account._get_shop_domain()

    def _get_base_url(self, account):
        return "https://%s/admin/api/%s" % (
            self._get_shop_domain(account),
            self.API_VERSION,
        )

    @staticmethod
    def _response_json(response):
        if not response.content:
            return {}

        try:
            return response.json()
        except ValueError:
            return {
                "message": response.text or "Respuesta no válida",
            }

    # ---------------------------------------------------------
    # OAuth
    # ---------------------------------------------------------

    def exchange_code_for_token(self, account, code, shop=None):
        account.ensure_one()

        if not code:
            raise UserError(
                _("Shopify no devolvió el código de autorización.")
            )

        shop_domain = shop or self._get_shop_domain(account)
        shop_domain = (
            shop_domain
            .replace("https://", "")
            .replace("http://", "")
            .strip("/")
            .lower()
        )

        try:
            response = requests.post(
                "https://%s/admin/oauth/access_token" % shop_domain,
                headers={
                    "Accept": "application/json",
                    "Content-Type":
                        "application/x-www-form-urlencoded",
                },
                data={
                    "client_id": account.client_id,
                    "client_secret": account.client_secret,
                    "code": code,

                    # Solicita un offline token expirable.
                    "expiring": "1",
                },
                timeout=self.TIMEOUT,
            )
        except requests.RequestException as error:
            raise UserError(
                _("No fue posible comunicarse con Shopify:\n%s")
                % error
            ) from error

        data = self._response_json(response)

        if not response.ok:
            raise UserError(
                _(
                    "Error obteniendo el token Shopify:\n"
                    "Status: %(status)s\n"
                    "Respuesta: %(response)s"
                )
                % {
                    "status": response.status_code,
                    "response": response.text,
                }
            )

        self._save_token_response(
            account=account,
            data=data,
            shop_domain=shop_domain,
        )

        return data

    def _save_token_response(
        self,
        account,
        data,
        shop_domain=None,
    ):
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = int(data.get("expires_in") or 0)
        refresh_expires_in = int(
            data.get("refresh_token_expires_in") or 0
        )

        if not access_token:
            raise UserError(
                _("Shopify no devolvió el Access Token.")
            )

        if not refresh_token:
            raise UserError(
                _(
                    "Shopify no devolvió el Refresh Token.\n\n"
                    "Verifique que el intercambio OAuth esté solicitando "
                    "un token offline expirable mediante expiring=1."
                )
            )

        if expires_in <= 0:
            raise UserError(
                _("Shopify devolvió una duración de token inválida.")
            )

        now = fields.Datetime.now()

        values = {
            "access_token": access_token,

            # Debes sustituir siempre el refresh token anterior.
            "refresh_token": refresh_token,

            "scopes": data.get("scope") or account.scopes,
            "token_expires_in": expires_in,
            "token_expiration_date": (
                now + timedelta(seconds=expires_in)
            ),
            "refresh_token_expiration_date": (
                now + timedelta(seconds=refresh_expires_in)
                if refresh_expires_in
                else False
            ),
            "last_token_refresh": now,
            "token_error": False,
            "state": "connected",
        }

        if shop_domain:
            values["shop"] = shop_domain

        account.sudo().write(values)

    def refresh_token(self, account):
        account.ensure_one()

        if not account.refresh_token:
            account.sudo().write({
                "state": "reconnect",
                "token_error": (
                    "La cuenta no tiene Refresh Token."
                ),
            })

            raise UserError(
                _(
                    "La tienda Shopify '%s' no tiene Refresh Token. "
                    "Debe volver a conectarla."
                )
                % account.display_name
            )

        # Bloquea la cuenta para evitar que dos procesos utilicen
        # simultáneamente el mismo refresh token.
        self.env.cr.execute(
            """
                SELECT id
                  FROM shopify_account
                 WHERE id = %s
                 FOR UPDATE
            """,
            [account.id],
        )

        account.invalidate_recordset([
            "access_token",
            "refresh_token",
            "token_expiration_date",
            "refresh_token_expiration_date",
        ])

        shop_domain = self._get_shop_domain(account)

        try:
            response = requests.post(
                "https://%s/admin/oauth/access_token" % shop_domain,
                headers={
                    "Accept": "application/json",
                    "Content-Type":
                        "application/x-www-form-urlencoded",
                },
                data={
                    "client_id": account.client_id,
                    "client_secret": account.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": account.refresh_token,
                },
                timeout=self.TIMEOUT,
            )
        except requests.RequestException as error:
            raise UserError(
                _("No fue posible comunicarse con Shopify:\n%s")
                % error
            ) from error

        data = self._response_json(response)

        if not response.ok:
            values = {
                "token_error": response.text,
            }

            if response.status_code == 401:
                values["state"] = "reconnect"

            account.sudo().write(values)

            raise UserError(
                _(
                    "No se pudo renovar el token de Shopify.\n"
                    "Status: %(status)s\n"
                    "Respuesta: %(response)s"
                )
                % {
                    "status": response.status_code,
                    "response": response.text,
                }
            )

        self._save_token_response(
            account=account,
            data=data,
        )

        return data

    def ensure_valid_access_token(self, account):
        account.ensure_one()

        if not account.access_token:
            raise UserError(
                _(
                    "Primero debe conectar Shopify para obtener "
                    "el Access Token."
                )
            )

        renewal_limit = (
            fields.Datetime.now() + timedelta(minutes=5)
        )

        if (
            account.refresh_token
            and (
                not account.token_expiration_date
                or account.token_expiration_date <= renewal_limit
            )
        ):
            self.refresh_token(account)

        return account.access_token

    # ---------------------------------------------------------
    # REST
    # ---------------------------------------------------------

    def request(
        self,
        account,
        method,
        endpoint,
        params=None,
        data=None,
        retry=True,
    ):
        account.ensure_one()

        self.ensure_valid_access_token(account)

        response = self._send_request(
            account=account,
            method=method,
            endpoint=endpoint,
            params=params,
            data=data,
        )

        # El token puede ser invalidado antes de la fecha almacenada.
        # Se renueva y se repite la llamada una sola vez.
        if response.status_code == 401 and retry:
            self.refresh_token(account)

            response = self._send_request(
                account=account,
                method=method,
                endpoint=endpoint,
                params=params,
                data=data,
            )

        if not response.ok:
            raise UserError(
                _(
                    "Error Shopify:\n"
                    "Status: %(status)s\n"
                    "Método: %(method)s\n"
                    "URL: %(endpoint)s\n"
                    "Respuesta: %(response)s"
                )
                % {
                    "status": response.status_code,
                    "method": method.upper(),
                    "endpoint": endpoint,
                    "response": response.text,
                }
            )

        return self._response_json(response)

    def _send_request(
        self,
        account,
        method,
        endpoint,
        params=None,
        data=None,
    ):
        try:
            return requests.request(
                method=method.upper(),
                url="%s%s" % (
                    self._get_base_url(account),
                    endpoint,
                ),
                headers={
                    "X-Shopify-Access-Token":
                        account.access_token,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                params=params or {},
                json=data,
                timeout=self.TIMEOUT,
            )
        except requests.RequestException as error:
            raise UserError(
                _(
                    "No fue posible comunicarse con Shopify.\n"
                    "Endpoint: %(endpoint)s\n"
                    "Detalle: %(error)s"
                )
                % {
                    "endpoint": endpoint,
                    "error": error,
                }
            ) from error

    def get(self, account, endpoint, params=None):
        return self.request(
            account,
            "GET",
            endpoint,
            params=params,
        )

    def post(self, account, endpoint, data=None, params=None):
        return self.request(
            account,
            "POST",
            endpoint,
            params=params,
            data=data,
        )

    def put(self, account, endpoint, data=None, params=None):
        return self.request(
            account,
            "PUT",
            endpoint,
            params=params,
            data=data,
        )

    def delete(self, account, endpoint, data=None, params=None):
        return self.request(
            account,
            "DELETE",
            endpoint,
            params=params,
            data=data,
        )

    # ---------------------------------------------------------
    # GraphQL
    # ---------------------------------------------------------

    def graphql(
        self,
        account,
        query,
        variables=None,
        retry=True,
    ):
        account.ensure_one()

        self.ensure_valid_access_token(account)

        response = self._send_graphql_request(
            account=account,
            query=query,
            variables=variables,
        )

        if response.status_code == 401 and retry:
            self.refresh_token(account)

            response = self._send_graphql_request(
                account=account,
                query=query,
                variables=variables,
            )

        if not response.ok:
            raise UserError(
                _(
                    "Error HTTP consultando Shopify:\n"
                    "Status: %(status)s\n"
                    "Respuesta: %(response)s"
                )
                % {
                    "status": response.status_code,
                    "response": response.text,
                }
            )

        data = self._response_json(response)

        if data.get("errors"):
            raise UserError(
                _("Shopify devolvió errores GraphQL:\n%s")
                % data["errors"]
            )

        return data

    def _send_graphql_request(
        self,
        account,
        query,
        variables=None,
    ):
        url = "%s/graphql.json" % self._get_base_url(account)

        try:
            return requests.post(
                url,
                headers={
                    "X-Shopify-Access-Token":
                        account.access_token,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "query": query,
                    "variables": variables or {},
                },
                timeout=self.TIMEOUT,
            )
        except requests.RequestException as error:
            raise UserError(
                _("Error consultando Shopify:\n%s") % error
            ) from error