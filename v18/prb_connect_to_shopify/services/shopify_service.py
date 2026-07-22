from odoo import models, _
from odoo.exceptions import UserError
import requests


class ShopifyService(models.AbstractModel):
    _name = "shopify.service"
    _description = "Servicio API Shopify"

    API_VERSION = "2026-04"

    def _get_base_url(self, account):
        shop = account.shop.replace("https://", "").replace("http://", "").strip("/")
        return "https://%s/admin/api/%s" % (shop, self.API_VERSION)

    def request(self, account, method, endpoint, params=None, data=None):
        if not account.access_token:
            raise UserError("Primero debes conectar Shopify para generar el Access Token.")

        headers = {
            "X-Shopify-Access-Token": account.access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        response = requests.request(
            method,
            "%s%s" % (self._get_base_url(account), endpoint),
            headers=headers,
            params=params or {},
            json=data,
            timeout=30,
        )

        if response.status_code >= 400:
            raise UserError(
                "Error Shopify:\n"
                "Status: %s\n"
                "URL: %s\n"
                "Respuesta: %s\n"
                "Payload enviado: %s"
                % (response.status_code, endpoint, response.text, data)
            )

        return response.json() if response.text else {}

    def get(self, account, endpoint, params=None):
        return self.request(account, "GET", endpoint, params=params)

    def post(self, account, endpoint, data=None):
        return self.request(account, "POST", endpoint, data=data)

    def put(self, account, endpoint, data=None):
        return self.request(account, "PUT", endpoint, data=data)

    def delete(self, account, endpoint, data=None):
        return self.request(account, "DELETE", endpoint, data=data)

    def exchange_code_for_token(self, account, code, shop=None):
        shop_domain = shop or account.shop
        shop_domain = shop_domain.replace("https://", "").replace("http://", "").strip("/")

        response = requests.post(
            "https://%s/admin/oauth/access_token" % shop_domain,
            json={
                "client_id": account.client_id,
                "client_secret": account.client_secret,
                "code": code,
            },
            timeout=30,
        )

        if response.status_code >= 400:
            raise UserError(
                "Error obteniendo token Shopify:\n"
                "Status: %s\n"
                "Respuesta: %s" % (response.status_code, response.text)
            )

        data = response.json()

        account.sudo().write({
            "shop": shop_domain,
            "access_token": data.get("access_token"),
            "scopes": data.get("scope"),
            "state": "connected",
        })

        return data

    def graphql(self, account, query, variables=None):
        account.ensure_one()

        shop = (
            account.shop
            .replace("https://", "")
            .replace("http://", "")
            .strip("/")
        )

        url = (
            f"https://{shop}/admin/api/"
            f"{self.API_VERSION}/graphql.json"
        )

        try:
            response = requests.post(
                url,
                headers={
                    "X-Shopify-Access-Token": account.access_token,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "query": query,
                    "variables": variables or {},
                },
                timeout=30,
            )

            response.raise_for_status()

        except requests.RequestException as error:
            raise UserError(
                _("Error consultando Shopify:\n%s") % error
            ) from error

        data = response.json()

        if data.get("errors"):
            raise UserError(
                _("Shopify devolvió errores:\n%s") % data["errors"]
            )

        return data
