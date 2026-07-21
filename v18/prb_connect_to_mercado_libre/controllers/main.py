from odoo import http
from odoo.http import request
import json


class MercadoLibreController(http.Controller):

    @http.route("/mercadolibre_v2/callback", auth="public", type="http", csrf=False)
    def meli_callback(self, **kw):
        code = kw.get("code")
        state = kw.get("state")

        if not code:
            return "No llegó código de autorización."

        if not state:
            return "No llegó el identificador de la cuenta Mercado Libre."

        try:
            account_id = int(state)
        except Exception:
            return "El identificador de la cuenta Mercado Libre no es válido."

        account = request.env["meli.account"].sudo().browse(account_id)

        if not account.exists():
            return "No existe la cuenta Mercado Libre indicada."

        request.env["meli.service"].sudo().exchange_code_for_token(account, code)

        return """
        <h2>Mercado Libre conectado correctamente</h2>
        <p>Ya puedes cerrar esta ventana y volver a Odoo.</p>
        """

    @http.route("/mercadolibre_v2/notifications", auth="public", type="json", methods=["POST"], csrf=False)
    def meli_notifications(self, **kw):
        data = request.jsonrequest or {}

        request.env["meli.notification"].sudo().create({
            "topic": data.get("topic"),
            "resource": data.get("resource"),
            "user_id": str(data.get("user_id") or ""),
            "application_id": str(data.get("application_id") or ""),
            "attempts": data.get("attempts") or 0,
            "sent": data.get("sent"),
            "payload": json.dumps(data),
        })

        return {"status": "ok"}