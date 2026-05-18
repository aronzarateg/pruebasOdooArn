# -*- coding: utf-8 -*-

import hmac
import json
import hashlib
import logging
import requests

from datetime import datetime, timezone
from urllib.parse import urlencode

from odoo import models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class FalabellaApiService(models.AbstractModel):
    _name = "falabella.api.service"
    _description = "Servicio API Falabella Seller Center"

    def _get_timestamp(self):
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")

    def _generate_signature(self, params, api_key):
        """
        Genera firma HMAC-SHA256.
        Importante:
        - No incluir Signature.
        - Ordenar params alfabéticamente.
        - Usar URL encoding.
        """
        params_to_sign = {
            key: value
            for key, value in params.items()
            if key != "Signature"
        }

        query_string = urlencode(sorted(params_to_sign.items()))

        signature = hmac.new(
            api_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return signature

    def _build_params(self, account, action, extra_params=None):
        params = {
            "Action": action,
            "Format": account.format or "JSON",
            "Timestamp": self._get_timestamp(),
            "UserID": account.user_id_api,
            "Version": account.version or "1.0",
        }

        if extra_params:
            params.update(extra_params)

        params["Signature"] = self._generate_signature(
            params,
            account.api_key,
        )

        return params

    def _call_api(self, account, action, method="GET", extra_params=None, payload=None):
        params = self._build_params(account, action, extra_params)

        headers = {
            "Accept": "application/json" if account.format == "JSON" else "application/xml",
        }

        try:
            if method == "GET":
                response = requests.get(
                    account.api_url,
                    params=params,
                    headers=headers,
                    timeout=60,
                )
            elif method == "POST":
                response = requests.post(
                    account.api_url,
                    params=params,
                    json=payload if account.format == "JSON" else None,
                    data=payload if account.format == "XML" else None,
                    headers=headers,
                    timeout=60,
                )
            else:
                raise UserError(_("Método HTTP no soportado: %s") % method)

        except requests.exceptions.RequestException as e:
            raise UserError(_("Error conectando con Falabella: %s") % e)

        _logger.info("Falabella URL: %s", response.url)
        _logger.info("Falabella Response: %s", response.text)

        if response.status_code not in [200, 201]:
            raise UserError(_("Error HTTP Falabella: %s") % response.text)

        if account.format == "JSON":
            try:
                data = response.json()
            except Exception:
                raise UserError(_("Respuesta JSON inválida: %s") % response.text)

            if data.get("ErrorResponse"):
                error = data["ErrorResponse"]["Head"].get("ErrorMessage")
                raise UserError(_("Error Falabella: %s") % error)

            return data

        return response.text

    def _extract_brands_from_response(self, response):
        body = response.get("SuccessResponse", {}).get("Body", {})
        brands_data = body.get("Brands", [])

        brands = []

        if isinstance(brands_data, list):
            for item in brands_data:
                if isinstance(item, dict) and item.get("Brand"):
                    brands.append(item.get("Brand"))

        elif isinstance(brands_data, dict):
            brand_data = brands_data.get("Brand", [])
            if isinstance(brand_data, list):
                brands = brand_data
            elif isinstance(brand_data, dict):
                brands = [brand_data]

        return brands

    def sync_brands(self, account):
        print("sync_brands")
        response = self.get_brands(account)

        raw_response = json.dumps(response, indent=4, ensure_ascii=False)


        brands = self._extract_brands_from_response(response)


        Brand = self.env["falabella.brand"].sudo()

        created = 0
        updated = 0

        for item in brands:
            brand_id = int(item.get("BrandId") or 0)
            name = item.get("Name")
            global_identifier = item.get("GlobalIdentifier")

            if not brand_id or not name:
                continue

            vals = {
                "account_id": account.id,
                "brand_id": brand_id,
                "name": name,
                "global_identifier": global_identifier,
                #"raw_xml": raw_response,
            }
            print("vals:", vals)
            brand = Brand.search([
                ("account_id", "=", account.id),
                ("brand_id", "=", brand_id),
            ], limit=1)

            if brand:
                brand.write(vals)
                updated += 1
            else:
                print("vals",vals)
                Brand.create(vals)
                created += 1

        return {
            "created": created,
            "updated": updated,
            "total": len(brands),
        }

    def get_brands(self, account):
        return self._call_api(
            account=account,
            action="GetBrands",
            method="GET",
        )

    def get_products(self, account, extra_params=None):
        return self._call_api(
            account=account,
            action="GetProducts",
            method="GET",
            extra_params=extra_params,
        )

    def send_product(self, account, payload):
        return self._call_api(
            account=account,
            action="ProductCreate",
            method="POST",
            payload=payload,
        )
