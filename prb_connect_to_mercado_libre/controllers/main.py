from odoo import http
from odoo.http import request


class MercadoLibreController(http.Controller):

    @http.route("/mercadolibre_v2/callback", auth="public", type="http", csrf=False)
    def meli_callback(self, **kw):
        code = kw.get("code")

        if not code:
            return "No llegó código de autorización."

        account = request.env["meli.account"].sudo().search([], limit=1)

        if not account:
            return "No existe una cuenta Mercado Libre configurada en Odoo."

        request.env["meli.service"].sudo().exchange_code_for_token(account, code)

        return """
        <h2>Mercado Libre conectado correctamente</h2>
        <p>Ya puedes cerrar esta ventana y volver a Odoo.</p>
        """

    @http.route("/mercadolibre_v2/notifications", auth="public", type="json", methods=["POST"], csrf=False, )
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
