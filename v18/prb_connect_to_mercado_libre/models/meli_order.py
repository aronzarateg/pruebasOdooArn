from odoo import models, fields, api, _
import json
from odoo.exceptions import UserError, ValidationError

from markupsafe import Markup, escape

import logging
import random

_logger = logging.getLogger(__name__)


class MeliOrder(models.Model):
    _name = "meli.order"
    _description = "Orden Mercado Libre"
    _rec_name = "meli_order_id"
    _order = "date_created desc, id desc"

    account_id = fields.Many2one(
        "meli.account",
        string="Cuenta",
        required=True,
        ondelete="cascade",
        index=True,
    )

    meli_order_id = fields.Char(
        string="Orden Mercado Libre",
        required=True,
        index=True,
    )

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Cotización/Venta",
        readonly=True,
        copy=False,
    )

    sale_order_count = fields.Integer(
        string="Cantidad de cotizaciones",
        compute="_compute_sale_order_count",
    )
    billing_info_id = fields.Char(
        string="ID datos de facturación",
        readonly=True,
    )

    state = fields.Selection(
        selection=[
            ("draft", "Pendiente"),
            ("sale_created", "Cotización creada"),
            ("error", "Error"),
            ("cancelled", "Cancelado"),
        ],
        string="Estado Odoo",
        default="draft",
        readonly=True,
        copy=False,
        index=True,
    )

    processing_error = fields.Text(
        string="Error de procesamiento",
        readonly=True,
        copy=False,
    )

    processing_attempts = fields.Integer(
        string="Intentos de procesamiento",
        readonly=True,
        copy=False,
        default=0,
    )

    status = fields.Char(string="Estado Mercado Libre")
    status_detail = fields.Char(string="Detalle del estado")

    buyer_id = fields.Char(string="ID comprador")
    buyer_nickname = fields.Char(string="Comprador")

    seller_id = fields.Char(string="ID vendedor")
    seller_nickname = fields.Char(string="Vendedor")

    currency_code = fields.Char(string="Moneda")
    total_amount = fields.Float(string="Total")
    paid_amount = fields.Float(string="Monto pagado")

    date_created = fields.Datetime(string="Fecha creación")
    date_last_updated = fields.Datetime(string="Fecha actualización")

    shipping_id = fields.Char(string="ID envío")
    fulfilled = fields.Boolean(string="Entregada")

    line_ids = fields.One2many(
        "meli.order.line",
        "order_id",
        string="Productos",
    )

    payment_ids = fields.One2many(
        "meli.order.payment",
        "order_id",
        string="Pagos",
    )
    date_closed = fields.Datetime(string="Fecha cierre")
    expiration_date = fields.Datetime(string="Fecha expiración")

    coupon_amount = fields.Float(string="Descuento")
    shipping_cost = fields.Float(string="Costo de envío")

    tag_names = fields.Char(string="Etiquetas")

    raw_data = fields.Text(string="JSON Original")

    _sql_constraints = [
        (
            "meli_order_account_unique",
            "unique(account_id, meli_order_id)",
            "La orden de Mercado Libre ya existe para esta cuenta.",
        ),
    ]

    @api.depends("sale_order_id")
    def _compute_sale_order_count(self):
        for order in self:
            order.sale_order_count = 1 if order.sale_order_id else 0

    def action_create_sale_order(self):
        self.ensure_one()

        if self.sale_order_id:
            raise UserError(
                _(
                    "La orden Mercado Libre %s ya tiene relacionada "
                    "la cotización %s."
                )
                % (
                    self.meli_order_id,
                    self.sale_order_id.name,
                )
            )

        self._create_sale_order_from_meli()

        return self.action_view_sale_order()

    def action_view_sale_order(self):
        self.ensure_one()

        if not self.sale_order_id:
            raise UserError(
                _("La orden Mercado Libre no tiene una cotización relacionada.")
            )

        return {
            "type": "ir.actions.act_window",
            "name": _("Cotización"),
            "res_model": "sale.order",
            "view_mode": "form",
            "res_id": self.sale_order_id.id,
            "target": "current",
        }

    def _prepare_sale_order_lines(self):
        self.ensure_one()

        Product = self.env["product.product"].sudo()

        sale_lines = []
        missing_skus = []

        for meli_line in self.line_ids:
            sku = (meli_line.seller_sku or "").strip()

            if not sku:
                missing_skus.append(
                    meli_line.title
                    or meli_line.item_id
                    or _("Producto sin SKU")
                )
                continue

            product = Product.search(
                [
                    ("default_code", "=", sku),
                    ("sale_ok", "=", True),
                ],
                limit=1,
            )

            if not product:
                missing_skus.append(sku)
                continue

            quantity = meli_line.quantity or 1.0
            price_unit = meli_line.unit_price or 0.0

            description = (
                    meli_line.title
                    or product.get_product_multiline_description_sale()
            )

            if meli_line.variation_description:
                description = "%s\n%s" % (
                    description,
                    meli_line.variation_description,
                )

            sale_lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "name": description,
                        "product_uom_qty": quantity,
                        "product_uom": product.uom_id.id,
                        "price_unit": price_unit,
                    },
                )
            )

        if missing_skus:
            raise ValidationError(
                _(
                    "No se pudo crear la cotización porque los siguientes "
                    "productos no fueron encontrados por SKU:\n\n%s"
                )
                % "\n".join(
                    "- %s" % sku
                    for sku in missing_skus
                )
            )

        if not sale_lines:
            raise ValidationError(
                _("La orden no tiene productos válidos para crear la cotización.")
            )

        return sale_lines

    def _get_or_create_partner(self):
        self.ensure_one()

        buyer_id = (self.buyer_id or "").strip()

        if not buyer_id:
            raise ValidationError(
                _("La orden no tiene el ID del comprador de Mercado Libre.")
            )

        company = self._get_meli_company()

        Partner = (
            self.env["res.partner"]
            .sudo()
            .with_company(company)
        )

        partner = Partner.search(
            [
                #("meli_buyer_id", "=", buyer_id),
                ("parent_id", "=", False),
            ],
            limit=1,
        )

        partner_vals = self._prepare_partner_vals()
        print("partner_vals:", partner_vals)
        raise UserError('kdkdkdkdk')
        if partner:
            vals_to_update = {
                key: value
                for key, value in partner_vals.items()
                if value
            }

            partner.write(vals_to_update)
        else:
            partner = Partner.create(partner_vals)

        return partner



    def _prepare_partner_vals(self):
        self.ensure_one()

        buyer_id = (self.buyer_id or "").strip()
        buyer_nickname = (self.buyer_nickname or "").strip()

        billing_data = self._get_billing_partner_data()
        print("billing_datasss:", billing_data)
        raise UserError('kdkdkdkdk')
        full_name = " ".join(
            filter(
                None,
                [
                    (billing_data.get("name") or "").strip(),
                    (billing_data.get("last_name") or "").strip(),
                ],
            )
        )

        street = self._join_address_parts(
            billing_data.get("street_name"),
            billing_data.get("street_number"),
        )

        country = self._find_meli_country(
            country_code=billing_data.get("country_code"),
        )

        state = self._find_meli_state(
            country=country,
            state_code=billing_data.get("state_code"),
            state_name=billing_data.get("state_name"),
        )

        city = self._find_meli_city(
            country=country,
            state=state,
            city_name=billing_data.get("city_name"),
        )

        district = self._find_meli_district(
            city=city,
            neighborhood_name=billing_data.get("neighborhood"),
        )

        document_number = (
                billing_data.get("document_number") or ""
        ).strip()

        vals = {
            "name": (
                    full_name
                    or buyer_nickname
                    or "Comprador Mercado Libre %s" % buyer_id
            ),
            "meli_buyer_id": buyer_id,
            "vat": document_number or False,
            "street": street or False,
            "street2": billing_data.get("comment") or False,
            "zip": billing_data.get("zip_code") or False,
            "city": billing_data.get("city_name") or False,
            "country_id": country.id if country else False,
            "state_id": state.id if state else False,
            "customer_rank": 1,
            "company_type": "person",
        }

        Partner = self.env["res.partner"]

        if "it_name" in Partner._fields:
            vals["it_name"] = vals["name"]

        if (
                document_number
                and "l10n_latam_identification_type_id" in Partner._fields
        ):
            identification_type = (
                self._find_meli_identification_type(
                    billing_data.get("document_type"),
                    document_number,
                )
            )

            if identification_type:
                vals["l10n_latam_identification_type_id"] = (
                    identification_type.id
                )

        if city and "city_id" in Partner._fields:
            vals["city_id"] = city.id
            vals.pop("city", None)

        if district and "l10n_pe_district" in Partner._fields:
            vals["l10n_pe_district"] = district.id

        return vals

    def _get_billing_partner_data(self):
        self.ensure_one()
        print("billing_partner_data",self.billing_info_id)
        if not self.billing_info_id:
            return {}

        response = self.env["meli.service"].get_billing_info(
            account=self.account_id,
            site_id=self.account_id.site_id or "MPE",
            billing_info_id=self.billing_info_id,
        )
        print("response:", response)
        buyer_data = response.get("buyer") or {}
        billing_data = buyer_data.get("billing_info") or {}
        identification = billing_data.get("identification") or {}
        address = billing_data.get("address") or {}
        state = address.get("state") or {}

        return {
            "name": billing_data.get("name"),
            "last_name": billing_data.get("last_name"),
            "document_type": identification.get("type"),
            "document_number": identification.get("number"),
            "street_name": address.get("street_name"),
            "street_number": address.get("street_number"),
            "comment": address.get("comment"),
            "city_name": address.get("city_name"),
            "neighborhood": address.get("neighborhood"),
            "state_name": state.get("name"),
            "state_code": state.get("code"),
            "zip_code": address.get("zip_code"),
            "country_code": address.get("country_id"),
        }

    def _find_meli_identification_type(self, document_type=False, document_number=False, ):
        IdentificationType = self.env["l10n_latam.identification.type"].sudo()

        document_type = (document_type or "").strip().upper()
        document_number = (document_number or "").strip()

        if document_type == "DNI" or len(document_number) == 8:
            vat_code = "1"
        elif document_type == "RUC" or len(document_number) == 11:
            vat_code = "6"
        else:
            return IdentificationType

        identification_type = IdentificationType.search(
            [("l10n_pe_vat_code", "=", vat_code)],
            limit=1,
        )

        return identification_type

    def _get_shipping_partner_data(self):
        self.ensure_one()

        shipment_data = self.env["meli.service"].get_shipment(
            account=self.account_id,
            shipping_id=self.shipping_id,
        )

        destination = shipment_data.get("destination") or {}
        address = destination.get("shipping_address") or {}

        country_data = address.get("country") or {}
        state_data = address.get("state") or {}
        city_data = address.get("city") or {}
        neighborhood_data = address.get("neighborhood") or {}
        municipality_data = address.get("municipality") or {}

        return {
            "receiver_name": destination.get("receiver_name"),
            "receiver_phone": destination.get("receiver_phone"),

            "address_line": address.get("address_line"),
            "street_name": address.get("street_name"),
            "street_number": address.get("street_number"),
            "comment": address.get("comment"),
            "zip_code": address.get("zip_code"),

            "country_code": country_data.get("id"),
            "country_name": country_data.get("name"),

            "state_code": state_data.get("id"),
            "state_name": state_data.get("name"),

            "city_code": city_data.get("id"),
            "city_name": city_data.get("name"),

            "neighborhood_code": neighborhood_data.get("id"),
            "neighborhood_name": neighborhood_data.get("name"),

            "municipality_code": municipality_data.get("id"),
            "municipality_name": municipality_data.get("name"),

            "latitude": address.get("latitude"),
            "longitude": address.get("longitude"),

            "raw_data": shipment_data,
        }

    @staticmethod
    def _build_meli_street(shipping_data):
        address_line = shipping_data.get("address_line")

        if address_line:
            return str(address_line).strip()

        street_name = shipping_data.get("street_name")
        street_number = shipping_data.get("street_number")

        parts = [
            str(value).strip()
            for value in [
                street_name,
                street_number,
            ]
            if value not in [None, False, ""]
        ]

        return " ".join(parts)

    def _find_meli_country(self, country_code=False, country_name=False):
        Country = self.env["res.country"].sudo()

        country_code = (country_code or "").strip().upper()

        if country_code:
            country = Country.search(
                [("code", "=", country_code)],
                limit=1,
            )

            if country:
                return country

        country_name = (country_name or "").strip()

        if country_name:
            return Country.search(
                [("name", "=ilike", country_name)],
                limit=1,
            )

        return Country

    def _find_meli_state(
            self,
            country,
            state_code=False,
            state_name=False,
    ):
        State = self.env["res.country.state"].sudo()

        state_code = (state_code or "").strip()
        state_name = (state_name or "").strip()

        if state_code:
            domain = [("code", "=", state_code)]

            if country:
                domain.append(("country_id", "=", country.id))

            state = State.search(domain, limit=1)

            if state:
                return state

        if state_name:
            domain = [("name", "=ilike", state_name)]

            if country:
                domain.append(("country_id", "=", country.id))

            return State.search(domain, limit=1)

        return State

    def _find_meli_city(
            self,
            country,
            state,
            city_name=False,
            municipality_name=False,
    ):
        if "res.city" not in self.env:
            return False

        City = self.env["res.city"].sudo()

        location_name = (
                (city_name or "").strip()
                or (municipality_name or "").strip()
        )

        if not location_name:
            return City

        domain = [
            ("name", "=ilike", location_name),
        ]

        if state and "state_id" in City._fields:
            domain.append(("state_id", "=", state.id))
        elif country and "country_id" in City._fields:
            domain.append(("country_id", "=", country.id))

        city = City.search(domain, limit=1)

        if not city and municipality_name:
            fallback_domain = [
                ("name", "=ilike", municipality_name.strip()),
            ]

            if state and "state_id" in City._fields:
                fallback_domain.append(("state_id", "=", state.id))

            city = City.search(fallback_domain, limit=1)

        return city

    def _find_meli_district(
            self,
            city=False,
            neighborhood_name=False,
            municipality_name=False,
    ):
        if "l10n_pe.res.city.district" not in self.env:
            return False

        District = self.env[
            "l10n_pe.res.city.district"
        ].sudo()

        possible_names = [
            (neighborhood_name or "").strip(),
            (municipality_name or "").strip(),
        ]

        possible_names = [
            name
            for name in possible_names
            if name
        ]

        for district_name in possible_names:
            domain = [
                ("name", "=ilike", district_name),
            ]

            if city and "city_id" in District._fields:
                domain.append(("city_id", "=", city.id))

            district = District.search(domain, limit=1)

            if district:
                return district

        # Fallback menos preciso, solo por nombre.
        for district_name in possible_names:
            district = District.search(
                [("name", "=ilike", district_name)],
                limit=1,
            )

            if district:
                return district

        return District

    def _create_sale_order_from_meli(self):
        self.ensure_one()

        if self.sale_order_id:
            raise UserError(
                _("La orden Mercado Libre ya tiene una cotización relacionada.")
            )

        if not self.line_ids:
            raise ValidationError(
                _("La orden Mercado Libre no tiene productos.")
            )

        partner = self._get_or_create_partner()
        sale_order_lines = self._prepare_sale_order_lines()

        source = self._get_or_create_meli_source()
        company = self._get_meli_company()
        user = self._get_meli_sale_user(company)

        note = _(
            "Cotización creada desde Mercado Libre:\n"
            "ID de orden: %(order_id)s\n"
            "Comprador: %(buyer)s\n"
            "Estado Mercado Libre: %(status)s"
        ) % {
                   "order_id": self.meli_order_id or "",
                   "buyer": self.buyer_nickname or self.buyer_id or "",
                   "status": self.status or "",
               }

        sale_vals = {
            "partner_id": partner.id,
            "partner_invoice_id": partner.id,
            "partner_shipping_id": partner.id,
            "company_id": company.id,
            "origin": self.meli_order_id,
            "client_order_ref": self.meli_order_id,
            "source_id": source.id,
            "date_order": self.date_created or fields.Datetime.now(),
            "user_id": user.id,
            "order_line": sale_order_lines,
            "note": note,
        }

        sale_order = self.env["sale.order"].sudo().create(sale_vals)

        message = Markup(
            "<p>"
            "<strong>Cotización creada desde Mercado Libre.</strong><br/>"
            "<b>ID de orden:</b> {}<br/>"
            "<b>Comprador:</b> {}<br/>"
            "<b>ID comprador:</b> {}"
            "</p>"
        ).format(
            escape(self.meli_order_id or ""),
            escape(self.buyer_nickname or ""),
            escape(self.buyer_id or ""),
        )

        sale_order.message_post(
            body=message,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )

        self.write({
            "sale_order_id": sale_order.id,
            "state": "sale_created",
            "processing_error": False,
        })

        return sale_order

    def _get_or_create_meli_source(self):
        self.ensure_one()

        UtmSource = self.env["utm.source"].sudo()

        source = UtmSource.search(
            [("name", "=", "api-mercado-libre")],
            limit=1,
        )

        if not source:
            source = UtmSource.create({
                "name": "api-mercado-libre",
            })

        return source

    def _get_meli_company(self):
        self.ensure_one()

        company = self.env["res.company"].sudo().search(
            [
                ("vat", "=", "20609533430"),
            ],
            limit=1,
        )

        if not company:
            raise UserError(
                _('No existe la empresa "DJK INTERNATIONAL S.A.C." configurada.')
            )

        return company

    def _get_meli_sale_user(self, company):
        self.ensure_one()

        group = self.env.ref(
            "api_mercado_libre.group_meli_api_administrator",
            raise_if_not_found=False,
        )

        if not group:
            raise UserError(
                _("No existe el grupo Administrador API Mercado Libre.")
            )

        users = group.users.filtered(
            lambda user:
            user.active
            and not user.share
            and company in user.company_ids
        )

        if not users:
            raise UserError(
                _(
                    "No existen usuarios activos del grupo Administrador API "
                    "Mercado Libre para la compañía %s."
                )
                % company.display_name
            )

        return random.choice(users)

    def _cron_create_sale_orders(self, limit=50):
        orders = self.sudo().search(
            [
                ("sale_order_id", "=", False),
                ("state", "in", ["draft", "error"]),
                ("status", "=", "paid"),
                ("processing_attempts", "<", 5),
            ],
            order="date_created asc, id asc",
            limit=limit,
        )

        for order in orders:
            try:
                with self.env.cr.savepoint():
                    order._create_sale_order_from_meli()

                    order.write({
                        "processing_error": False,
                        "processing_attempts": 0,
                    })

            except Exception as error:
                _logger.exception(
                    "Error creando cotización para orden Mercado Libre %s.",
                    order.meli_order_id,
                )

                order.write({
                    "state": "error",
                    "processing_attempts": order.processing_attempts + 1,
                    "processing_error": str(error),
                })

        return True


class MeliOrderLine(models.Model):
    _name = "meli.order.line"
    _description = "Línea de orden Mercado Libre"
    _order = "id"

    order_id = fields.Many2one("meli.order", string="Orden", required=True, ondelete="cascade", index=True, )
    item_id = fields.Char(string="ID publicación", required=True, index=True, )
    seller_sku = fields.Char(string="SKU", index=True, )
    title = fields.Char(string="Producto", required=True, )
    category_id = fields.Char(string="Categoría ML", )
    variation_id = fields.Char(string="ID variación", )
    variation_description = fields.Char(string="Variación", )
    condition = fields.Char(string="Condición", )
    warranty = fields.Char(string="Garantía", )
    quantity = fields.Float(string="Cantidad", )
    unit_price = fields.Float(string="Precio unitario", )
    gross_price = fields.Float(string="Precio bruto", )
    sale_fee = fields.Float(string="Comisión Mercado Libre", )
    currency_code = fields.Char(string="Moneda", size=3, )
