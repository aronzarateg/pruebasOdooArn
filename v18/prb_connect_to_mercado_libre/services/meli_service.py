from odoo import models
import requests
from odoo.exceptions import UserError, ValidationError

class MeliService(models.AbstractModel):
    _name = "meli.service"
    _description = "Servicio API Mercado Libre"

    BASE_URL = "https://api.mercadolibre.com"

    def exchange_code_for_token(self, account, code):
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
        response.raise_for_status()
        data = response.json()

        account.sudo().write({
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
            "meli_user_id": str(data.get("user_id")),
            "token_expires_in": data.get("expires_in"),
        })

        return data

    def refresh_token(self, account):
        response = requests.post(
            f"{self.BASE_URL}/oauth/token",
            headers={
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "client_id": account.client_id,
                "client_secret": account.client_secret,
                "refresh_token": account.refresh_token,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        account.sudo().write({
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
            "token_expires_in": data.get("expires_in"),
        })

        return data

    def request(self, account, method, endpoint, params=None, data=None):
        headers = {
            "Authorization": f"Bearer {account.access_token}",
            "Content-Type": "application/json",
        }

        response = requests.request(
            method,
            f"{self.BASE_URL}{endpoint}",
            headers=headers,
            params=params or {},
            json=data,
            timeout=30,
        )

        if response.status_code == 401:
            self.refresh_token(account)
            headers["Authorization"] = f"Bearer {account.access_token}"

            response = requests.request(
                method,
                f"{self.BASE_URL}{endpoint}",
                headers=headers,
                params=params or {},
                json=data,
                timeout=30,
            )

        if response.status_code >= 400:
            raise UserError(
                "Error Mercado Libre:\n"
                f"Status: {response.status_code}\n"
                f"URL: {endpoint}\n"
                f"Respuesta: {response.text}\n"
                f"Payload enviado: {data}"
            )

        return response.json() if response.text else {}

    def get(self, account, endpoint, params=None):
        return self.request(account, "GET", endpoint, params=params)

    def post(self, account, endpoint, data=None):
        return self.request(account, "POST", endpoint, data=data)

    def put(self, account, endpoint, data=None):
        return self.request(account, "PUT", endpoint, data=data)