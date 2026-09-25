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
from .fixture import (
    gateway,
    warn_gateway,
    warn_case_gateway,
    enforce_gateway,
    unrecognized_gateway,
    zpl_gateway,
)

import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models
from karrio.providers.dhl_freight_sweden.address import PostalCodeNotServableError


class TestDHLFreightShipment(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

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

    def test_create_shipment_request_customs_document_to_norway(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload109CustomsNO)
        )
        serialized = lib.to_dict(request.serialize())

        self.assertEqual(
            serialized["customsInformation"]["customsDocuments"],
            [CustomsDocumentNO],
        )

    def test_create_shipment_request_customs_without_eori_omits_eori(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload202Customs)
        )
        serialized = lib.to_dict(request.serialize())

        document = serialized["customsInformation"]["customsDocuments"][0]
        self.assertNotIn("eori", document)

    def test_create_shipment_request_invoice_without_commercial_flag_is_proforma(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload202InvoiceNotCommercial)
        )
        serialized = lib.to_dict(request.serialize())

        document = serialized["customsInformation"]["customsDocuments"][0]
        self.assertEqual(document["type"], "ProformaInvoice")
        self.assertEqual(document["id"], "INV-2026-001")

    def test_create_shipment_request_merchandise_without_flag_is_proforma(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload202MerchandiseNoFlag)
        )
        serialized = lib.to_dict(request.serialize())

        document = serialized["customsInformation"]["customsDocuments"][0]
        self.assertEqual(document["type"], "ProformaInvoice")

    def test_create_shipment_request_transport_movement_from_shipper_country(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload202CustomsWithinNO)
        )
        serialized = lib.to_dict(request.serialize())

        document = serialized["customsInformation"]["customsDocuments"][0]
        self.assertNotIn("transportMovement", document)

    def test_create_shipment_request_customs_without_service_option(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload109CustomsNO)
        )
        serialized = lib.to_dict(request.serialize())

        self.assertFalse(
            set(serialized.get("additionalServices") or {}) & CustomsServiceKeys
        )

    def test_create_shipment_request_customs_services(self):
        cases = [
            (
                {"dhl_freight_sweden_customs_handling_standard": True},
                {"customsHandlingStandard": True},
            ),
            (
                {"dhl_freight_sweden_customs_handling_full_service": True},
                {"customsHandlingFullService": True},
            ),
            (
                {
                    "dhl_freight_sweden_customs_own_declaration": True,
                    "dhl_freight_sweden_customs_own_declaration_id": "26SE000000000000A1",
                },
                {"customsCustomersOwnDeclaration": {"customsId": "26SE000000000000A1"}},
            ),
            (
                {
                    "dhl_freight_sweden_customs_joint_declaration": True,
                    "dhl_freight_sweden_customs_joint_declaration_id": "SFID-0001",
                },
                {"customsJointDeclaration": {"sfid": "SFID-0001"}},
            ),
        ]

        for options, expected in cases:
            with self.subTest(options=options):
                request = gateway.mapper.create_shipment_request(
                    models.ShipmentRequest(
                        **{**ShipmentPayload109CustomsNO, "options": options}
                    )
                )
                serialized = lib.to_dict(request.serialize())

                self.assertEqual(serialized["additionalServices"], expected)

    def test_create_shipment_request_customs_services_unset_flags(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(
                **{
                    **ShipmentPayload109CustomsNO,
                    "options": {
                        "dhl_freight_sweden_customs_handling_standard": False,
                        "dhl_freight_sweden_customs_handling_full_service": False,
                        "dhl_freight_sweden_customs_own_declaration": False,
                        "dhl_freight_sweden_customs_joint_declaration": False,
                    },
                }
            )
        )
        serialized = lib.to_dict(request.serialize())

        self.assertFalse(
            set(serialized.get("additionalServices") or {}) & CustomsServiceKeys
        )

    def test_create_shipment_request_voec_number_selects_voec_service(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload109CustomsVOEC)
        )
        serialized = lib.to_dict(request.serialize())

        self.assertEqual(
            serialized["additionalServices"],
            {"voecSupplyVAT": {"vatId": "VOEC2012345"}},
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

    def test_create_shipment_request_instructions(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayloadWithInstructions)
        )
        serialized = lib.to_dict(request.serialize())

        self.assertEqual(serialized["pickupInstruction"], "Ring the bell on arrival")
        self.assertEqual(serialized["deliveryInstruction"], "Leave at reception")

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

    def test_shipment_customs_service_missing_identifier_surfaces_field_error(self):
        cases = [
            (
                ShipmentPayload109StandardWithoutEORI,
                "customs.options.eori_number",
                "EORI",
            ),
            (
                _with_options(
                    ShipmentPayload109CustomsNO,
                    {"dhl_freight_sweden_customs_own_declaration": True},
                ),
                "dhl_freight_sweden_customs_own_declaration_id",
                "customs identifier",
            ),
            (
                _with_options(
                    ShipmentPayload109CustomsNO,
                    {
                        "dhl_freight_sweden_customs_own_declaration": True,
                        "dhl_freight_sweden_customs_own_declaration_id": " ",
                    },
                ),
                "dhl_freight_sweden_customs_own_declaration_id",
                "customs identifier",
            ),
            (
                _with_options(
                    ShipmentPayload109CustomsNO,
                    {"dhl_freight_sweden_customs_joint_declaration": True},
                ),
                "dhl_freight_sweden_customs_joint_declaration_id",
                "SFID",
            ),
            (
                _with_options(
                    ShipmentPayload109CustomsNO,
                    {
                        "dhl_freight_sweden_customs_joint_declaration": True,
                        "dhl_freight_sweden_customs_joint_declaration_id": " ",
                    },
                ),
                "dhl_freight_sweden_customs_joint_declaration_id",
                "SFID",
            ),
        ]

        for payload, field, label in cases:
            with self.subTest(field=field, options=payload["options"]):
                with patch(
                    "karrio.mappers.dhl_freight_sweden.proxy.lib.request"
                ) as mock:
                    details, messages = (
                        karrio.Shipment.create(models.ShipmentRequest(**payload))
                        .from_(gateway)
                        .parse()
                    )

                mock.assert_not_called()
                self.assertIsNone(details)
                self.assertEqual(len(messages), 1)
                self.assertEqual(messages[0].code, "SHIPPING_SDK_FIELD_ERROR")
                self.assertEqual(set(messages[0].details), {field})
                self.assertIn(label, messages[0].message)

    def test_shipment_customs_identifier_without_selector_selects_no_service(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [BookingResponse102, PrintResponse]
            karrio.Shipment.create(
                models.ShipmentRequest(
                    **_with_options(
                        ShipmentPayload109CustomsNO,
                        {
                            "dhl_freight_sweden_customs_own_declaration_id": "26SE000000000000A1",
                            "dhl_freight_sweden_customs_joint_declaration_id": "SFID-0001",
                        },
                    )
                )
            ).from_(gateway)

        booking = lib.to_dict(mock.call_args_list[0].kwargs["data"])
        self.assertFalse(
            set(booking.get("additionalServices") or {}) & CustomsServiceKeys
        )

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

    def test_parse_label_type_pdf_magic_over_zpl_config(self):
        # The account emits PDF regardless of the connection's label type
        # (live sandbox 2026-09-10); the decoded document magic prefix
        # outranks the connection config tag.
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

    def test_parse_label_type_zpl_magic_over_pdf_content_type(self):
        # The decoded document bytes identify the format when the report
        # contentType disagrees.
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [BookingResponse102, ZplBytesPdfContentTypePrintResponse]
            details, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload102))
                .from_(gateway)
                .parse()
            )

        self.assertEqual(messages, [])
        self.assertIsNotNone(details)
        self.assertEqual(details.label_type, "ZPL")
        self.assertEqual(details.docs.label, ZplMagicBase64)

    def test_parse_label_type_pdf_magic_over_zpl_content_type(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [BookingResponse102, PdfBytesZplContentTypePrintResponse]
            details, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload102))
                .from_(gateway)
                .parse()
            )

        self.assertEqual(messages, [])
        self.assertIsNotNone(details)
        self.assertEqual(details.label_type, "PDF")
        self.assertEqual(details.docs.label, PdfMagicBase64)

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

    def test_parse_error_response(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [ErrorResponse, "{}"]
            parsed_response = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload102))
                .from_(gateway)
                .parse()
            )

        self.assertListEqual(lib.to_dict(parsed_response), ParsedErrorResponse)

    def _called_urls(self, mock) -> typing.List[str]:
        return [call.kwargs["url"] for call in mock.call_args_list]

    def test_preflight_off_makes_no_route_call(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [BookingResponse118, PrintResponse]
            details, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload118))
                .from_(gateway)
                .parse()
            )

        self.assertEqual(messages, [])
        self.assertEqual(details.tracking_number, "TI-118-0001")
        self.assertEqual(
            self._called_urls(mock),
            [
                f"{gateway.settings.transport_instruction_url}"
                "/transportinstruction/sendtransportinstruction",
                f"{gateway.settings.print_url}/print/printdocumentsbyid",
            ],
        )

    def test_preflight_case_insensitive_mode_resolves(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [RouteResponseGoteborg, BookingResponse118, PrintResponse]
            details, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload118))
                .from_(warn_case_gateway)
                .parse()
            )

        self.assertEqual(messages, [])
        self.assertEqual(details.tracking_number, "TI-118-0001")
        self.assertTrue(
            self._called_urls(mock)[0].endswith("/postalcodes/SE/41103/route")
        )

    def test_preflight_unrecognized_mode_skips_check(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [BookingResponse118, PrintResponse]
            details, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload118))
                .from_(unrecognized_gateway)
                .parse()
            )

        self.assertEqual(messages, [])
        self.assertEqual(details.tracking_number, "TI-118-0001")
        self.assertEqual(
            self._called_urls(mock),
            [
                f"{gateway.settings.transport_instruction_url}"
                "/transportinstruction/sendtransportinstruction",
                f"{gateway.settings.print_url}/print/printdocumentsbyid",
            ],
        )

    def test_preflight_warn_servable_books_without_messages(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [RouteResponseGoteborg, BookingResponse118, PrintResponse]
            details, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload118))
                .from_(warn_gateway)
                .parse()
            )

        self.assertEqual(messages, [])
        self.assertEqual(details.tracking_number, "TI-118-0001")
        self.assertTrue(
            self._called_urls(mock)[0].endswith("/postalcodes/SE/41103/route")
        )

    def test_preflight_warn_not_servable_books_with_warning(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [RouteResponseKiruna, BookingResponse118, PrintResponse]
            details, messages = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**ShipmentPayload118Kiruna)
                )
                .from_(warn_gateway)
                .parse()
            )

        self.assertIsNotNone(details)
        self.assertEqual(details.tracking_number, "TI-118-0001")
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].code, "postal_code_not_servable")
        self.assertEqual(
            messages[0].details, dict(postal_code="98138", product="118")
        )
        self.assertIn("98138", messages[0].message)

    def test_preflight_enforce_not_servable_blocks_booking(self):
        request = enforce_gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload118Kiruna)
        )
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.return_value = RouteResponseKiruna
            with self.assertRaises(PostalCodeNotServableError) as context:
                enforce_gateway.proxy.create_shipment(request)

        self.assertEqual(context.exception.code, "SHIPPING_SDK_FIELD_ERROR")
        self.assertIn("98138", str(context.exception))
        urls = self._called_urls(mock)
        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].endswith("/postalcodes/SE/98138/route"))

    def test_preflight_enforce_invalid_code_blocks_booking(self):
        request = enforce_gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**ShipmentPayload118Invalid)
        )
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.return_value = RouteLookupInvalidCode
            with self.assertRaises(PostalCodeNotServableError) as context:
                enforce_gateway.proxy.create_shipment(request)

        self.assertIn("99999", str(context.exception))
        urls = self._called_urls(mock)
        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].endswith("/postalcodes/SE/99999/route"))

    def test_preflight_enforce_outage_fails_open(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [
                ConnectionError("route API unreachable"),
                BookingResponse118,
                PrintResponse,
            ]
            details, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload118))
                .from_(enforce_gateway)
                .parse()
            )

        self.assertIsNotNone(details)
        self.assertEqual(details.tracking_number, "TI-118-0001")
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].code, "address_validation_unavailable")

    def test_preflight_enforce_unavailable_api_fails_open(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [RouteApiUnavailable, BookingResponse118, PrintResponse]
            details, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload118))
                .from_(enforce_gateway)
                .parse()
            )

        self.assertIsNotNone(details)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].code, "address_validation_unavailable")

    def test_preflight_enforce_non_118_service_skips_check(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [BookingResponse102, PrintResponse]
            details, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload102))
                .from_(enforce_gateway)
                .parse()
            )

        self.assertEqual(messages, [])
        self.assertEqual(details.tracking_number, "TI-102-0001")
        self.assertEqual(len(self._called_urls(mock)), 2)

    def test_preflight_enforce_non_se_consignee_skips_check(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [BookingResponse118, PrintResponse]
            details, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload118De))
                .from_(enforce_gateway)
                .parse()
            )

        self.assertEqual(messages, [])
        self.assertEqual(details.tracking_number, "TI-118-0001")
        self.assertEqual(len(self._called_urls(mock)), 2)


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

# Pre-flight trigger scope: product 118 (the only product with a documented
# per-product route flag) to Swedish consignees with a postal code.
_recipient_kiruna = {
    **_recipient_se,
    "city": "Kiruna",
    "postal_code": "98138",
}

_recipient_invalid_postal = {
    **_recipient_se,
    "postal_code": "99999",
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


def _with_options(payload: dict, options: dict) -> dict:
    return {**payload, "options": options}


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
ShipmentPayload118 = _payload(
    "dhl_freight_sweden_hemleverans_paket_b2c", _recipient_se
)
ShipmentPayload118Kiruna = _payload(
    "dhl_freight_sweden_hemleverans_paket_b2c", _recipient_kiruna
)
ShipmentPayload118Invalid = _payload(
    "dhl_freight_sweden_hemleverans_paket_b2c", _recipient_invalid_postal
)
ShipmentPayload118De = _payload(
    "dhl_freight_sweden_hemleverans_paket_b2c", _recipient_de
)
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

_recipient_no = {
    **_recipient_se,
    "city": "Oslo",
    "postal_code": "0154",
    "country_code": "NO",
}

_shipper_no = {
    **_shipper,
    "city": "Bergen",
    "postal_code": "5003",
    "country_code": "NO",
}

CustomsNO = {
    **Customs,
    "duty": {"paid_by": "sender", "currency": "SEK", "declared_value": 2500.0},
    "commodities": [
        {**Customs["commodities"][0], "value_amount": 2500.0, "value_currency": "SEK"}
    ],
    "options": {"eori_number": "SE5560000001"},
}

ShipmentPayload109CustomsNO = {
    **_payload("dhl_freight_sweden_parcel_connect_b2c", _recipient_no),
    "customs": CustomsNO,
}

CustomsDocumentNO = {
    "id": "INV-2026-001",
    "type": "CommercialInvoice",
    "transportMovement": "Export",
    "invoiceDate": "2026-09-08",
    "invoiceCurrency": "SEK",
    "invoiceAmount": 2500.0,
    "eori": "SE5560000001",
}

ShipmentPayload109CustomsVOEC = {
    **ShipmentPayload109CustomsNO,
    "customs": {
        **CustomsNO,
        "options": {**CustomsNO["options"], "voec_number": "VOEC2012345"},
    },
}

ShipmentPayload109StandardWithoutEORI = {
    **ShipmentPayload109CustomsNO,
    "customs": {**CustomsNO, "options": {}},
    "options": {"dhl_freight_sweden_customs_handling_standard": True},
}

CustomsServiceKeys = {
    "customsHandlingStandard",
    "customsHandlingFullService",
    "customsCustomersOwnDeclaration",
    "customsJointDeclaration",
    "voecSupplyVAT",
}

ShipmentPayload202InvoiceNotCommercial = {
    **_payload("dhl_freight_sweden_road_freight_standard", _recipient_de),
    "customs": {**Customs, "commercial_invoice": False},
}

ShipmentPayload202MerchandiseNoFlag = {
    **_payload("dhl_freight_sweden_road_freight_standard", _recipient_de),
    "customs": {
        key: value for key, value in Customs.items() if key != "commercial_invoice"
    },
}

ShipmentPayload202CustomsWithinNO = {
    **_payload("dhl_freight_sweden_road_freight_standard", _recipient_no),
    "shipper": _shipper_no,
    "customs": Customs,
}

ShipmentPayloadWithReference = {
    **_payload("dhl_freight_sweden_paket", _recipient_se),
    "reference": "ORDER-2026-042",
}

# Universal instruction options (SDK category INSTRUCTIONS) map onto the
# transport instruction's free-text driver instructions.
ShipmentPayloadWithInstructions = _payload(
    "dhl_freight_sweden_paket",
    _recipient_se,
    {
        "shipper_instructions": "Ring the bell on arrival",
        "recipient_instructions": "Leave at reception",
    },
)

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
BookingResponse118 = _booking("TI-118-0001", 118)

# Route fixtures captured live from the sandbox PostalCodes API on
# 2026-09-17 (GET /postalcodes/SE/{pc}/route); values are verbatim.
# Göteborg 41103 is servable for product 118; Kiruna 98138 is generally
# bookable without home delivery (homeDeliveryParcel false).
RouteResponseGoteborg = """{
  "countryCode": "SE",
  "postalCode": "41103",
  "city": "GÖTEBORG",
  "lineHaul": "400",
  "terminalId": "2210",
  "deviating": "0",
  "updatedDate": "1999-11-29T00:00:00",
  "bookable": true,
  "homeDeliveryParcel": true
}"""

RouteResponseKiruna = """{
  "countryCode": "SE",
  "postalCode": "98138",
  "city": "KIRUNA",
  "lineHaul": "950",
  "terminalId": "4850",
  "deviating": "0",
  "updatedDate": "2026-07-02T22:00:03",
  "bookable": true,
  "homeDeliveryParcel": false
}"""

# The 400 body captured for postal code 99999, in the form
# ``lib.error_decoder`` hands to the caller: the live wire body plus the
# HTTP metadata the decoder adds (the mocked ``lib.request`` stands in for
# the whole request-and-decode step).
RouteLookupInvalidCode = dict(
    Status=400,
    ErrorCode=16010,
    UserMessage="Post code '99999' not found.",
    http_status=400,
    http_message="Bad Request",
)

# A 5xx body with the decoder's metadata is an infrastructure failure
# rather than a definitive rejection, so bookings fail open.
RouteApiUnavailable = dict(http_status=503, http_message="Service Unavailable")

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

# Conflicting-contentType fixtures: the decoded bytes pin the format when
# the report contentType names a different one.
ZplBytesPdfContentTypePrintResponse = lib.to_json(
    {
        "reports": [
            {
                "name": "Label",
                "content": ZplMagicBase64,
                "contentType": "application/pdf",
                "type": "Label",
                "valid": True,
            }
        ]
    }
)

PdfBytesZplContentTypePrintResponse = lib.to_json(
    {
        "reports": [
            {
                "name": "Label",
                "content": PdfMagicBase64,
                "contentType": "application/zpl",
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
