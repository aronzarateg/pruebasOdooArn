from odoo import models, fields, _
import requests
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta

import logging

_logger = logging.getLogger(__name__)


class MeliService(models.AbstractModel):
    _name = "meli.service"
    _description = "Servicio API Mercado Libre"

    BASE_URL = "https://api.mercadolibre.com"
    TIMEOUT = 30

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

    def _send_request(self, account, method, endpoint, params=None, data=None, ):
        account.ensure_one()

        endpoint = endpoint or ""

        if not endpoint.startswith("/"):
            endpoint = "/%s" % endpoint

        url = "%s%s" % (
            self.BASE_URL.rstrip("/"),
            endpoint,
        )

        headers = {
            "Authorization": "Bearer %s" % account.access_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        try:
            return requests.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params or {},
                json=data,
                timeout=self.TIMEOUT,
            )

        except requests.RequestException as error:
            _logger.exception(
                "Error consumiendo Mercado Libre. "
                "Cuenta: %s, método: %s, endpoint: %s",
                account.display_name,
                method,
                endpoint,
            )

            raise UserError(
                _(
                    "No fue posible comunicarse con Mercado Libre.\n\n"
                    "Método: %(method)s\n"
                    "Endpoint: %(endpoint)s\n"
                    "Detalle: %(error)s"
                )
                % {
                    "method": method.upper(),
                    "endpoint": endpoint,
                    "error": str(error),
                }
            ) from error

    def exchange_code_for_token(self, account, code):
        print("exchange_code_for_token")
        response = requests.post(
            f"{self.BASE_URL}/oauth/token",
            headers={
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "client_id": account.client_id,
                "client_secret": account.client_secret,
                "code": code,
                "redirect_uri": account.redirect_uri,
            },
            timeout=30,
        )

        if response.status_code >= 400:
            raise UserError(
                "Error obteniendo token Mercado Libre:\n"
                f"Status: {response.status_code}\n"
                f"Respuesta: {response.text}"
            )

        data = response.json()
        print("data", data)
        expires_in = int(data.get("expires_in") or 0)
        now = fields.Datetime.now()

        vals = {
            "access_token": data.get("access_token") or False,
            "token_type": data.get("token_type") or False,
            "token_scope": data.get("scope") or False,
            "meli_user_id": str(data.get("user_id") or ""),
            "token_expires_in": expires_in,
            "token_expiration_date": (
                now + timedelta(seconds=expires_in)
                if expires_in
                else False
            ),
            "token_last_update": now,
            "token_response": data,
        }

        # No sobrescribir el refresh_token existente con False.
        if data.get("refresh_token"):
            vals["refresh_token"] = data["refresh_token"]

        account.sudo().write(vals)

        return data

    def refresh_token(self, account):
        account.ensure_one()

        if not account.client_id:
            raise UserError(_("La cuenta no tiene configurado el Client ID."))

        if not account.client_secret:
            raise UserError(_("La cuenta no tiene configurado el Client Secret."))

        if not account.refresh_token:
            raise UserError(_(
                "La cuenta no tiene un Refresh Token.\n\n"
                "Debe volver a conectar y autorizar la cuenta de Mercado Libre."
            ))

        payload = {
            "grant_type": "refresh_token",
            "client_id": str(account.client_id).strip(),
            "client_secret": str(account.client_secret).strip(),
            "refresh_token": str(account.refresh_token).strip(),
        }

        try:
            response = requests.post(
                f"{self.BASE_URL}/oauth/token",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=payload,
                timeout=30,
            )
        except requests.RequestException as error:
            _logger.exception(
                "Error de conexión al renovar token Mercado Libre. Cuenta: %s",
                account.display_name,
            )
            raise UserError(_(
                "No se pudo conectar con Mercado Libre para renovar el token.\n\n"
                "Detalle: %s"
            ) % str(error)) from error

        try:
            response_data = response.json()
        except ValueError:
            response_data = {
                "message": response.text or "Respuesta vacía"
            }

        if response.status_code >= 400:
            error_code = response_data.get("error", "")
            error_message = (
                    response_data.get("message")
                    or response_data.get("error_description")
                    or response.text
            )

            _logger.error(
                "Error renovando token Mercado Libre. "
                "Cuenta: %s, status: %s, error: %s, respuesta: %s",
                account.display_name,
                response.status_code,
                error_code,
                response.text,
            )

            reconnect_message = ""

            if error_code in (
                    "invalid_grant",
                    "invalid_token",
                    "invalid_refresh_token",
            ):
                reconnect_message = _(
                    "\n\nEl Refresh Token ya no es válido. "
                    "Debe volver a conectar y autorizar la cuenta."
                )

            raise UserError(_(
                "No se pudo renovar el token de Mercado Libre.\n\n"
                "Estado HTTP: %(status)s\n"
                "Código: %(code)s\n"
                "Respuesta: %(message)s"
                "%(reconnect)s"
            ) % {
                                "status": response.status_code,
                                "code": error_code or "Sin código",
                                "message": error_message or "Sin detalle",
                                "reconnect": reconnect_message,
                            })

        access_token = response_data.get("access_token")
        refresh_token = response_data.get("refresh_token")
        expires_in = int(response_data.get("expires_in") or 0)

        if not access_token:
            raise UserError(_(
                "Mercado Libre no devolvió un Access Token.\n\n"
                "Respuesta: %s"
            ) % response.text)

        vals = {
            "access_token": access_token,
            "token_expires_in": expires_in,
            "token_expiration_date": (
                    fields.Datetime.now() + timedelta(seconds=expires_in)
            ),
        }

        # Mercado Libre normalmente devuelve un nuevo refresh_token.
        # Si no viene, se conserva el actual.
        if refresh_token:
            vals["refresh_token"] = refresh_token

        account.sudo().write(vals)

        return response_data

    def request(            self,            account,            method,            endpoint,            params=None,            data=None,            retry=True,    ):
        account.ensure_one()

        # Antes de consumir la API, comprueba la vigencia del token.
        self.ensure_valid_access_token(account)

        response = self._send_request(
            account=account,
            method=method,
            endpoint=endpoint,
            params=params,
            data=data,
        )

        # Si Mercado Libre invalida el token antes de la fecha registrada,
        # se renueva y se reintenta una sola vez.
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
                    "Error Mercado Libre.\n\n"
                    "Status: %(status)s\n"
                    "Método: %(method)s\n"
                    "Endpoint: %(endpoint)s\n"
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

    def get(self, account, endpoint, params=None):
        return self.request(account, "GET", endpoint, params=params)

    def post(self, account, endpoint, data=None):
        return self.request(account, "POST", endpoint, data=data)

    def put(self, account, endpoint, data=None):
        return self.request(account, "PUT", endpoint, data=data)

    def ensure_valid_access_token(self, account):
        account.ensure_one()

        if not account.access_token:
            raise UserError(
                _("La cuenta no tiene Access Token. Debe conectarla.")
            )

        renewal_limit = (
                fields.Datetime.now() + timedelta(minutes=10)
        )

        if (
                not account.token_expiration_date
                or account.token_expiration_date <= renewal_limit
        ):
            self.refresh_token(account)

        return account.access_token

    BASE_URL = "https://api.mercadolibre.com"

    def get_shipment(self, account, shipping_id):
        if not shipping_id:
            raise UserError(
                _("La orden no tiene un ID de envío de Mercado Libre.")
            )

        if not account.access_token:
            raise UserError(
                _("La cuenta Mercado Libre no tiene un token configurado.")
            )

        try:
            response = requests.get(
                "%s/shipments/%s" % (
                    self.BASE_URL,
                    shipping_id,
                ),
                headers={
                    "Authorization": "Bearer %s" % account.access_token,
                    "Accept": "application/json",
                    "x-format-new": "true",
                },
                timeout=30,
            )
        except requests.RequestException as error:
            raise UserError(
                _("No se pudo consultar el envío de Mercado Libre:\n%s")
                % str(error)
            )

        if response.status_code == 401:
            raise UserError(
                _("El token de Mercado Libre es inválido o ha expirado.")
            )

        if response.status_code == 404:
            raise UserError(
                _("No se encontró el envío Mercado Libre %s.")
                % shipping_id
            )

        if response.status_code >= 400:
            raise UserError(
                _(
                    "Error consultando el envío Mercado Libre.\n"
                    "Código HTTP: %(status)s\n"
                    "Respuesta: %(response)s"
                )
                % {
                    "status": response.status_code,
                    "response": response.text,
                }
            )

        try:
            return response.json()
        except ValueError:
            raise UserError(
                _("Mercado Libre devolvió una respuesta JSON inválida.")
            )

    def get_billing_info(self, account, site_id, billing_info_id):
        if not billing_info_id:
            return {}

        response = requests.get(
            "%s/orders/billing-info/%s/%s" % (
                self.BASE_URL,
                site_id,
                billing_info_id,
            ),
            headers={
                "Authorization": "Bearer %s" % account.access_token,
                "Accept": "application/json",
            },
            timeout=30,
        )

        if response.status_code >= 400:
            raise UserError(
                _(
                    "Error consultando datos de facturación de Mercado Libre.\n"
                    "Código HTTP: %(status)s\n"
                    "Respuesta: %(response)s"
                )
                % {
                    "status": response.status_code,
                    "response": response.text,
                }
            )

        return response.json()
