from odoo import http
from odoo.http import request


class ShopifyController(http.Controller):

    @http.route("/shopify/callback", auth="public", type="http", csrf=False)
    def shopify_callback(self, **kw):
        print("SHOPIFY KW:", kw)

        code = kw.get("code")
        state = kw.get("state")
        shop = kw.get("shop")

        if not code:
            return "No llegó código de autorización."

        if not state:
            return "No llegó state. Parámetros recibidos: %s" % kw

        try:
            account_id = int(state)
        except Exception:
            return "State inválido: %s" % state

        account = request.env["shopify.account"].sudo().browse(account_id)

        if not account.exists():
            return "No existe la cuenta Shopify indicada."

        request.env["shopify.service"].sudo().exchange_code_for_token(account, code)

        return """
        <h2>Shopify conectado correctamente</h2>
        <p>Tienda: %s</p>
        <p>Ya puedes cerrar esta ventana y volver a Odoo.</p>
        """ % (shop or account.shop)