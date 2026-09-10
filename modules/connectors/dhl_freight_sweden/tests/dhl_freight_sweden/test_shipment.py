"""DHL Freight (SE API Farm) shipment tests.

The connector books a transport instruction and then prints its documents in
a two-call chain per shipment create. The proxy issues:

    1. POST {transportinstructionapi/v1}/transportinstruction/sendtransportinstruction
    2. POST {printapi/v1}/print/printdocumentsbyid  { shipmentIds: [id], options }

Both requests carry the ``client-key`` header. Product codes serialize as
strings on the wire (e.g. "102", "SPI").
"""

import typing
import unittest
from unittest.mock import patch
from .fixture import gateway, zpl_gateway

import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models


class TestDHLFreightShipment(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    # -- create request serialization (product code as string + product fields)

    def test_create_shipment_request_102(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload102)
        )

        self.assertEqual(lib.to_dict(request.serialize()), ShipmentRequest102)
        self.assertEqual(request.ctx["print_options"], PrintOptions)

    def test_create_shipment_request_232(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload232)
        )

        self.assertEqual(lib.to_dict(request.serialize()), ShipmentRequest232)
        self.assertEqual(request.ctx["print_options"], PrintOptions)

    def test_create_shipment_request_401_doorstep(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload401)
        )
        serialized = lib.to_dict(request.serialize())

        self.assertEqual(serialized["productCode"], "401")
        self.assertIsInstance(serialized["productCode"], str)
        self.assertEqual(
            serialized["additionalServices"]["doorstepDelivery"],
            {"accessCode": 1234},
        )

    def test_create_shipment_request_103_access_point(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload103)
        )
        serialized = lib.to_dict(request.serialize())

        self.assertEqual(serialized["productCode"], "103")
        self.assertIsInstance(serialized["productCode"], str)
        self.assertEqual(_access_point(serialized), AccessPointShop)

    def test_create_shipment_request_202(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload202)
        )
        serialized = lib.to_dict(request.serialize())

        self.assertEqual(serialized["productCode"], "202")
        self.assertIsInstance(serialized["productCode"], str)

    def test_create_shipment_request_109_access_point(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload109)
        )
        serialized = lib.to_dict(request.serialize())

        self.assertEqual(serialized["productCode"], "109")
        self.assertIsInstance(serialized["productCode"], str)
        self.assertEqual(_access_point(serialized), AccessPointStation)

    def test_create_shipment_request_109_access_point_shop(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload109Shop)
        )
        serialized = lib.to_dict(request.serialize())

        self.assertEqual(serialized["productCode"], "109")
        self.assertIsInstance(serialized["productCode"], str)
        self.assertEqual(_access_point(serialized), AccessPointShopDK)

    def test_create_shipment_request_202_customs(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload202Customs)
        )
        serialized = lib.to_dict(request.serialize())

        self.assertEqual(serialized["customsInformation"], CustomsInformation)
        # hsItemId serializes as the raw HS string, not a coerced int.
        hs_item = serialized["customsInformation"]["customsCommodities"][0]["hsItemId"]
        self.assertEqual(hs_item, "7615101090")
        self.assertIsInstance(hs_item, str)

    def test_create_shipment_request_customs_domestic_omits_export_movement(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload102Customs)
        )
        serialized = lib.to_dict(request.serialize())

        document = serialized["customsInformation"]["customsDocuments"][0]
        self.assertEqual(document["type"], "CommercialInvoice")
        self.assertNotIn("transportMovement", document)

    def test_create_shipment_request_without_customs_omits_section(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload202)
        )
        serialized = lib.to_dict(request.serialize())

        self.assertNotIn("customsInformation", serialized)

    def test_create_shipment_request_customs_without_invoice_is_proforma(self):
        # The API requires at least one customs document whenever the customs
        # section is present, so commodities alone still emit a document.
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload202Proforma)
        )
        serialized = lib.to_dict(request.serialize())

        document = serialized["customsInformation"]["customsDocuments"][0]
        self.assertEqual(document["type"], "ProformaInvoice")
        self.assertNotIn("id", document)
        self.assertEqual(
            serialized["customsInformation"]["customsCommodities"][0]["procedureCode"],
            "1042",
        )

    def test_create_shipment_request_payer_from_customs_incoterm(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload202Customs)
        )
        serialized = lib.to_dict(request.serialize())

        self.assertEqual(serialized["payerCode"], {"code": "DAP"})

    def test_create_shipment_request_reference_uses_cu_qualifier(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayloadWithReference)
        )
        serialized = lib.to_dict(request.serialize())

        self.assertEqual(
            serialized["references"],
            [{"qualifier": "CU", "value": "ORDER-2026-042"}],
        )

    def test_create_shipment_request_customs_currency_gap_fill(self):
        # Commodity lines without value_currency inherit the declaration
        # currency (duty currency first, else the commodities' common one).
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload202GapCurrency)
        )
        serialized = lib.to_dict(request.serialize())

        commodities = serialized["customsInformation"]["customsCommodities"]
        self.assertEqual(
            [c["customsValueCurrency"] for c in commodities], ["EUR", "EUR"]
        )
        document = serialized["customsInformation"]["customsDocuments"][0]
        self.assertEqual(document["invoiceCurrency"], "EUR")

    def test_shipment_customs_mixed_currency_surfaces_field_error(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request"):
            details, messages = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**ShipmentPayload202MixedCurrency)
                )
                .from_(gateway)
                .parse()
            )

        self.assertIsNone(details)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].code, "SHIPPING_SDK_FIELD_ERROR")
        self.assertIn("customs.commodities.value_currency", messages[0].details)
        self.assertIn("EUR", messages[0].message)
        self.assertIn("SEK", messages[0].message)

    def test_shipment_service_point_missing_details_surfaces_field_error(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request"):
            details, messages = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**ShipmentPayload103MissingDetails)
                )
                .from_(gateway)
                .parse()
            )

        self.assertIsNone(details)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].code, "SHIPPING_SDK_FIELD_ERROR")
        self.assertEqual(
            set(messages[0].details),
            {
                "dhl_freight_sweden_service_point_name",
                "dhl_freight_sweden_service_point_street",
                "dhl_freight_sweden_service_point_city",
                "dhl_freight_sweden_service_point_postal_code",
                "dhl_freight_sweden_service_point_country_code",
            },
        )
        self.assertIn("service point details", messages[0].message)
        self.assertIn("postal_code", messages[0].message)

    # -- proxy: two sequential calls (book -> print) with client-key header

    def test_create_shipment(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [BookingResponse102, PrintResponse]
            karrio.Shipment.create(
                models.ShipmentRequest(**ShipmentPayload102)
            ).from_(gateway)

        booking_call, print_call = mock.call_args_list
        self.assertEqual(
            booking_call.kwargs["url"],
            f"{gateway.settings.transport_instruction_url}"
            "/transportinstruction/sendtransportinstruction",
        )
        self.assertEqual(
            print_call.kwargs["url"],
            f"{gateway.settings.print_url}/print/printdocumentsbyid",
        )
        self.assertEqual(
            booking_call.kwargs["headers"]["client-key"],
            gateway.settings.client_key,
        )
        self.assertEqual(
            print_call.kwargs["headers"]["client-key"],
            gateway.settings.client_key,
        )
        self.assertEqual(lib.to_dict(print_call.kwargs["data"]), PrintByIdRequest)

    # -- parse response (book -> print => ShipmentDetails)

    def test_parse_shipment_response_102(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [BookingResponse102, PrintResponse]
            parsed_response = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload102))
                .from_(gateway)
                .parse()
            )

        self.assertListEqual(
            lib.to_dict(parsed_response),
            [_expected_details("TI-102-0001", "102"), []],
        )

    def test_parse_shipment_response_232(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [BookingResponse232, PrintResponse]
            parsed_response = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload232))
                .from_(gateway)
                .parse()
            )

        self.assertListEqual(
            lib.to_dict(parsed_response),
            [_expected_details("TI-232-0001", "232"), []],
        )

    def test_parse_shipment_response_401(self):
        self._assert_labelled_parse(ShipmentPayload401, "TI-401-0001", 401)

    def test_parse_shipment_response_103(self):
        self._assert_labelled_parse(ShipmentPayload103, "TI-103-0001", 103)

    def test_parse_shipment_response_202(self):
        self._assert_labelled_parse(ShipmentPayload202, "TI-202-0001", 202)

    def test_parse_shipment_response_109(self):
        self._assert_labelled_parse(ShipmentPayload109, "TI-109-0001", 109)

    # -- label type resolution (document magic prefix -> contentType -> config)

    def test_parse_label_type_pdf_magic_over_zpl_config(self):
        # The account emits PDF regardless of the connection's label type
        # (live sandbox 2026-09-10); the decoded document magic prefix wins
        # over both contentType and the connection config tag.
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [BookingResponse102, PdfMagicPrintResponse]
            details, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload102))
                .from_(zpl_gateway)
                .parse()
            )

        self.assertEqual(messages, [])
        self.assertIsNotNone(details)
        self.assertEqual(details.label_type, "PDF")
        self.assertEqual(details.docs.label, PdfMagicBase64)

    def test_parse_label_type_zpl_magic_without_content_type(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [BookingResponse102, ZplMagicPrintResponse]
            details, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload102))
                .from_(gateway)
                .parse()
            )

        self.assertEqual(messages, [])
        self.assertIsNotNone(details)
        self.assertEqual(details.label_type, "ZPL")
        self.assertEqual(details.docs.label, ZplMagicBase64)

    def test_parse_label_type_config_last_resort(self):
        # Without a known magic prefix or contentType, the connection's
        # label_type tag is the last resort.
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [BookingResponse102, PlainTextPrintResponse]
            details, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload102))
                .from_(zpl_gateway)
                .parse()
            )

        self.assertEqual(messages, [])
        self.assertIsNotNone(details)
        self.assertEqual(details.label_type, "ZPL")
        self.assertEqual(details.docs.label, PlainTextBase64)

    def _assert_labelled_parse(self, payload: dict, shipment_id: str, product: int):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [_booking(shipment_id, product), PrintResponse]
            details, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**payload))
                .from_(gateway)
                .parse()
            )

        self.assertEqual(messages, [])
        self.assertIsNotNone(details)
        self.assertEqual(details.tracking_number, shipment_id)
        self.assertEqual(details.docs.label, LabelBase64)
        self.assertEqual(details.label_type, "PDF")
        self.assertEqual(
            details.meta["carrier_tracking_link"],
            gateway.settings.tracking_url.format(shipment_id),
        )

    # -- error parsing

    def test_parse_error_response(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [ErrorResponse, "{}"]
            parsed_response = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload102))
                .from_(gateway)
                .parse()
            )

        self.assertListEqual(lib.to_dict(parsed_response), ParsedErrorResponse)


if __name__ == "__main__":
    unittest.main()


def _access_point(serialized: dict) -> dict:
    return next(
        party
        for party in serialized["parties"]
        if party.get("type") == "AccessPoint"
    )


def _booking(shipment_id: str, product: int) -> str:
    return lib.to_json(
        {
            "status": "OK",
            "transportInstruction": {
                "id": shipment_id,
                "productCode": product,
                "totalNumberOfPieces": 1,
                "totalWeight": 5.0,
                "payerCode": {"code": "1"},
                "pieces": [
                    {"id": [f"{shipment_id}-P1"], "numberOfPieces": 1, "weight": 5.0}
                ],
            },
        }
    )


def _expected_details(shipment_id: str, product: str) -> dict:
    return {
        "carrier_id": "dhl_freight_sweden",
        "carrier_name": "dhl_freight_sweden",
        "tracking_number": shipment_id,
        "shipment_identifier": shipment_id,
        "label_type": "PDF",
        "docs": {"label": LabelBase64},
        "meta": {
            "carrier_tracking_link": gateway.settings.tracking_url.format(shipment_id),
            "product_code": product,
        },
    }


LabelBase64 = "JVBERi0xLjQgc2FtcGxlIGxhYmVs"

_shipper = {
    "company_name": "Test Shipper AB",
    "person_name": "Sven Svensson",
    "address_line1": "Kungsgatan 1",
    "city": "Stockholm",
    "postal_code": "11143",
    "country_code": "SE",
    "phone_number": "+46 8 123 456",
    "email": "shipper@example.se",
}

_recipient_se = {
    "company_name": "Test Recipient AB",
    "person_name": "Anna Andersson",
    "address_line1": "Storgatan 2",
    "city": "Goteborg",
    "postal_code": "41103",
    "country_code": "SE",
    "phone_number": "+46 31 987 654",
    "email": "recipient@example.se",
}

_recipient_de = {
    **_recipient_se,
    "city": "Berlin",
    "postal_code": "10115",
    "country_code": "DE",
}

_recipient_dk = {
    **_recipient_se,
    "city": "Frederiksberg",
    "postal_code": "2000",
    "country_code": "DK",
}

_parcel = {
    "weight": 5.0,
    "width": 20.0,
    "height": 15.0,
    "length": 30.0,
    "weight_unit": "KG",
    "dimension_unit": "CM",
    "reference_number": "REF-001",
}


def _payload(service: str, recipient: dict, options: typing.Optional[dict] = None) -> dict:
    return {
        "service": service,
        "shipper": _shipper,
        "recipient": recipient,
        "parcels": [_parcel],
        "options": options or {},
    }


# Domestic (Sweden)
ShipmentPayload102 = _payload("dhl_freight_sweden_paket", _recipient_se)
ShipmentPayload401 = _payload(
    "dhl_freight_sweden_home_delivery_b2c",
    _recipient_se,
    {"dhl_freight_sweden_doorstep_access_code": 1234},
)
ShipmentPayload103 = _payload(
    "dhl_freight_sweden_service_point_b2c",
    _recipient_se,
    {
        "dhl_freight_sweden_service_point": "SE-230500",
        "dhl_freight_sweden_service_point_type": "ParcelShop",
        "dhl_freight_sweden_service_point_name": "KUNGSKLIPPAN TOBAK, T-BANA RÅDHUSET",
        "dhl_freight_sweden_service_point_street": "KUNGSKLIPPAN 17",
        "dhl_freight_sweden_service_point_city": "STOCKHOLM",
        "dhl_freight_sweden_service_point_postal_code": "11225",
        "dhl_freight_sweden_service_point_country_code": "SE",
    },
)

# An id-only service point: DHL rejects the AccessPoint party without name
# and address (validation errors 22001/22006, live sandbox 2026-09-10), so
# the request surfaces a field error instead of a carrier 400.
ShipmentPayload103MissingDetails = _payload(
    "dhl_freight_sweden_service_point_b2c",
    _recipient_se,
    {
        "dhl_freight_sweden_service_point": "SE-230500",
        "dhl_freight_sweden_service_point_type": "ParcelShop",
    },
)

# International
ShipmentPayload232 = _payload("dhl_freight_sweden_euroconnect_plus", _recipient_de)
ShipmentPayload202 = _payload("dhl_freight_sweden_road_freight_standard", _recipient_de)
# 109 access points: DK allows both sub types per the product catalog
# (GET /productapi/v1/products/109); DE allows ParcelShop only.
ShipmentPayload109 = _payload(
    "dhl_freight_sweden_parcel_connect_b2c",
    _recipient_dk,
    {
        "dhl_freight_sweden_service_point": "8009-591371",
        "dhl_freight_sweden_service_point_type": "ParcelStation",
        "dhl_freight_sweden_service_point_name": "Pakkeboks Westmarket",
        "dhl_freight_sweden_service_point_street": "Matthæusgade 46",
        "dhl_freight_sweden_service_point_city": "København V",
        "dhl_freight_sweden_service_point_postal_code": "1600",
        "dhl_freight_sweden_service_point_country_code": "DK",
    },
)
ShipmentPayload109Shop = _payload(
    "dhl_freight_sweden_parcel_connect_b2c",
    _recipient_dk,
    {
        "dhl_freight_sweden_service_point": "8009-591479",
        "dhl_freight_sweden_service_point_type": "ParcelShop",
        "dhl_freight_sweden_service_point_name": "Føtex Vesterbrogade",
        "dhl_freight_sweden_service_point_street": "Vesterbrogade 74",
        "dhl_freight_sweden_service_point_city": "København V",
        "dhl_freight_sweden_service_point_postal_code": "1620",
        "dhl_freight_sweden_service_point_country_code": "DK",
    },
)

Customs = {
    "commodities": [
        {
            "description": "Aluminium brackets",
            "hs_code": "7615101090",
            "quantity": 4,
            "weight": 2.5,
            "value_amount": 1200.0,
            "value_currency": "EUR",
            "origin_country": "SE",
        }
    ],
    "content_type": "merchandise",
    "incoterm": "DAP",
    "invoice": "INV-2026-001",
    "invoice_date": "2026-09-08",
    "commercial_invoice": True,
    "duty": {"paid_by": "sender", "currency": "EUR", "declared_value": 1200.0},
}

ShipmentPayload202Customs = {
    **_payload("dhl_freight_sweden_road_freight_standard", _recipient_de),
    "customs": Customs,
}

ShipmentPayload102Customs = {
    **_payload("dhl_freight_sweden_paket", _recipient_se),
    "customs": Customs,
}

ShipmentPayload202Proforma = {
    **_payload("dhl_freight_sweden_road_freight_standard", _recipient_de),
    "customs": {
        "commodities": Customs["commodities"],
        "incoterm": "DAP",
    },
}

ShipmentPayloadWithReference = {
    **_payload("dhl_freight_sweden_paket", _recipient_se),
    "reference": "ORDER-2026-042",
}

# The second commodity omits value_currency and inherits the duty currency.
_gap_currency_commodity = {
    key: value
    for key, value in Customs["commodities"][0].items()
    if key != "value_currency"
}

ShipmentPayload202GapCurrency = {
    **_payload("dhl_freight_sweden_road_freight_standard", _recipient_de),
    "customs": {
        "commodities": [
            _gap_currency_commodity,
            {
                **Customs["commodities"][0],
                "description": "Steel fasteners",
                "hs_code": "7318159800",
            },
        ],
        "incoterm": "DAP",
        "duty": {"paid_by": "sender", "currency": "EUR", "declared_value": 1250.0},
    },
}

ShipmentPayload202MixedCurrency = {
    **_payload("dhl_freight_sweden_road_freight_standard", _recipient_de),
    "customs": {
        "commodities": [
            Customs["commodities"][0],
            {
                **Customs["commodities"][0],
                "description": "Steel fasteners",
                "hs_code": "7318159800",
                "value_currency": "SEK",
            },
        ],
        "incoterm": "DAP",
    },
}

CustomsInformation = {
    "customsDocuments": [
        {
            "id": "INV-2026-001",
            "type": "CommercialInvoice",
            "transportMovement": "Export",
            "invoiceDate": "2026-09-08",
            "invoiceCurrency": "EUR",
            "invoiceAmount": 1200.0,
        }
    ],
    "customsCommodities": [
        {
            "countryCodeOfOrigin": "SE",
            "customsValueCurrency": "EUR",
            "customsValue": 1200.0,
            "hsItemId": "7615101090",
            "commodityDescription": "Aluminium brackets",
            "procedureCode": "1042",
            "netWeight": 2.5,
            "numberOfUnits": 4,
        }
    ],
}

PrintOptions = {
    "label": True,
    "pageOptions": {"pageType": "Label"},
}

# The by-id print payload the proxy completes with the runtime shipment id.
PrintByIdRequest = {
    "shipmentIds": ["TI-102-0001"],
    "options": PrintOptions,
}

# Full AccessPoint parties as booked against the live sandbox 2026-09-10:
# DHL requires name and address (street, cityName, postalCode, countryCode)
# alongside the id (validation errors 22001/22006 without them).
AccessPointShop = {
    "id": "SE-230500",
    "type": "AccessPoint",
    "subType": "ParcelShop",
    "name": "KUNGSKLIPPAN TOBAK, T-BANA RÅDHUSET",
    "address": {
        "street": "KUNGSKLIPPAN 17",
        "cityName": "STOCKHOLM",
        "postalCode": "11225",
        "countryCode": "SE",
    },
}
AccessPointStation = {
    "id": "8009-591371",
    "type": "AccessPoint",
    "subType": "ParcelStation",
    "name": "Pakkeboks Westmarket",
    "address": {
        "street": "Matthæusgade 46",
        "cityName": "København V",
        "postalCode": "1600",
        "countryCode": "DK",
    },
}
AccessPointShopDK = {
    "id": "8009-591479",
    "type": "AccessPoint",
    "subType": "ParcelShop",
    "name": "Føtex Vesterbrogade",
    "address": {
        "street": "Vesterbrogade 74",
        "cityName": "København V",
        "postalCode": "1620",
        "countryCode": "DK",
    },
}

ShipmentRequest102 = {
    "additionalServices": {},
    "parties": [
        {
            "address": {
                "cityName": "Stockholm",
                "countryCode": "SE",
                "postalCode": "11143",
                "street": "Kungsgatan 1",
            },
            "contactName": "Sven Svensson",
            "email": "shipper@example.se",
            "id": "1234567",
            "name": "Test Shipper AB",
            "phone": "+46 8 123 456",
            "type": "Consignor",
        },
        {
            "address": {
                "cityName": "Goteborg",
                "countryCode": "SE",
                "postalCode": "41103",
                "street": "Storgatan 2",
            },
            "contactName": "Anna Andersson",
            "email": "recipient@example.se",
            "name": "Test Recipient AB",
            "phone": "+46 31 987 654",
            "type": "Consignee",
        },
    ],
    "payerCode": {"code": "1"},
    "pieces": [
        {
            "height": 15.0,
            "length": 30.0,
            "marksAndNumbers": "REF-001",
            "numberOfPieces": 1,
            "volume": 0.01,
            "weight": 5.0,
            "width": 20.0,
        }
    ],
    "productCode": "102",
    "totalNumberOfPieces": 1,
    "totalWeight": 5.0,
}

ShipmentRequest232 = {
    "additionalServices": {},
    "parties": [
        {
            "address": {
                "cityName": "Stockholm",
                "countryCode": "SE",
                "postalCode": "11143",
                "street": "Kungsgatan 1",
            },
            "contactName": "Sven Svensson",
            "email": "shipper@example.se",
            "id": "1234567",
            "name": "Test Shipper AB",
            "phone": "+46 8 123 456",
            "type": "Consignor",
        },
        {
            "address": {
                "cityName": "Berlin",
                "countryCode": "DE",
                "postalCode": "10115",
                "street": "Storgatan 2",
            },
            "contactName": "Anna Andersson",
            "email": "recipient@example.se",
            "name": "Test Recipient AB",
            "phone": "+46 31 987 654",
            "type": "Consignee",
        },
    ],
    "payerCode": {"code": "1"},
    "pieces": [
        {
            "height": 15.0,
            "length": 30.0,
            "marksAndNumbers": "REF-001",
            "numberOfPieces": 1,
            "volume": 0.01,
            "weight": 5.0,
            "width": 20.0,
        }
    ],
    "productCode": "232",
    "totalNumberOfPieces": 1,
    "totalWeight": 5.0,
}

BookingResponse102 = _booking("TI-102-0001", 102)
BookingResponse232 = _booking("TI-232-0001", 232)

PrintResponse = lib.to_json(
    {
        "reports": [
            {
                "name": "Label",
                "content": LabelBase64,
                "contentType": "application/pdf",
                "type": "Label",
                "valid": True,
            }
        ]
    }
)

# Magic-prefix fixtures: content values are base64 strings in the real API
# shape, with contentType absent or opaque so only the decoded document
# bytes identify the format.
PdfMagicBase64 = "JVBERi0xLjYgc2FtcGxlIGxhYmVs"  # b"%PDF-1.6 sample label"
ZplMagicBase64 = "XlhBCl5GTzUwLDUwXkZEVEVTVF5GUwpeWFo="  # b"^XA\n^FO50,50^FDTEST^FS\n^XZ"
PlainTextBase64 = "cGxhaW4gdGV4dCBkb2N1bWVudCBieXRlcw=="  # b"plain text document bytes"

PdfMagicPrintResponse = lib.to_json(
    {
        "reports": [
            {
                "name": "Label",
                "content": PdfMagicBase64,
                "type": "Label",
                "valid": True,
            }
        ]
    }
)

ZplMagicPrintResponse = lib.to_json(
    {
        "reports": [
            {
                "name": "Label",
                "content": ZplMagicBase64,
                "type": "Label",
                "valid": True,
            }
        ]
    }
)

PlainTextPrintResponse = lib.to_json(
    {
        "reports": [
            {
                "name": "Label",
                "content": PlainTextBase64,
                "contentType": "application/octet-stream",
                "type": "Label",
                "valid": True,
            }
        ]
    }
)

ErrorResponse = lib.to_json(
    {
        "status": "BadRequest",
        "errorMessage": "Validation failed",
        "validationErrors": [
            {
                "field": "productCode",
                "errorCode": 4001,
                "message": "Unknown product code",
            },
            {
                "field": "parties",
                "errorCode": 4002,
                "message": "Consignee address invalid",
                "incompatibleFields": ["parties[1].address.postalCode"],
            },
        ],
    }
)

ParsedErrorResponse = [
    None,
    [
        {
            "carrier_id": "dhl_freight_sweden",
            "carrier_name": "dhl_freight_sweden",
            "code": "4001",
            "message": "Unknown product code",
            "details": {"field": "productCode"},
        },
        {
            "carrier_id": "dhl_freight_sweden",
            "carrier_name": "dhl_freight_sweden",
            "code": "4002",
            "message": "Consignee address invalid",
            "details": {
                "field": "parties",
                "incompatible_fields": ["parties[1].address.postalCode"],
            },
        },
    ],
]
