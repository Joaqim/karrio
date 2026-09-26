"""PostNord carrier shipment tests."""

import base64
import http.client
import json
import unittest
from unittest.mock import patch, ANY

import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models
import karrio.schemas.postnord.shipment_response as postnord_res
import karrio.providers.postnord.units as provider_units

from .fixture import (
    _settings,
    gateway,
    gateway_small_label,
    gateway_zpl_label,
    gateway_with_country_locale,
    gateway_with_language,
)


class TestPostNordShipment(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.ShipmentRequest = models.ShipmentRequest(**ShipmentPayload)
        self.ShipmentCancelRequest = models.ShipmentCancelRequest(
            **ShipmentCancelPayload
        )

    def test_create_shipment_request(self):
        request = gateway.mapper.create_shipment_request(self.ShipmentRequest)
        self.assertEqual(lib.to_dict(request.serialize()), ShipmentRequest)

    def test_create_shipment_request_new_service(self):
        # postnord_varubrev_first_class must route to basicServiceCode "86"
        # (evidence: delivery-options bookingInstructions worked example).
        payload = {**ShipmentPayload, "service": "postnord_varubrev_first_class"}
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        serialized = lib.to_dict(request.serialize())
        self.assertEqual(
            serialized["shipment"][0]["service"]["basicServiceCode"], "86"
        )

    def test_create_shipment_request_pallet_groupage_option(self):
        # postnord_pallet_groupage must route into additionalServiceCode as "65"
        # (evidence: delivery-options DeliveryType narrative).
        payload = {
            **ShipmentPayload,
            "service": "postnord_groupage",
            "options": {"postnord_pallet_groupage": True},
        }
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        serialized = lib.to_dict(request.serialize())
        self.assertEqual(
            serialized["shipment"][0]["service"]["basicServiceCode"], "83"
        )
        self.assertIn(
            "65", serialized["shipment"][0]["service"]["additionalServiceCode"]
        )

    def test_create_shipment(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(self.ShipmentRequest).from_(gateway)
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/edi/labels/pdf?apikey=TEST_API_KEY&locale=en",
            )

    def test_create_shipment_entry_code_request(self):
        # options.entry_code maps to a ZDC freeText on the booking body.
        payload = {**ShipmentPayload, "options": {"entry_code": "1442"}}
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        serialized = lib.to_dict(request.serialize())
        self.assertEqual(
            serialized["shipment"][0]["freeText"],
            [{"usageCode": "ZDC", "text": "1442"}],
        )

    def test_create_shipment_entry_code_absent(self):
        # No option: freeText omitted, no rejection flag; payload unchanged.
        request = gateway.mapper.create_shipment_request(self.ShipmentRequest)
        serialized = lib.to_dict(request.serialize())
        self.assertNotIn("freeText", serialized["shipment"][0])
        self.assertIsNone(request.ctx.get("entry_code_error"))

    def test_create_shipment_entry_code_coerced(self):
        # PlainDictField does not enforce inner types; numeric codes are sent
        # as strings (same coercion rationale as options.language).
        payload = {**ShipmentPayload, "options": {"entry_code": 1442}}
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        serialized = lib.to_dict(request.serialize())
        self.assertEqual(
            serialized["shipment"][0]["freeText"],
            [{"usageCode": "ZDC", "text": "1442"}],
        )

    def test_create_shipment_entry_code_at_limit(self):
        # Exactly 50 characters is the inclusive boundary and is sent.
        payload = {**ShipmentPayload, "options": {"entry_code": "1" * 50}}
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        serialized = lib.to_dict(request.serialize())
        self.assertEqual(
            serialized["shipment"][0]["freeText"],
            [{"usageCode": "ZDC", "text": "1" * 50}],
        )

    def test_create_shipment_entry_code_over_limit(self):
        # 51 characters rejects the booking: no HTTP call, a synthesized
        # compositeFault surfaces as an ENTRY_CODE_LENGTH message.
        payload = {**ShipmentPayload, "options": {"entry_code": "1" * 51}}
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            shipment, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**payload))
                .from_(gateway)
                .parse()
            )
            mock.assert_not_called()
        self.assertIsNone(shipment)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].code, "ENTRY_CODE_LENGTH")
        self.assertIn("exceeds 50 characters", messages[0].message)

    def test_create_shipment_notification_sms_option(self):
        # Unified sms_notification books exactly A3 and no other channel.
        payload = {**ShipmentPayload, "options": {"sms_notification": True}}
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        codes = lib.to_dict(request.serialize())["shipment"][0]["service"][
            "additionalServiceCode"
        ]
        self.assertEqual(codes, ["A3"])

    def test_create_shipment_notification_email_option(self):
        # Unified email_notification books exactly A4.
        payload = {**ShipmentPayload, "options": {"email_notification": True}}
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        codes = lib.to_dict(request.serialize())["shipment"][0]["service"][
            "additionalServiceCode"
        ]
        self.assertEqual(codes, ["A4"])

    def test_create_shipment_notification_multiple_channels(self):
        # Channels combine additively.
        payload = {
            **ShipmentPayload,
            "options": {"sms_notification": True, "email_notification": True},
        }
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        codes = lib.to_dict(request.serialize())["shipment"][0]["service"][
            "additionalServiceCode"
        ]
        self.assertEqual(sorted(codes), ["A3", "A4"])

    def test_create_shipment_notification_carrier_scoped_names(self):
        # Channels without unified equivalents use carrier-scoped names.
        payload = {
            **ShipmentPayload,
            "options": {
                "postnord_notify_by_letter": True,
                "postnord_notify_by_phone": True,
                "postnord_driver_notification": True,
            },
        }
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        codes = lib.to_dict(request.serialize())["shipment"][0]["service"][
            "additionalServiceCode"
        ]
        self.assertEqual(sorted(codes), ["A2", "A9", "B8"])

    def test_create_shipment_notification_explicit_false_opts_out(self):
        # An explicit False must not book the channel.
        payload = {**ShipmentPayload, "options": {"sms_notification": False}}
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        service = lib.to_dict(request.serialize())["shipment"][0]["service"]
        self.assertNotIn("A3", service.get("additionalServiceCode") or [])

    def test_create_shipment_notification_aliases_dedupe(self):
        # Unified and scoped names for the same code collapse to one member.
        payload = {
            **ShipmentPayload,
            "options": {
                "sms_notification": True,
                "postnord_notify_by_sms": True,
            },
        }
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        codes = lib.to_dict(request.serialize())["shipment"][0]["service"][
            "additionalServiceCode"
        ]
        self.assertEqual(codes, ["A3"])

    def test_create_shipment_option_false_not_emitted(self):
        payload = {
            **ShipmentPayload,
            "options": {"postnord_optional_service_point": False},
        }
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        service = lib.to_dict(request.serialize())["shipment"][0]["service"]
        self.assertNotIn("A7", service.get("additionalServiceCode") or [])

    def test_create_shipment_customs_request(self):
        # payload.customs rides the booking EDI as the shipment entry's
        # customsDeclarationCN22 branch: LB commodity weight converts to
        # KGM, title falls back to description, rowNo is 1-based, and
        # totalValue sums the lines with the first line's currency.
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**CustomsShipmentPayload)
        )
        self.assertEqual(lib.to_dict(request.serialize()), CustomsShipmentRequest)

    def test_create_shipment_customs_category_vocabulary(self):
        # Each karrio-canonical content_type resolves to its PostNord CN22
        # category: karrio's vocabulary names the same six categories under
        # different values (MERCHANDISE is PostNord's SALE OF GOODS).
        for content_type, category in [
            ("documents", "DOCUMENT"),
            ("gift", "GIFT"),
            ("sample", "COMMERCIAL SAMPLE"),
            ("merchandise", "SALE OF GOODS"),
            ("return_merchandise", "RETURNED GOODS"),
            ("other", "OTHER"),
        ]:
            with self.subTest(content_type=content_type):
                payload = {
                    **CustomsShipmentPayload,
                    "customs": {
                        **CustomsShipmentPayload["customs"],
                        "content_type": content_type,
                    },
                }
                request = gateway.mapper.create_shipment_request(
                    models.ShipmentRequest(**payload)
                )
                declaration = lib.to_dict(request.serialize())["shipment"][0][
                    "customsDeclarationCN22"
                ]
                self.assertEqual(
                    declaration["categoryOfItem"], {"categoryType": [category]}
                )

    def test_create_shipment_customs_category_postnord_native_form(self):
        # A caller already speaking PostNord's vocabulary canonicalizes to
        # the uppercase form; resolution ignores case and extra whitespace.
        for content_type in ["sale of goods", "  SALE   OF GOODS "]:
            with self.subTest(content_type=content_type):
                payload = {
                    **CustomsShipmentPayload,
                    "customs": {
                        **CustomsShipmentPayload["customs"],
                        "content_type": content_type,
                    },
                }
                request = gateway.mapper.create_shipment_request(
                    models.ShipmentRequest(**payload)
                )
                declaration = lib.to_dict(request.serialize())["shipment"][0][
                    "customsDeclarationCN22"
                ]
                self.assertEqual(
                    declaration["categoryOfItem"],
                    {"categoryType": ["SALE OF GOODS"]},
                )

    def test_create_shipment_customs_category_unknown_passthrough(self):
        # categoryType is a free string validated server-side, so a value
        # outside both vocabularies is sent verbatim, not rejected or coerced.
        payload = {
            **CustomsShipmentPayload,
            "customs": {
                **CustomsShipmentPayload["customs"],
                "content_type": "intercompany transfer",
            },
        }
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        declaration = lib.to_dict(request.serialize())["shipment"][0][
            "customsDeclarationCN22"
        ]
        self.assertEqual(
            declaration["categoryOfItem"],
            {"categoryType": ["intercompany transfer"]},
        )

    def test_create_shipment_customs_category_absent(self):
        # Without a content_type the request carries no categoryOfItem
        # element at all.
        payload = {
            **CustomsShipmentPayload,
            "customs": {
                key: value
                for key, value in CustomsShipmentPayload["customs"].items()
                if key != "content_type"
            },
        }
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        declaration = lib.to_dict(request.serialize())["shipment"][0][
            "customsDeclarationCN22"
        ]
        self.assertNotIn("categoryOfItem", declaration)

    def test_create_shipment_customs_registration_numbers(self):
        # customs.options registration numbers pass through onto the CN22
        # branch: PostNord rejects a declaration carrying none of them
        # (SACUS-BR-24062502 "should have either EORI, VOEC, IOSS").
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**CustomsRegistrationShipmentPayload)
        )
        self.assertEqual(
            lib.to_dict(request.serialize()), CustomsRegistrationShipmentRequest
        )

    def test_create_shipment_customs_registration_numbers_partial(self):
        # Any subset maps; the absent numbers are not cross-defaulted.
        payload = {
            **CustomsShipmentPayload,
            "customs": {
                **CustomsShipmentPayload["customs"],
                "options": {"voec_number": "1234567"},
            },
        }
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        declaration = lib.to_dict(request.serialize())["shipment"][0][
            "customsDeclarationCN22"
        ]
        self.assertEqual(declaration["voec"], "1234567")
        self.assertNotIn("EORIorPersonalIdNumber", declaration)
        self.assertNotIn("ioss", declaration)

    def test_create_shipment_customs_registration_numbers_empty_reject(self):
        # Option-state truthiness: empty-string or None options count as
        # absent, and a CN22 without EORI, VOEC, or IOSS is rejected before
        # submission, as PostNord rejects it (SACUS-BR-24062502).
        for label, options in [
            ("empty", {"eori_number": "", "voec_number": None}),
            ("absent", {}),
        ]:
            with self.subTest(options=label):
                with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
                    shipment, messages = (
                        karrio.Shipment.create(
                            models.ShipmentRequest(
                                **{
                                    **CustomsShipmentPayload,
                                    "customs": {
                                        **CustomsShipmentPayload["customs"],
                                        "options": options,
                                    },
                                }
                            )
                        )
                        .from_(gateway)
                        .parse()
                    )
                    mock.assert_not_called()
                self.assertIsNone(shipment)
                self.assertEqual(len(messages), 1)
                self.assertEqual(messages[0].code, "SHIPPING_SDK_FIELD_ERROR")
                self.assertEqual(
                    messages[0].details,
                    {
                        "customs.options": (
                            "a CN22 declaration requires at least one of "
                            "eori_number, voec_number, or ioss_number"
                        )
                    },
                )

    def test_create_shipment_customs_registration_numbers_any_one_suffices(self):
        # Any single registration number satisfies the CN22 rule and the
        # request carries only that number.
        for key, element in [
            ("eori_number", "EORIorPersonalIdNumber"),
            ("voec_number", "voec"),
            ("ioss_number", "ioss"),
        ]:
            with self.subTest(option=key):
                payload = {
                    **CustomsShipmentPayload,
                    "customs": {
                        **CustomsShipmentPayload["customs"],
                        "options": {key: "REG123"},
                    },
                }
                request = gateway.mapper.create_shipment_request(
                    models.ShipmentRequest(**payload)
                )
                declaration = lib.to_dict(request.serialize())["shipment"][0][
                    "customsDeclarationCN22"
                ]
                expected = {
                    k: v
                    for k, v in CustomsShipmentRequest["shipment"][0][
                        "customsDeclarationCN22"
                    ].items()
                    if k != "EORIorPersonalIdNumber"
                }
                self.assertEqual(declaration, {**expected, element: "REG123"})

    def test_create_shipment_customs_registration_numbers_misplaced_reject(self):
        # Registration keys under shipment-level options are dropped by the
        # typed-options helper without any signal; the booking rejects the
        # placement locally instead of letting PostNord reject the CN22
        # (SACUS-BR-24062502 "should have either EORI, VOEC, IOSS").
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            shipment, messages = (
                karrio.Shipment.create(
                    models.ShipmentRequest(
                        **{
                            **CustomsShipmentPayload,
                            "options": {
                                "eori_number": "SE556000123401",
                                "voec_number": "1234567",
                            },
                        }
                    )
                )
                .from_(gateway)
                .parse()
            )
            mock.assert_not_called()
        self.assertIsNone(shipment)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].code, "SHIPPING_SDK_FIELD_ERROR")
        self.assertEqual(
            messages[0].details,
            {
                "options.eori_number": (
                    "customs registration number; send it under customs.options"
                ),
                "options.voec_number": (
                    "customs registration number; send it under customs.options"
                ),
            },
        )

    def test_create_shipment_customs_registration_numbers_misplaced_empty_pass(self):
        # The guard is truthy-only: empty values send nothing under either
        # placement, so the booking is identical to one without the keys.
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(
                **{
                    **CustomsShipmentPayload,
                    "options": {
                        **CustomsShipmentPayload["options"],
                        "eori_number": "",
                        "ioss_number": None,
                    },
                }
            )
        )
        self.assertEqual(lib.to_dict(request.serialize()), CustomsShipmentRequest)

    def test_create_shipment_without_customs_ignores_registration_options(self):
        # The guard is scoped to customs bookings: without a customs branch
        # the registration keys are inert and the booking is unchanged.
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(
                **{
                    **ShipmentPayload,
                    "options": {
                        **ShipmentPayload["options"],
                        "eori_number": "SE556000123401",
                    },
                }
            )
        )
        self.assertEqual(lib.to_dict(request.serialize()), ShipmentRequest)

    def test_create_shipment_customs_lines_at_limit(self):
        # 13 lines is the inclusive boundary and is sent in full.
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**_customs_payload(13))
        )
        declaration = lib.to_dict(request.serialize())["shipment"][0][
            "customsDeclarationCN22"
        ]
        self.assertEqual(len(declaration["detailedDescription"]), 13)
        self.assertEqual(declaration["detailedDescription"][-1]["rowNo"], 13)

    def test_create_shipment_customs_lines_over_limit(self):
        # 14 lines reject the booking before submission: a field error
        # naming the 13-line limit, and no HTTP call.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            shipment, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**_customs_payload(14)))
                .from_(gateway)
                .parse()
            )
            mock.assert_not_called()
        self.assertIsNone(shipment)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].code, "SHIPPING_SDK_FIELD_ERROR")
        self.assertEqual(
            messages[0].details["customs.commodities"],
            "customs.commodities exceeds the 13-line customs declaration limit",
        )

    def test_create_shipment_customs_total_value_rounding(self):
        # Line values sum as money: 0.1 + 0.2 is 0.3, not the float
        # artifact 0.30000000000000004, and the currency is the first
        # line's (SEK), not the second line's (EUR).
        payload = {
            **ShipmentPayload,
            "recipient": NorwayRecipient,
            "service": "postnord_tracked_letter",
            "customs": {
                "content_type": "merchandise",
                "options": {"eori_number": "SE556000123401"},
                "commodities": [
                    {
                        "title": "Sticker sheet",
                        "quantity": 1,
                        "value_amount": 0.1,
                        "value_currency": "SEK",
                    },
                    {
                        "title": "Postcard",
                        "quantity": 1,
                        "value_amount": 0.2,
                        "value_currency": "EUR",
                    },
                ],
            },
        }
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        declaration = lib.to_dict(request.serialize())["shipment"][0][
            "customsDeclarationCN22"
        ]
        self.assertEqual(
            declaration["totalValue"], {"amount": 0.3, "currency": "SEK"}
        )

    def test_create_shipment_customs_line_totals_over_quantity(self):
        # Unified commodity value and weight are per unit; CN22 lines and
        # totals are per line: 3 x (10 SEK, 0.2 kg) is 30 SEK and 0.6 kg.
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**QuantityThreeCN22Payload)
        )
        declaration = lib.to_dict(request.serialize())["shipment"][0][
            "customsDeclarationCN22"
        ]
        self.assertEqual(
            declaration["detailedDescription"],
            [
                {
                    "content": "Enamel pin",
                    "quantity": {"value": 3},
                    "grossWeight": {"value": 0.6, "unit": "KGM"},
                    "value": {"amount": 30.0, "currency": "SEK"},
                    "hsTariffNumber": "7117190000",
                    "countryCode": "SE",
                    "rowNo": 1,
                },
                {
                    "content": "Postcard",
                    "quantity": {"value": 1},
                    "grossWeight": {"value": 0.1, "unit": "KGM"},
                    "value": {"amount": 5.0, "currency": "SEK"},
                    "hsTariffNumber": "4909000000",
                    "countryCode": "SE",
                    "rowNo": 2,
                },
            ],
        )
        self.assertEqual(
            declaration["totalValue"], {"amount": 35.0, "currency": "SEK"}
        )

    def test_create_shipment_customs_gross_weight_from_parcels(self):
        # Total gross weight includes packaging: the sum of the parcel
        # weights (1.5 kg + 500 g), not the 0.7 kg of commodity lines.
        payload = {
            **QuantityThreeCN22Payload,
            "parcels": [
                *ShipmentPayload["parcels"],
                {"weight": 500, "weight_unit": "G"},
            ],
        }
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        declaration = lib.to_dict(request.serialize())["shipment"][0][
            "customsDeclarationCN22"
        ]
        self.assertEqual(
            declaration["totalGrossWeight"], {"value": 2.0, "unit": "KGM"}
        )

    def test_create_shipment_customs_gross_weight_falls_back_to_lines(self):
        # Without any parcel weight the commodity line weights are the only
        # derivable gross weight.
        payload = {
            **QuantityThreeCN22Payload,
            "parcels": [{"length": 30.0, "width": 20.0, "height": 10.0, "dimension_unit": "CM"}],
        }
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        declaration = lib.to_dict(request.serialize())["shipment"][0][
            "customsDeclarationCN22"
        ]
        self.assertEqual(
            declaration["totalGrossWeight"], {"value": 0.7, "unit": "KGM"}
        )

    def test_create_shipment_customs_underivable_line_fields_omitted(self):
        # A commodity without weight_unit has no KGM value and a line
        # without value_amount carries no value: the elements are omitted
        # entirely rather than emitted as unitless/amountless structs.
        payload = {
            **ShipmentPayload,
            "recipient": NorwayRecipient,
            "service": "postnord_tracked_letter",
            "customs": {
                "content_type": "merchandise",
                "options": {"eori_number": "SE556000123401"},
                "commodities": [
                    {
                        "title": "Undeclared weight item",
                        "quantity": 1,
                        "weight": 0.4,
                        "value_amount": 10.0,
                        "value_currency": "SEK",
                    },
                    {
                        "title": "Currency-only item",
                        "quantity": 1,
                        "weight": 0.2,
                        "weight_unit": "KG",
                        "value_currency": "SEK",
                    },
                ],
            },
        }
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        rows = lib.to_dict(request.serialize())["shipment"][0][
            "customsDeclarationCN22"
        ]["detailedDescription"]
        self.assertEqual(rows[0]["content"], "Undeclared weight item")
        self.assertNotIn("grossWeight", rows[0])
        self.assertEqual(rows[1]["grossWeight"], {"value": 0.2, "unit": "KGM"})
        self.assertNotIn("value", rows[1])

    def test_parse_shipment_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ShipmentResponse
            parsed_response = (
                karrio.Shipment.create(self.ShipmentRequest).from_(gateway).parse()
            )
            self.assertListEqual(
                lib.to_dict(parsed_response), ParsedShipmentResponse
            )

    def test_create_cancel_shipment_request(self):
        request = gateway.mapper.create_cancel_shipment_request(
            self.ShipmentCancelRequest
        )
        self.assertEqual(lib.to_dict(request.serialize()), ShipmentCancelRequest)

    def test_cancel_shipment(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.cancel(self.ShipmentCancelRequest).from_(gateway)
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/edi?apikey=TEST_API_KEY",
            )

    def test_parse_cancel_shipment_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ShipmentCancelResponse
            parsed_response = (
                karrio.Shipment.cancel(self.ShipmentCancelRequest).from_(gateway).parse()
            )
            self.assertListEqual(
                lib.to_dict(parsed_response), ParsedShipmentCancelResponse
            )

    def test_parse_error_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ErrorResponse
            parsed_response = (
                karrio.Shipment.create(self.ShipmentRequest).from_(gateway).parse()
            )
            self.assertListEqual(lib.to_dict(parsed_response), ParsedErrorResponse)

    def test_parse_partial_failure_response(self):
        # A mixed 200/201 booking: one parcel is allocated ids + label, another
        # fails inline. The successful shipment details must be preserved and the
        # inline fault surfaced as a message alongside them.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = PartialFailureResponse
            parsed_response = (
                karrio.Shipment.create(self.ShipmentRequest).from_(gateway).parse()
            )
            self.assertListEqual(
                lib.to_dict(parsed_response), ParsedPartialFailureResponse
            )

    def test_parse_authorization_error(self):
        # PostNord's API-gateway 403 envelope must surface a clear authorization
        # error (the key is not authorized for this product), not a silent
        # generic failure.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = AuthErrorResponse
            parsed_response = (
                karrio.Shipment.create(self.ShipmentRequest).from_(gateway).parse()
            )
            self.assertListEqual(
                lib.to_dict(parsed_response), ParsedAuthErrorResponse
            )

    def test_create_shipment_locale_from_request(self):
        # options.language on the request wins over connection config.
        payload = {**ShipmentPayload, "options": {"language": "sv"}}
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(models.ShipmentRequest(**payload)).from_(gateway)
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/edi/labels/pdf?apikey=TEST_API_KEY&locale=sv",
            )

    def test_create_shipment_locale_from_config(self):
        # Connection-config language applies when the request omits it.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(self.ShipmentRequest).from_(gateway_with_language)
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/edi/labels/pdf?apikey=TEST_API_KEY&locale=da",
            )

    def test_create_shipment_locale_from_recipient_country(self):
        # locale_by_recipient maps the recipient's country to a Nordic locale.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(self.ShipmentRequest).from_(
                gateway_with_country_locale
            )
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/edi/labels/pdf?apikey=TEST_API_KEY&locale=sv",
            )

    def test_create_shipment_locale_recipient_country_unmapped(self):
        # Countries outside the mapping fall back to en even with the flag on.
        payload = {
            **ShipmentPayload,
            "recipient": {**ShipmentPayload["recipient"], "country_code": "DE"},
        }
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(models.ShipmentRequest(**payload)).from_(
                gateway_with_country_locale
            )
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/edi/labels/pdf?apikey=TEST_API_KEY&locale=en",
            )

    def test_create_shipment_locale_explicit_wins_over_country(self):
        # An explicit options.language beats the recipient-country tier.
        payload = {**ShipmentPayload, "options": {"language": "da"}}
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(models.ShipmentRequest(**payload)).from_(
                gateway_with_country_locale
            )
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/edi/labels/pdf?apikey=TEST_API_KEY&locale=da",
            )

    def test_create_shipment_locale_config_wins_over_country(self):
        # config.language outranks the country tier: a Norwegian recipient on
        # a connection configured sv still books sv.
        payload = {
            **ShipmentPayload,
            "recipient": {**ShipmentPayload["recipient"], "country_code": "NO"},
        }
        gateway_sv_country = karrio.gateway["postnord"].create(
            dict(
                _settings,
                config=dict(language="sv", locale_by_recipient=True),
            )
        )
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(models.ShipmentRequest(**payload)).from_(
                gateway_sv_country
            )
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/edi/labels/pdf?apikey=TEST_API_KEY&locale=sv",
            )

    def test_create_shipment_locale_country_flag_off(self):
        # Without locale_by_recipient the recipient country is ignored.
        payload = {
            **ShipmentPayload,
            "recipient": {**ShipmentPayload["recipient"], "country_code": "DK"},
        }
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(models.ShipmentRequest(**payload)).from_(gateway)
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/edi/labels/pdf?apikey=TEST_API_KEY&locale=en",
            )

    def test_parse_shipment_response_zpl(self):
        # encoding "none" + raw ZPL text -> base64-of-ZPL in docs.label and
        # label_type from the response's labelFormat.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ShipmentZPLResponse
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**{**ShipmentPayload, "label_type": "ZPL"})
                )
                .from_(gateway)
                .parse()
            )
            details, _ = parsed_response
            self.assertEqual(details.label_type, "ZPL")
            self.assertEqual(
                details.docs.label, base64.b64encode(RawZPL.encode("utf-8")).decode("utf-8")
            )

    def test_parse_shipment_response_zpl_without_label_format(self):
        # A ZPL printout without labelFormat falls back to the requested type
        # threaded on the ctx rather than assuming PDF.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ShipmentZPLNoFormatResponse
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**{**ShipmentPayload, "label_type": "ZPL"})
                )
                .from_(gateway)
                .parse()
            )
            details, _ = parsed_response
            self.assertEqual(details.label_type, "ZPL")
            self.assertEqual(
                details.docs.label, base64.b64encode(RawZPL.encode("utf-8")).decode("utf-8")
            )

    def test_parse_shipment_response_zpl_bundle(self):
        # Multiple raw-ZPL printouts bundle into base64 of the newline-joined
        # ZPL texts (bundle_zpls semantics); verified by decode round-trip.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ShipmentZPLMultiResponse
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**{**ShipmentPayload, "label_type": "ZPL"})
                )
                .from_(gateway)
                .parse()
            )
            details, _ = parsed_response
            self.assertEqual(details.label_type, "ZPL")
            decoded = base64.b64decode(details.docs.label).decode("utf-8")
            # bundle_zpls appends NEW_LINE after every label, incl. the last.
            self.assertEqual(decoded, f"{RawZPL}\n{RawZPL2}\n")

    def test_parse_shipment_response_absent_encoding_defaults_base64(self):
        # The swagger documents encoding "base64" only, so a printout without
        # the element passes its data through unchanged rather than
        # re-encoding it as raw text.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ShipmentNoEncodingResponse
            parsed_response = (
                karrio.Shipment.create(self.ShipmentRequest).from_(gateway).parse()
            )
        details, _ = parsed_response
        self.assertEqual(details.docs.label, "JVBERi0xLjQK")


class TestPostNordRecipientLocale(unittest.TestCase):
    def test_recipient_locale_from_recipient_country(self):
        self.assertEqual(
            gateway_with_country_locale.settings.recipient_locale(
                {"country_code": "DK"}
            ),
            "da",
        )

    def test_recipient_locale_flag_off(self):
        self.assertIsNone(gateway.settings.recipient_locale({"country_code": "DK"}))

    def test_recipient_locale_config_language_wins(self):
        gateway_sv_country = karrio.gateway["postnord"].create(
            dict(_settings, config=dict(language="sv", locale_by_recipient=True))
        )
        self.assertIsNone(
            gateway_sv_country.settings.recipient_locale({"country_code": "DK"})
        )

    def test_recipient_locale_unmapped_country(self):
        self.assertIsNone(
            gateway_with_country_locale.settings.recipient_locale(
                {"country_code": "DE"}
            )
        )

    def test_recipient_locale_without_recipient(self):
        self.assertIsNone(gateway_with_country_locale.settings.recipient_locale())


class TestPostNordLabel(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_create_shipment_zpl_routes_zpl_endpoint(self):
        # Request-level label_type selects the ZPL endpoint (exact URL).
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            payload = {**ShipmentPayload, "label_type": "ZPL"}
            karrio.Shipment.create(models.ShipmentRequest(**payload)).from_(gateway)
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/edi/labels/zpl?apikey=TEST_API_KEY&locale=en",
            )

    def test_create_shipment_config_label_type_routes_zpl_endpoint(self):
        # Connection-config label_type=ZPL with payload label_type unset resolves
        # the format from the connection default and routes to the ZPL endpoint
        # via the threaded ctx (exact URL).
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(
                models.ShipmentRequest(**ShipmentPayload)
            ).from_(gateway_zpl_label)
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/edi/labels/zpl?apikey=TEST_API_KEY&locale=en",
            )

    def test_create_shipment_defaults_pdf_endpoint(self):
        # No label_type anywhere: PDF endpoint (exact URL).
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(
                models.ShipmentRequest(**ShipmentPayload)
            ).from_(gateway)
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/edi/labels/pdf?apikey=TEST_API_KEY&locale=en",
            )

    def test_create_shipment_label_size_query(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(
                models.ShipmentRequest(**ShipmentPayload)
            ).from_(gateway_small_label)
            self.assertIn("labelType=small", mock.call_args[1]["url"])

    def test_create_shipment_default_label_size_absent(self):
        # Unset label_size sends no labelType override (PostNord defaults to
        # standard); _url drops the None value.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(
                models.ShipmentRequest(**ShipmentPayload)
            ).from_(gateway)
            self.assertNotIn("labelType", mock.call_args[1]["url"])


class TestPostNordCustomsDocument(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_parse_shipment_response_printout_composition(self):
        # Non-zero printoutComposition kinds are carried into meta as the
        # composed document kinds. A tracked letter keeps the by-id fetch
        # gated off, so exactly one HTTP call is made.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = CustomsBookingResponse
            parsed_response = (
                karrio.Shipment.create(models.ShipmentRequest(**CustomsShipmentPayload))
                .from_(gateway)
                .parse()
            )
            mock.assert_called_once()
        details, messages = parsed_response
        self.assertEqual(messages, [])
        self.assertEqual(details.meta["printout_composition"], ["cn22", "label"])

    def test_create_shipment_customs_document_fetch(self):
        # Export letter + customs: after the booking, a second POST fetches
        # the standalone customs document by the booking response's printId
        # (live finding 2026-09-21: /v3/labels/ids resolves a real booking's
        # printId, not its item id) with definePrintout=onlyCustomsDeclarations,
        # and the printouts attach as extra_documents categorized by what
        # PostNord composed.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = [CustomsBookingResponse, CustomsPrintoutsResponse]
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**ExportLetterCustomsPayload)
                )
                .from_(gateway)
                .parse()
            )
            self.assertEqual(mock.call_count, 2)
            booking_call, customs_call = mock.call_args_list
            self.assertEqual(
                booking_call[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/edi/labels/pdf"
                "?apikey=TEST_API_KEY&locale=en",
            )
            self.assertEqual(
                customs_call[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/labels/ids/pdf"
                "?apikey=TEST_API_KEY&definePrintout=onlyCustomsDeclarations",
            )
            self.assertEqual(customs_call[1]["method"], "POST")
            self.assertEqual(
                json.loads(customs_call[1]["data"]),
                [{"id": "P1"}],
            )
        details, messages = parsed_response
        self.assertEqual(messages, [])
        self.assertEqual(
            lib.to_dict(details.docs),
            {
                "label": "JVBERi0xLjQK",
                "extra_documents": [
                    {
                        "category": "cn22",
                        "format": "PDF",
                        "base64": CustomsPDFData,
                    }
                ],
            },
        )
        # The by-id itemIds member's reference is the references object
        # (swagger $ref), not a string: pin its typed deserialization.
        printout_entry = lib.to_object(
            postnord_res.LabelPrintoutType, json.loads(CustomsPrintoutsResponse)[0]
        )
        reference = printout_entry.itemIds[0].reference
        self.assertEqual(reference.item, [])
        self.assertEqual(
            [(r.referenceNo, r.referenceType) for r in reference.shipment],
            [("BOOK-UX1", "IL")],
        )

    def test_create_shipment_customs_document_fetch_falls_back_to_item_id(self):
        # The printId accompanying the first assigned item id keys the by-id
        # fetch; when PostNord allocates no printId the item id is the only
        # key available.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = [
                CustomsBookingNoPrintIdResponse,
                CustomsPrintoutsResponse,
            ]
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**ExportLetterCustomsPayload)
                )
                .from_(gateway)
                .parse()
            )
            self.assertEqual(mock.call_count, 2)
            self.assertEqual(
                json.loads(mock.call_args_list[1][1]["data"]),
                [{"id": "00373500454541020957"}],
            )
        details, messages = parsed_response
        self.assertEqual(messages, [])
        self.assertEqual(
            [document.category for document in details.docs.extra_documents],
            ["cn22"],
        )

    def test_create_shipment_customs_document_empty_ok_response_fails_open(self):
        # Live capture (2026-09-21): before a declaration exists, the
        # printId-keyed onlyCustomsDeclarations fetch answers OK members with
        # no printout data and an all-zero printoutComposition — the fetch
        # succeeded but nothing attaches. The booking stands, no documents
        # attach, and exactly one message reports the empty result instead
        # of silence.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = [
                CustomsBookingResponse,
                CustomsPrintoutsEmptyResponse,
            ]
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**ExportLetterCustomsPayload)
                )
                .from_(gateway)
                .parse()
            )
            self.assertEqual(mock.call_count, 2)
        details, messages = parsed_response
        self.assertIsNotNone(details)
        self.assertEqual(details.tracking_number, "00373500454541020957")
        self.assertEqual(details.docs.label, "JVBERi0xLjQK")
        self.assertEqual(details.docs.extra_documents, [])
        self.assertEqual(len(messages), 1)
        self.assertIsNone(messages[0].code)
        self.assertEqual(
            messages[0].message,
            "no customs documents in by-id response for item id: "
            "00373500454541020957",
        )

    def test_create_shipment_customs_document_zpl_fetch(self):
        # ZPL bookings fetch through /labels/ids/zpl; the printout carries
        # raw UTF-8 ZPL (encoding "none") without labelFormat, so the
        # document format falls back to the requested label type and the
        # data re-encodes to base64 like the booking label.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = [CustomsBookingZPLResponse, CustomsPrintoutsZPLResponse]
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(
                        **{**ExportLetterCustomsPayload, "label_type": "ZPL"}
                    )
                )
                .from_(gateway)
                .parse()
            )
            self.assertEqual(mock.call_count, 2)
            self.assertEqual(
                mock.call_args_list[1][1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/labels/ids/zpl"
                "?apikey=TEST_API_KEY&definePrintout=onlyCustomsDeclarations",
            )
        details, _ = parsed_response
        self.assertEqual(details.label_type, "ZPL")
        self.assertEqual(
            lib.to_dict(details.docs.extra_documents),
            [
                {
                    "category": "cn22",
                    "format": "ZPL",
                    "base64": base64.b64encode(CustomsRawZPL.encode("utf-8")).decode(
                        "utf-8"
                    ),
                }
            ],
        )

    def test_create_shipment_customs_document_multi_kind_category_sorted(self):
        # The joined category is deterministic regardless of the composition
        # key order PostNord serializes: sorted, like meta.printout_composition.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = [
                CustomsBookingResponse,
                CustomsPrintoutsMultiKindResponse,
            ]
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**ExportLetterCustomsPayload)
                )
                .from_(gateway)
                .parse()
            )
            self.assertEqual(mock.call_count, 2)
        details, messages = parsed_response
        self.assertEqual(messages, [])
        self.assertEqual(
            details.docs.extra_documents[0].category, "cn22,customsInvoice"
        )

    def test_create_shipment_customs_document_category_fallback(self):
        # A by-id printout without printoutComposition falls back to the
        # standardized customs-declaration category name (snake_case, the
        # same output family as the composed kind keys).
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = [
                CustomsBookingResponse,
                CustomsPrintoutsNoCompositionResponse,
            ]
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**ExportLetterCustomsPayload)
                )
                .from_(gateway)
                .parse()
            )
            self.assertEqual(mock.call_count, 2)
        details, messages = parsed_response
        self.assertEqual(messages, [])
        self.assertEqual(
            details.docs.extra_documents[0].category, "customs_declaration"
        )

    def test_create_shipment_customs_document_error_body_fails_open(self):
        # An error body from the by-id fetch leaves the booking successful;
        # the fault surfaces as a message alongside the shipment details.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = [CustomsBookingResponse, CustomsRetrievalErrorResponse]
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**ExportLetterCustomsPayload)
                )
                .from_(gateway)
                .parse()
            )
            self.assertEqual(mock.call_count, 2)
        details, messages = parsed_response
        self.assertIsNotNone(details)
        self.assertEqual(details.docs.label, "JVBERi0xLjQK")
        self.assertEqual(details.docs.extra_documents, [])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].code, "EDI_NOT_FOUND")
        self.assertIn("No EDI found", messages[0].message)

    def test_create_shipment_customs_document_per_id_failure_fails_open(self):
        # Live-captured by-id shape: the body parses as a labelPrintout
        # array, so without per-id inspection the failure would vanish (no
        # printout data to attach as a document, no error body reaching the
        # messages). The FAIL member's errorResponse surfaces as exactly
        # one message — attributed to the failed item id like the
        # synthesized path — while the booking stands.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = [
                CustomsBookingResponse,
                CustomsPrintoutsIdNotFoundResponse,
            ]
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**ExportLetterCustomsPayload)
                )
                .from_(gateway)
                .parse()
            )
            self.assertEqual(mock.call_count, 2)
        details, messages = parsed_response
        self.assertIsNotNone(details)
        self.assertEqual(details.tracking_number, "00373500454541020957")
        self.assertEqual(details.docs.label, "JVBERi0xLjQK")
        self.assertEqual(details.docs.extra_documents, [])
        self.assertEqual(len(messages), 1)
        self.assertIsNone(messages[0].code)
        self.assertEqual(
            messages[0].message,
            "customs document retrieval failed for item id "
            "00373500454541020957: id not found",
        )

    def test_create_shipment_customs_document_partial_failure_fails_open(self):
        # A by-id array mixing a data-bearing printout for one id and a FAIL
        # member for another attaches the document and surfaces the failure
        # message at once: only data-bearing printouts become documents.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = [
                CustomsBookingResponse,
                CustomsPrintoutsPartialFailureResponse,
            ]
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**ExportLetterCustomsPayload)
                )
                .from_(gateway)
                .parse()
            )
            self.assertEqual(mock.call_count, 2)
        details, messages = parsed_response
        self.assertIsNotNone(details)
        self.assertEqual(details.tracking_number, "00373500454541020957")
        self.assertEqual(
            lib.to_dict(details.docs.extra_documents),
            [
                {
                    "category": "cn22",
                    "format": "PDF",
                    "base64": CustomsPDFData,
                }
            ],
        )
        self.assertEqual(len(messages), 1)
        self.assertIsNone(messages[0].code)
        self.assertEqual(
            messages[0].message,
            "customs document retrieval failed for item id "
            "00373500454541020957: id not found",
        )

    def test_create_shipment_customs_document_transport_failure_fails_open(self):
        # A transport-level failure of the by-id fetch is also fail-open: no
        # exception escapes, the booking stands, and a synthesized message
        # reports the retrieval failure.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = [
                CustomsBookingResponse,
                ConnectionError("connection refused"),
            ]
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**ExportLetterCustomsPayload)
                )
                .from_(gateway)
                .parse()
            )
            self.assertEqual(mock.call_count, 2)
        details, messages = parsed_response
        self.assertIsNotNone(details)
        self.assertEqual(details.tracking_number, "00373500454541020957")
        self.assertEqual(details.docs.extra_documents, [])
        self.assertEqual(len(messages), 1)
        self.assertIsNone(messages[0].code)
        self.assertIn("customs document retrieval failed", messages[0].message)
        self.assertIn("connection refused", messages[0].message)

    def test_create_shipment_customs_document_protocol_failure_fails_open(self):
        # A protocol-level transport failure (an http.client.HTTPException
        # such as IncompleteRead, re-raised by lib.request since it is not
        # an OSError) is also fail-open: the booking stands and the failure
        # surfaces as a message.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = [
                CustomsBookingResponse,
                http.client.IncompleteRead(partial=b"<trunc"),
            ]
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**ExportLetterCustomsPayload)
                )
                .from_(gateway)
                .parse()
            )
            self.assertEqual(mock.call_count, 2)
        details, messages = parsed_response
        self.assertIsNotNone(details)
        self.assertEqual(details.docs.label, "JVBERi0xLjQK")
        self.assertEqual(details.docs.extra_documents, [])
        self.assertEqual(len(messages), 1)
        self.assertIsNone(messages[0].code)
        self.assertIn("customs document retrieval failed", messages[0].message)
        self.assertIn("IncompleteRead(6 bytes read)", messages[0].message)

    def test_create_shipment_customs_document_unreadable_body_fails_open(self):
        # A non-JSON body from the by-id fetch (e.g. an intermediary's HTML
        # error page) is also fail-open: the booking stands and a synthesized
        # message reports the unreadable body.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = [CustomsBookingResponse, UnreadableBodyResponse]
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**ExportLetterCustomsPayload)
                )
                .from_(gateway)
                .parse()
            )
            self.assertEqual(mock.call_count, 2)
        details, messages = parsed_response
        self.assertIsNotNone(details)
        self.assertEqual(details.docs.label, "JVBERi0xLjQK")
        self.assertEqual(details.docs.extra_documents, [])
        self.assertEqual(len(messages), 1)
        self.assertIsNone(messages[0].code)
        self.assertIn("unreadable body", messages[0].message)
        self.assertIn("<html>502 Bad Gateway</html>", messages[0].message)

    def test_create_shipment_customs_document_no_item_id_skips_fetch(self):
        # A failed booking that allocated no item ids has no target for the
        # by-id fetch: exactly one HTTP call, and the booking fault surfaces.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = CustomsBookingNoIdsResponse
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**ExportLetterCustomsPayload)
                )
                .from_(gateway)
                .parse()
            )
            mock.assert_called_once()
        details, messages = parsed_response
        self.assertIsNone(details)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].code, "CUSTOMS_VALIDATION")
        self.assertIn("totalValue is mandatory", messages[0].message)

    def test_create_shipment_export_letter_without_customs_skips_fetch(self):
        # The fetch is gated on customs data being present: an export letter
        # without customs books exactly as before (one call, no documents).
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = CustomsBookingResponse
            payload = {**ShipmentPayload, "service": "postnord_export_letter"}
            parsed_response = (
                karrio.Shipment.create(models.ShipmentRequest(**payload))
                .from_(gateway)
                .parse()
            )
            mock.assert_called_once()
        details, messages = parsed_response
        self.assertEqual(messages, [])
        self.assertEqual(details.docs.extra_documents, [])


    def test_create_shipment_customs_invoice_document_fetch(self):
        # Parcel product + customs: the booking composes a customs invoice,
        # and the same printId-keyed onlyCustomsDeclarations fetch as for
        # export letters attaches it categorized customsInvoice.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = [
                CustomsInvoiceBookingResponse,
                CustomsInvoicePrintoutsResponse,
            ]
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**CustomsInvoiceShipmentPayload)
                )
                .from_(gateway)
                .parse()
            )
            self.assertEqual(mock.call_count, 2)
            customs_call = mock.call_args_list[1]
            self.assertEqual(
                customs_call[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/labels/ids/pdf"
                "?apikey=TEST_API_KEY&definePrintout=onlyCustomsDeclarations",
            )
            self.assertEqual(json.loads(customs_call[1]["data"]), [{"id": "P1"}])
        details, messages = parsed_response
        self.assertEqual(messages, [])
        self.assertEqual(
            details.meta["printout_composition"], ["customsInvoice", "label"]
        )
        self.assertEqual(
            lib.to_dict(details.docs.extra_documents),
            [
                {
                    "category": "customsInvoice",
                    "format": "PDF",
                    "base64": CustomsPDFData,
                }
            ],
        )

    def test_create_shipment_customs_invoice_document_zpl_fetch(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = [
                CustomsInvoiceBookingZPLResponse,
                CustomsInvoicePrintoutsZPLResponse,
            ]
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(
                        **{**CustomsInvoiceShipmentPayload, "label_type": "ZPL"}
                    )
                )
                .from_(gateway)
                .parse()
            )
            self.assertEqual(mock.call_count, 2)
            self.assertEqual(
                mock.call_args_list[1][1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/labels/ids/zpl"
                "?apikey=TEST_API_KEY&definePrintout=onlyCustomsDeclarations",
            )
        details, messages = parsed_response
        self.assertEqual(messages, [])
        self.assertEqual(
            lib.to_dict(details.docs.extra_documents),
            [
                {
                    "category": "customsInvoice",
                    "format": "ZPL",
                    "base64": base64.b64encode(
                        CustomsRawZPL.encode("utf-8")
                    ).decode("utf-8"),
                }
            ],
        )

    def test_create_shipment_customs_invoice_document_error_fails_open(self):
        # A failing by-id call on a parcel booking leaves the shipment
        # successful with its label; the failure surfaces as a message.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = [
                CustomsInvoiceBookingResponse,
                CustomsRetrievalErrorResponse,
            ]
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**CustomsInvoiceShipmentPayload)
                )
                .from_(gateway)
                .parse()
            )
            self.assertEqual(mock.call_count, 2)
        details, messages = parsed_response
        self.assertIsNotNone(details)
        self.assertEqual(details.tracking_number, "00373500454541020957")
        self.assertEqual(details.docs.label, "JVBERi0xLjQK")
        self.assertEqual(details.docs.extra_documents, [])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].code, "EDI_NOT_FOUND")

    def test_create_shipment_customs_invoice_document_transport_failure_fails_open(
        self,
    ):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = [
                CustomsInvoiceBookingResponse,
                ConnectionError("connection reset"),
            ]
            parsed_response = (
                karrio.Shipment.create(
                    models.ShipmentRequest(**CustomsInvoiceShipmentPayload)
                )
                .from_(gateway)
                .parse()
            )
            self.assertEqual(mock.call_count, 2)
        details, messages = parsed_response
        self.assertIsNotNone(details)
        self.assertEqual(details.docs.extra_documents, [])
        self.assertEqual(len(messages), 1)
        self.assertIn("customs document retrieval failed", messages[0].message)

    def test_create_shipment_parcel_without_customs_skips_fetch(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = CustomsInvoiceBookingResponse
            parsed_response = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload))
                .from_(gateway)
                .parse()
            )
            mock.assert_called_once()
        details, messages = parsed_response
        self.assertEqual(messages, [])
        self.assertEqual(details.docs.extra_documents, [])


class TestPostNordCustomsInvoice(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def _invoice(self, payload: dict) -> dict:
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        return lib.to_dict(request.serialize())["shipment"][0]["customsInvoice"]

    def _field_errors(self, payload: dict) -> dict:
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            shipment, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**payload))
                .from_(gateway)
                .parse()
            )
            mock.assert_not_called()
        self.assertIsNone(shipment)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].code, "SHIPPING_SDK_FIELD_ERROR")
        return messages[0].details

    def test_create_shipment_customs_invoice_request(self):
        # A parcel product with customs data carries customsInvoice built
        # from the unified payload, and no CN22 or CN23 branch.
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**CustomsInvoiceShipmentPayload)
        )
        self.assertEqual(
            lib.to_dict(request.serialize()), CustomsInvoiceShipmentRequest
        )

    def test_create_shipment_customs_invoice_for_parcel_products(self):
        for service in [
            "postnord_mypack_home",
            "postnord_mypack_collect",
            "postnord_parcel",
            "postnord_pallet",
        ]:
            with self.subTest(service=service):
                request = gateway.mapper.create_shipment_request(
                    models.ShipmentRequest(
                        **{**CustomsInvoiceShipmentPayload, "service": service}
                    )
                )
                shipment = lib.to_dict(request.serialize())["shipment"][0]
                self.assertIn("customsInvoice", shipment)
                self.assertNotIn("customsDeclarationCN22", shipment)
                self.assertNotIn("customsDeclarationCN23", shipment)

    def test_create_shipment_customs_invoice_keeps_leading_zero_postal_code(self):
        invoice = self._invoice(CustomsInvoiceShipmentPayload)
        self.assertEqual(invoice["buyer"]["postalCode"], "0154")

    def test_create_shipment_customs_invoice_number_falls_back_to_reference(self):
        payload = {
            **CustomsInvoiceShipmentPayload,
            "customs": {
                key: value
                for key, value in CustomsInvoiceShipmentPayload["customs"].items()
                if key != "invoice"
            },
        }
        invoice = self._invoice(payload)
        self.assertEqual(invoice["invoice"]["invoiceNo"], "ORDER-7788")

    def test_create_shipment_customs_invoice_without_number_or_reference(self):
        payload = {
            key: value
            for key, value in CustomsInvoiceShipmentPayload.items()
            if key != "reference"
        }
        payload["customs"] = {
            key: value
            for key, value in CustomsInvoiceShipmentPayload["customs"].items()
            if key != "invoice"
        }
        self.assertEqual(
            self._field_errors(payload),
            {
                "customs.invoice": (
                    "invoice number is required for a PostNord customs invoice; "
                    "send customs.invoice or a shipment reference"
                )
            },
        )

    def test_create_shipment_customs_invoice_without_seller_vat_number(self):
        payload = {
            **CustomsInvoiceShipmentPayload,
            "shipper": {
                key: value
                for key, value in CustomsInvoiceShipmentPayload["shipper"].items()
                if key != "federal_tax_id"
            },
        }
        self.assertEqual(
            self._field_errors(payload),
            {
                "shipper.federal_tax_id": (
                    "shipper VAT number is required for a PostNord customs invoice"
                )
            },
        )

    def test_create_shipment_customs_invoice_without_party_contacts(self):
        # Contact name falls back to the company name, so only a party with
        # neither person nor company name lacks one.
        payload = {
            **CustomsInvoiceShipmentPayload,
            "shipper": {
                **CustomsInvoiceShipmentPayload["shipper"],
                "person_name": None,
                "company_name": None,
            },
            "recipient": {
                **CustomsInvoiceShipmentPayload["recipient"],
                "phone_number": None,
            },
        }
        self.assertEqual(
            self._field_errors(payload),
            {
                "shipper.person_name": (
                    "contact name is required for a PostNord customs invoice"
                ),
                "recipient.phone_number": (
                    "contact phone number is required for a PostNord customs invoice"
                ),
            },
        )

    def test_create_shipment_customs_invoice_without_line_tariff_or_origin(self):
        commodities = CustomsInvoiceShipmentPayload["customs"]["commodities"]
        payload = {
            **CustomsInvoiceShipmentPayload,
            "customs": {
                **CustomsInvoiceShipmentPayload["customs"],
                "commodities": [
                    {k: v for k, v in commodities[0].items() if k != "hs_code"},
                    {k: v for k, v in commodities[1].items() if k != "origin_country"},
                ],
            },
        }
        self.assertEqual(
            self._field_errors(payload),
            {
                "customs.commodities[0].hs_code": (
                    "HS tariff number is required for a PostNord customs invoice line"
                ),
                "customs.commodities[1].origin_country": (
                    "country of origin is required for a PostNord customs invoice line"
                ),
            },
        )

    def test_create_shipment_customs_invoice_without_registration_numbers(self):
        # The CN22 registration rule does not apply: the sandbox accepted a
        # parcel customsInvoice without EORI, VOEC, or IOSS (2026-09-25), so
        # the invoice is sent as-is for PostNord to judge.
        payload = {
            **CustomsInvoiceShipmentPayload,
            "customs": {
                **CustomsInvoiceShipmentPayload["customs"],
                "options": {},
            },
        }
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        expected_invoice = CustomsInvoiceShipmentRequest["shipment"][0][
            "customsInvoice"
        ]
        self.assertEqual(
            lib.to_dict(request.serialize())["shipment"][0]["customsInvoice"],
            {
                **expected_invoice,
                "seller": {
                    k: v
                    for k, v in expected_invoice["seller"].items()
                    if k != "eoriNo"
                },
            },
        )

    def test_create_shipment_customs_invoice_registration_numbers(self):
        payload = {
            **CustomsInvoiceShipmentPayload,
            "customs": {
                **CustomsInvoiceShipmentPayload["customs"],
                "options": {
                    "eori_number": "SE556000123401",
                    "voec_number": "1234567",
                    "ioss_number": "IM1234567890",
                },
            },
        }
        invoice = self._invoice(payload)
        self.assertEqual(invoice["seller"]["eoriNo"], "SE556000123401")
        self.assertEqual(invoice["voec"], "1234567")
        self.assertEqual(invoice["ioss"], "IM1234567890")

    def test_create_shipment_customs_invoice_line_totals_over_quantity(self):
        invoice = self._invoice(
            {
                **CustomsInvoiceShipmentPayload,
                "customs": {
                    **CustomsInvoiceShipmentPayload["customs"],
                    "commodities": QuantityThreeCN22Payload["customs"]["commodities"],
                },
            }
        )
        self.assertEqual(
            [
                (line["quantity"], line["netWeight"], line["grossWeight"], line["itemValue"])
                for line in invoice["detailedDescription"]
            ],
            [
                (
                    3,
                    {"value": 0.6, "unit": "KGM"},
                    {"value": 0.6, "unit": "KGM"},
                    {"amount": 30.0, "currency": "SEK"},
                ),
                (
                    1,
                    {"value": 0.1, "unit": "KGM"},
                    {"value": 0.1, "unit": "KGM"},
                    {"amount": 5.0, "currency": "SEK"},
                ),
            ],
        )
        self.assertEqual(invoice["invoiceTotal"], {"amount": 35.0, "currency": "SEK"})
        # Net weight sums the commodity lines; gross weight is the parcel's
        # 1.5 kg, which includes packaging.
        self.assertEqual(invoice["totalNetWeight"], {"value": 0.7, "unit": "KGM"})
        self.assertEqual(invoice["totalGrossWeight"], {"value": 1.5, "unit": "KGM"})

    def test_create_shipment_customs_invoice_gross_weight_falls_back_to_lines(self):
        invoice = self._invoice(
            {
                **CustomsInvoiceShipmentPayload,
                "parcels": [
                    {"length": 30.0, "width": 20.0, "height": 10.0, "dimension_unit": "CM"}
                ],
            }
        )
        self.assertEqual(invoice["totalNetWeight"], {"value": 0.5, "unit": "KGM"})
        self.assertEqual(invoice["totalGrossWeight"], {"value": 0.5, "unit": "KGM"})

    def test_create_shipment_customs_invoice_commercial_type(self):
        invoice = self._invoice(CustomsInvoiceShipmentPayload)
        self.assertEqual(invoice["type"], "COMMERCIAL")

    def test_create_shipment_customs_invoice_proforma_type(self):
        # The flag applies literally: false and omitted both declare a
        # proforma invoice, even for merchandise.
        customs = CustomsInvoiceShipmentPayload["customs"]
        omitted = {k: v for k, v in customs.items() if k != "commercial_invoice"}
        for label, customs_payload in [
            ("false", {**customs, "commercial_invoice": False}),
            ("omitted", omitted),
        ]:
            with self.subTest(commercial_invoice=label):
                self.assertEqual(customs_payload["content_type"], "merchandise")
                invoice = self._invoice(
                    {**CustomsInvoiceShipmentPayload, "customs": customs_payload}
                )
                self.assertEqual(invoice["type"], "PROFORMA")


class TestPostNordEUVATArea(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_in_eu_vat_area(self):
        cases = [
            ("SE", "11143", True),
            ("PL", "00-001", True),
            ("GR", "10552", True),
            ("EL", "10552", True),
            ("DE", "10115", True),
            ("DE", "78266", False),
            ("DE", "27498", False),
            ("IT", "23041", False),
            ("IT", "22061", False),
            ("IT", "00100", True),
            ("FI", "22100", False),
            ("FI", "22 100", False),
            ("FI", "00100", True),
            ("AX", "22100", False),
            ("ES", "35001", False),
            ("ES", "38001", False),
            ("ES", "51001", False),
            ("ES", "52001", False),
            ("ES", "28001", True),
            ("IC", "35001", False),
            ("GP", "97110", False),
            ("GF", "97300", False),
            ("MQ", "97200", False),
            ("RE", "97400", False),
            ("YT", "97600", False),
            ("NO", "0154", False),
            ("GB", "SW1A 1AA", False),
            ("GB", "BT1 1AA", True),
            ("GB", "bt1 1aa", True),
            ("GB", "EC1A 1BB", False),
            ("MC", "98000", True),
            ("FR", "98000", True),
            ("GR", "630 86", False),
            ("CH", "8001", False),
            (None, None, False),
        ]
        for country_code, postal_code, expected in cases:
            with self.subTest(country_code=country_code, postal_code=postal_code):
                self.assertEqual(
                    provider_units.in_eu_vat_area(country_code, postal_code),
                    expected,
                )

    def test_intra_eu_parcel_omits_customs_and_warns(self):
        payload = {
            **CustomsInvoiceShipmentPayload,
            "recipient": PolandRecipient,
        }
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        shipment = lib.to_dict(request.serialize())["shipment"][0]
        for structure in [
            "customsDeclarationCN22",
            "customsDeclarationCN23",
            "customsInvoice",
        ]:
            self.assertNotIn(structure, shipment)

        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = CustomsInvoiceBookingResponse
            details, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**payload))
                .from_(gateway)
                .parse()
            )
            mock.assert_called_once()
        self.assertIsNotNone(details)
        self.assertEqual(details.docs.extra_documents, [])
        self.assertListEqual(
            lib.to_dict(messages),
            [
                {
                    "carrier_id": "postnord",
                    "carrier_name": "postnord",
                    "code": "customs_omitted_intra_eu",
                    "level": "warning",
                    "message": (
                        "Customs data was not sent: the shipment from SE to PL "
                        "stays within the EU VAT area"
                    ),
                }
            ],
        )

    def test_intra_eu_skips_customs_fail_fast_checks(self):
        # A letter to Germany without registration numbers, shipper VAT
        # number, HS codes, and with misplaced registration keys and too
        # many lines is sent without customs instead of failing.
        payload = {
            **_customs_payload(14),
            "recipient": GermanyRecipient,
            "options": {"eori_number": "SE556000123401"},
        }
        payload["customs"] = {
            key: value for key, value in payload["customs"].items() if key != "options"
        }
        for service in ["postnord_tracked_letter", "postnord_parcel"]:
            with self.subTest(service=service):
                with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
                    mock.return_value = ShipmentResponse
                    details, messages = (
                        karrio.Shipment.create(
                            models.ShipmentRequest(
                                **{**payload, "service": service, "reference": None}
                            )
                        )
                        .from_(gateway)
                        .parse()
                    )
                    mock.assert_called_once()
                    body = json.loads(mock.call_args[1]["data"])
                self.assertIsNotNone(details)
                self.assertNotIn("customsDeclarationCN22", body["shipment"][0])
                self.assertNotIn("customsInvoice", body["shipment"][0])
                self.assertEqual(
                    [message.code for message in messages],
                    ["customs_omitted_intra_eu"],
                )

    def test_aland_parcel_keeps_customs_invoice(self):
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(
                **{**CustomsInvoiceShipmentPayload, "recipient": AlandRecipient}
            )
        )
        shipment = lib.to_dict(request.serialize())["shipment"][0]
        self.assertEqual(shipment["customsInvoice"]["buyer"]["postalCode"], "22100")
        self.assertIsNone(request.ctx.get("customs_omitted"))

    def test_norway_keeps_customs(self):
        for payload, structure in [
            (CustomsInvoiceShipmentPayload, "customsInvoice"),
            (CustomsShipmentPayload, "customsDeclarationCN22"),
        ]:
            with self.subTest(structure=structure):
                request = gateway.mapper.create_shipment_request(
                    models.ShipmentRequest(**payload)
                )
                self.assertIn(
                    structure, lib.to_dict(request.serialize())["shipment"][0]
                )
                self.assertIsNone(request.ctx.get("customs_omitted"))

    def test_intra_eu_without_customs_does_not_warn(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ShipmentResponse
            _, messages = (
                karrio.Shipment.create(models.ShipmentRequest(**ShipmentPayload))
                .from_(gateway)
                .parse()
            )
        self.assertEqual(messages, [])


class TestPostNordProductGroups(unittest.TestCase):
    def test_letter_services_pinned(self):
        self.assertEqual(
            {service.value for service in provider_units.LETTER_SERVICES},
            {"04", "34", "UX", "86", "LX", "RR", "RK", "RL", "RE", "RQ", "VV", "AF"},
        )
        self.assertEqual(provider_units.INTERNATIONAL_PARCEL_SERVICE.value, "91")

    def test_every_service_classifies_into_one_customs_structure(self):
        # Letters and International Parcel keep CN22; every other service,
        # including ones added later, is a parcel product sending an invoice.
        for service in provider_units.ShippingService:
            with self.subTest(service=service.name):
                is_cn22 = lib.identity(
                    service in provider_units.LETTER_SERVICES
                    or service == provider_units.INTERNATIONAL_PARCEL_SERVICE
                )
                self.assertEqual(
                    provider_units.customs_structure(service.value),
                    lib.identity(
                        provider_units.CustomsStructure.cn22
                        if is_cn22
                        else provider_units.CustomsStructure.customs_invoice
                    ),
                )

    def test_unknown_service_code_is_parcel_product(self):
        self.assertEqual(
            provider_units.customs_structure("99"),
            provider_units.CustomsStructure.customs_invoice,
        )


if __name__ == "__main__":
    unittest.main()


ShipmentPayload = {
    "shipper": {
        "address_line1": "Sandhamnsgatan 61",
        "city": "Stockholm",
        "postal_code": "11528",
        "country_code": "SE",
        "state_code": "Stockholm",
        "person_name": "John Sender",
        "company_name": "ACME Sender AB",
        "phone_number": "+46701234567",
        "email": "sender@example.com",
    },
    "recipient": {
        "address_line1": "Terminalvagen 24",
        "city": "Solna",
        "postal_code": "17173",
        "country_code": "SE",
        "state_code": "Stockholm",
        "person_name": "Jane Receiver",
        "company_name": "Receiver Co",
        "phone_number": "+46709876543",
        "email": "receiver@example.com",
    },
    "parcels": [
        {
            "weight": 1.5,
            "width": 20.0,
            "height": 10.0,
            "length": 30.0,
            "weight_unit": "KG",
            "dimension_unit": "CM",
            "packaging_type": "small_box",
        }
    ],
    "service": "postnord_parcel",
    "options": {"insurance": 500.0},
    "reference": "ORDER-7788",
}

ShipmentCancelPayload = {
    "shipment_identifier": "SHIP-0001",
}

ShipmentRequest = {
    "application": {"name": "Karrio", "applicationId": 2458},
    "messageDate": ANY,
    "language": "EN",
    "testIndicator": True,
    "updateIndicator": "Original",
    "shipment": [
        {
            "shipmentIdentification": {"shipmentId": "ORDER-7788"},
            "service": {
                "basicServiceCode": "18",
                "additionalServiceCode": ["A5"],
            },
            "parties": {
                "consignor": {
                    "issuerCode": "Z12",
                    "partyIdentification": {
                        "partyId": "00000000",
                        "partyIdType": "160",
                    },
                    "party": {
                        "nameIdentification": {
                            "name": "John Sender",
                            "companyName": "ACME Sender AB",
                        },
                        "address": {
                            "streets": ["Sandhamnsgatan 61"],
                            "postalCode": "11528",
                            "state": "Stockholm",
                            "city": "Stockholm",
                            "countryCode": "SE",
                        },
                        "contact": {
                            "contactName": "John Sender",
                            "emailAddress": "sender@example.com",
                            "phoneNo": "+46701234567",
                            "smsNo": "+46701234567",
                        },
                    },
                },
                "consignee": {
                    "issuerCode": "Z12",
                    "party": {
                        "nameIdentification": {
                            "name": "Jane Receiver",
                            "companyName": "Receiver Co",
                        },
                        "address": {
                            "streets": ["Terminalvagen 24"],
                            "postalCode": "17173",
                            "state": "Stockholm",
                            "city": "Solna",
                            "countryCode": "SE",
                        },
                        "contact": {
                            "contactName": "Jane Receiver",
                            "emailAddress": "receiver@example.com",
                            "phoneNo": "+46709876543",
                            "smsNo": "+46709876543",
                        },
                    },
                },
            },
            "goodsItem": [
                {
                    "packageTypeCode": "BX",
                    "numberOfPackageTypeCodeItems": {"value": 1},
                    "items": [
                        {
                            "itemIdentification": {"itemId": "0"},
                            "grossWeight": {"value": 1.5, "unit": "KGM"},
                            "dimensions": {
                                "height": {"value": 10.0, "unit": "CMT"},
                                "width": {"value": 20.0, "unit": "CMT"},
                                "length": {"value": 30.0, "unit": "CMT"},
                            },
                        }
                    ],
                }
            ],
        }
    ],
}

# Customs is only sent outside the EU VAT area, so customs fixtures ship
# from Sweden to Norway.
NorwayRecipient = {
    "address_line1": "Karl Johans gate 22",
    "city": "Oslo",
    "postal_code": "0154",
    "country_code": "NO",
    "person_name": "Kari Receiver",
    "company_name": "Receiver AS",
    "phone_number": "+4791234567",
    "email": "receiver@example.com",
}

NorwayConsignee = {
    "issuerCode": "Z12",
    "party": {
        "nameIdentification": {
            "name": "Kari Receiver",
            "companyName": "Receiver AS",
        },
        "address": {
            "streets": ["Karl Johans gate 22"],
            "postalCode": "0154",
            "city": "Oslo",
            "countryCode": "NO",
        },
        "contact": {
            "contactName": "Kari Receiver",
            "emailAddress": "receiver@example.com",
            "phoneNo": "+4791234567",
            "smsNo": "+4791234567",
        },
    },
}

PolandRecipient = {
    **NorwayRecipient,
    "address_line1": "ul. Marszalkowska 1",
    "city": "Warszawa",
    "postal_code": "00-001",
    "country_code": "PL",
}
GermanyRecipient = {
    **NorwayRecipient,
    "address_line1": "Unter den Linden 1",
    "city": "Berlin",
    "postal_code": "10117",
    "country_code": "DE",
}
AlandRecipient = {
    **NorwayRecipient,
    "address_line1": "Torggatan 1",
    "city": "Mariehamn",
    "postal_code": "22100",
    "country_code": "FI",
}

# CN22 is sent for letters and International Parcel; a tracked letter
# exercises the CN22 branch without triggering the export-letter fetch.
CustomsShipmentPayload = {
    **ShipmentPayload,
    "recipient": NorwayRecipient,
    "service": "postnord_tracked_letter",
    "customs": {
        "content_type": "merchandise",
        "commodities": [
            {
                "title": "Wool socks",
                "quantity": 2,
                "weight": 0.4,
                "weight_unit": "KG",
                "value_amount": 25.0,
                "value_currency": "SEK",
                "hs_code": "6115950000",
                "origin_country": "SE",
            },
            {
                # description-only line: covers the title fallback; the
                # non-SEK currency pins totalValue to the FIRST line's
                # currency rather than the last line's.
                "description": "Baseball cap",
                "quantity": 1,
                "weight": 2.205,
                "weight_unit": "LB",
                "value_amount": 15.0,
                "value_currency": "EUR",
                "hs_code": "6505003000",
                "origin_country": "CN",
            },
        ],
        "options": {"eori_number": "SE556000123401"},
    },
}

CustomsShipmentRequest = {
    **ShipmentRequest,
    "shipment": [
        {
            **ShipmentRequest["shipment"][0],
            "service": {
                "basicServiceCode": "34",
                "additionalServiceCode": ["A5"],
            },
            "parties": {
                **ShipmentRequest["shipment"][0]["parties"],
                "consignee": NorwayConsignee,
            },
            "customsDeclarationCN22": {
                "EORIorPersonalIdNumber": "SE556000123401",
                "countryOfOrigin": "SE",
                "categoryOfItem": {"categoryType": ["SALE OF GOODS"]},
                "detailedDescription": [
                    {
                        # 2 x (0.4 kg, 25 SEK): line totals over the quantity
                        "content": "Wool socks",
                        "quantity": {"value": 2},
                        "grossWeight": {"value": 0.8, "unit": "KGM"},
                        "value": {"amount": 50.0, "currency": "SEK"},
                        "hsTariffNumber": "6115950000",
                        "countryCode": "SE",
                        "rowNo": 1,
                    },
                    {
                        "content": "Baseball cap",
                        "quantity": {"value": 1},
                        # 2.205 LB converts to exactly 1.0 KGM
                        "grossWeight": {"value": 1.0, "unit": "KGM"},
                        "value": {"amount": 15.0, "currency": "EUR"},
                        "hsTariffNumber": "6505003000",
                        "countryCode": "CN",
                        "rowNo": 2,
                    },
                ],
                "totalGrossWeight": {"value": 1.5, "unit": "KGM"},
                "totalValue": {"amount": 65.0, "currency": "SEK"},
            },
        }
    ],
}


CustomsRegistrationShipmentPayload = {
    **CustomsShipmentPayload,
    "customs": {
        **CustomsShipmentPayload["customs"],
        "options": {
            "eori_number": "SE556000123401",
            "voec_number": "1234567",
            "ioss_number": "IM1234567890",
        },
    },
}

CustomsRegistrationShipmentRequest = {
    **CustomsShipmentRequest,
    "shipment": [
        {
            **CustomsShipmentRequest["shipment"][0],
            "customsDeclarationCN22": {
                **CustomsShipmentRequest["shipment"][0]["customsDeclarationCN22"],
                "EORIorPersonalIdNumber": "SE556000123401",
                "voec": "1234567",
                "ioss": "IM1234567890",
            },
        }
    ],
}


def _customs_payload(lines: int) -> dict:
    return {
        **ShipmentPayload,
        "recipient": NorwayRecipient,
        "service": "postnord_tracked_letter",
        "customs": {
            "content_type": "merchandise",
            "commodities": [
                {
                    "title": f"Item {index}",
                    "quantity": 1,
                    "weight": 0.1,
                    "weight_unit": "KG",
                    "value_amount": 1.0,
                    "value_currency": "SEK",
                }
                for index in range(1, lines + 1)
            ],
            "options": {"eori_number": "SE556000123401"},
        },
    }


# A quantity-3 commodity with per-unit value 10 SEK and weight 0.2 kg next
# to a single-unit line: lines carry 30 SEK / 0.6 kg and 5 SEK / 0.1 kg.
QuantityThreeCN22Payload = {
    **ShipmentPayload,
    "recipient": NorwayRecipient,
    "service": "postnord_tracked_letter",
    "customs": {
        "options": {"eori_number": "SE556000123401"},
        "commodities": [
            {
                "title": "Enamel pin",
                "quantity": 3,
                "weight": 0.2,
                "weight_unit": "KG",
                "value_amount": 10.0,
                "value_currency": "SEK",
                "hs_code": "7117190000",
                "origin_country": "SE",
            },
            {
                "title": "Postcard",
                "quantity": 1,
                "weight": 0.1,
                "weight_unit": "KG",
                "value_amount": 5.0,
                "value_currency": "SEK",
                "hs_code": "4909000000",
                "origin_country": "SE",
            },
        ],
    },
}

# Export letter (UX) to an international recipient with the customs block:
# the payload shape that triggers the implicit by-id customs document fetch.
ExportLetterCustomsPayload = {
    **ShipmentPayload,
    "recipient": {**ShipmentPayload["recipient"], "country_code": "US"},
    "service": "postnord_export_letter",
    "customs": CustomsShipmentPayload["customs"],
}

# Parcel product from Sweden to Norway with customs: the payload shape that
# selects the customsInvoice branch instead of CN22.
CustomsInvoiceShipmentPayload = {
    **ShipmentPayload,
    "shipper": {**ShipmentPayload["shipper"], "federal_tax_id": "SE556123471101"},
    "recipient": NorwayRecipient,
    "customs": {
        "content_type": "merchandise",
        "commercial_invoice": True,
        "invoice": "INV-2026-001",
        "invoice_date": "2026-09-25",
        "commodities": [
            {
                "title": "Wool socks",
                "quantity": 2,
                "weight": 0.2,
                "weight_unit": "KG",
                "value_amount": 150.0,
                "value_currency": "SEK",
                "hs_code": "6115950000",
                "origin_country": "SE",
            },
            {
                "description": "Knitted cap",
                "quantity": 1,
                "weight": 0.1,
                "weight_unit": "KG",
                "value_amount": 200.0,
                "value_currency": "SEK",
                "hs_code": "6505003000",
                "origin_country": "SE",
            },
        ],
        "options": {"eori_number": "SE556000123401"},
    },
}

CustomsInvoiceShipmentRequest = {
    **ShipmentRequest,
    "shipment": [
        {
            **ShipmentRequest["shipment"][0],
            "parties": {
                **ShipmentRequest["shipment"][0]["parties"],
                "consignee": NorwayConsignee,
            },
            "customsInvoice": {
                "declarationType": "invoiceExportDeclaration",
                "type": "COMMERCIAL",
                "seller": {
                    "partyIdentification": {
                        "partyId": "00000000",
                        "partyIdType": "160",
                    },
                    "vatNo": "SE556123471101",
                    "name": "ACME Sender AB",
                    "streets": ["Sandhamnsgatan 61"],
                    "city": "Stockholm",
                    "postalCode": "11528",
                    "countryCode": "SE",
                    "contacts": {
                        "name": "John Sender",
                        "phoneNo": "+46701234567",
                        "emailAddress": "sender@example.com",
                    },
                    "eoriNo": "SE556000123401",
                },
                "buyer": {
                    "name": "Receiver AS",
                    "streets": ["Karl Johans gate 22"],
                    "city": "Oslo",
                    "postalCode": "0154",
                    "countryCode": "NO",
                    "contacts": {
                        "name": "Kari Receiver",
                        "phoneNo": "+4791234567",
                        "emailAddress": "receiver@example.com",
                    },
                },
                "invoice": {
                    "invoiceNo": "INV-2026-001",
                    "shippingDate": "2026-09-25",
                    "reasonForExportation": "1000",
                },
                "detailedDescription": [
                    {
                        "quantity": 2,
                        "hsTariffNumber": "6115950000",
                        "content": "Wool socks",
                        "countryOfOrigin": "SE",
                        "netWeight": {"value": 0.4, "unit": "KGM"},
                        "grossWeight": {"value": 0.4, "unit": "KGM"},
                        "itemValue": {"amount": 300.0, "currency": "SEK"},
                    },
                    {
                        "quantity": 1,
                        "hsTariffNumber": "6505003000",
                        "content": "Knitted cap",
                        "countryOfOrigin": "SE",
                        "netWeight": {"value": 0.1, "unit": "KGM"},
                        "grossWeight": {"value": 0.1, "unit": "KGM"},
                        "itemValue": {"amount": 200.0, "currency": "SEK"},
                    },
                ],
                "totalNetWeight": {"value": 0.5, "unit": "KGM"},
                "totalGrossWeight": {"value": 1.5, "unit": "KGM"},
                "invoiceTotal": {"amount": 500.0, "currency": "SEK"},
            },
        }
    ],
}

ShipmentCancelRequest = {
    "ids": [{"id": "SHIP-0001"}],
}

ShipmentResponse = """{
  "bookingResponse": {
    "bookingId": "BOOK-123",
    "idInformation": [{
      "status": "OK",
      "ids": [
        {"idType": "itemId", "value": "00373500454541020957", "printId": "P1"},
        {"idType": "shipmentId", "value": "SHIP-0001", "printId": "P2"}
      ],
      "urls": [
        {"type": "TRACKING", "url": "https://tracking.postnord.com/se/?id=00373500454541020957"}
      ],
      "errorResponse": null
    }]
  },
  "labelPrintout": [{
    "printout": {"type": "LABEL", "labelFormat": "PDF", "encoding": "base64", "data": "JVBERi0xLjQK"}
  }]
}"""

ShipmentCancelResponse = "{}"

ErrorResponse = """{
  "message": "Invalid indata object EdiInstruction",
  "compositeFault": {
    "faults": [
      {
        "explanationText": "applicationId (2458) is not a type of integer",
        "faultReferences": [
          {"key": "CustomerOriginValidationError.type", "value": "MANDATORY_FIELDS_MISSING"},
          {"key": "CustomerOriginValidationError.subType", "value": "APPLICATION_ID"}
        ]
      },
      {
        "explanationText": "itemIdentification is a required field",
        "faultReferences": [
          {"key": "CustomerOriginValidationError.type", "value": "MANDATORY_FIELDS_MISSING"},
          {"key": "CustomerOriginValidationError.subType", "value": "ITEM_IDENTIFICATION"}
        ]
      }
    ]
  }
}"""

ParsedShipmentResponse = [
    {
        "carrier_id": "postnord",
        "carrier_name": "postnord",
        "tracking_number": "00373500454541020957",
        "shipment_identifier": "ORDER-7788",
        "label_type": "PDF",
        "docs": {"label": "JVBERi0xLjQK"},
        "meta": {
            "booking_id": "BOOK-123",
            "tracking_url": "https://tracking.postnord.com/se/?id=00373500454541020957",
            "carrier_tracking_link": "https://tracking.postnord.com/se/?id=00373500454541020957",
        },
    },
    [],
]

ParsedShipmentCancelResponse = [
    None,
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "code": "cancellation_unsupported",
            "message": (
                "PostNord REST cancellation is unavailable: the id-based delete "
                "endpoint is pending. The shipment was not cancelled."
            ),
        }
    ],
]

ParsedErrorResponse = [
    None,
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "code": "APPLICATION_ID",
            "message": "applicationId (2458) is not a type of integer",
            "details": {
                "references": {
                    "CustomerOriginValidationError.type": "MANDATORY_FIELDS_MISSING",
                    "CustomerOriginValidationError.subType": "APPLICATION_ID",
                }
            },
        },
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "code": "ITEM_IDENTIFICATION",
            "message": "itemIdentification is a required field",
            "details": {
                "references": {
                    "CustomerOriginValidationError.type": "MANDATORY_FIELDS_MISSING",
                    "CustomerOriginValidationError.subType": "ITEM_IDENTIFICATION",
                }
            },
        },
    ],
]

# PostNord API-gateway / auth error envelope (403 not authorized for the product).
AuthErrorResponse = """{
  "error": {
    "status_code": 403,
    "error_type": "Forbidden",
    "message": "Invalid API Key",
    "xrequestid": "278b9442a7efatapi28363581782383141"
  }
}"""

ParsedAuthErrorResponse = [
    None,
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "code": "Forbidden",
            "level": "error",
            "message": (
                "Invalid API Key: the PostNord API key is not authorized for "
                "this service/product"
            ),
            "details": {"status_code": 403},
        }
    ],
]

PartialFailureResponse = """{
  "bookingResponse": {
    "bookingId": "BOOK-456",
    "idInformation": [
      {
        "status": "OK",
        "ids": [
          {"idType": "itemId", "value": "00373500454541020958", "printId": "P1"},
          {"idType": "shipmentId", "value": "ORDER-7788", "printId": "P2"}
        ],
        "urls": [
          {"type": "TRACKING", "url": "https://tracking.postnord.com/se/?id=00373500454541020958"}
        ],
        "errorResponse": null
      },
      {
        "status": "ERROR",
        "ids": null,
        "urls": null,
        "errorResponse": {
          "compositeFault": {
            "faults": [
              {
                "explanationText": "grossWeight exceeds maximum for service",
                "faultReferences": [
                  {"key": "CustomerValidationError.subType", "value": "WEIGHT_LIMIT"}
                ]
              }
            ]
          }
        }
      }
    ]
  },
  "labelPrintout": [{
    "printout": {"type": "LABEL", "labelFormat": "PDF", "encoding": "base64", "data": "JVBERi0xLjQK"}
  }]
}"""

ParsedPartialFailureResponse = [
    {
        "carrier_id": "postnord",
        "carrier_name": "postnord",
        "tracking_number": "00373500454541020958",
        "shipment_identifier": "ORDER-7788",
        "label_type": "PDF",
        "docs": {"label": "JVBERi0xLjQK"},
        "meta": {
            "booking_id": "BOOK-456",
            "tracking_url": "https://tracking.postnord.com/se/?id=00373500454541020958",
            "carrier_tracking_link": "https://tracking.postnord.com/se/?id=00373500454541020958",
        },
    },
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "code": "WEIGHT_LIMIT",
            "message": "grossWeight exceeds maximum for service",
            "details": {
                "references": {
                    "CustomerValidationError.subType": "WEIGHT_LIMIT",
                }
            },
        }
    ],
]

# Raw ZPL fragments modeled on the live /labels/zpl observation: persistent
# host commands (^LL/^CI28/^PO) then the format body (^XA...^XZ) with ^CW font
# aliasing to printer-memory fonts. Truncated for fixture use.
RawZPL = (
    "^LL1520\n"
    "^FX utf-8^FS    ^CI28\n"
    "^PON\n"
    "^XA\n"
    "^CWW,E:ARI000.TTF\n"
    "^CWW,E:ARIAL.TTF\n"
    "^CWW,E:T0003M_\n"
    "^A@N,50,50,E:ARI000.TTF\n"
    "^FO50,50\n"
    "^FD00373500454541020957\n"
    "^FS\n"
    "^XZ"
)

RawZPL2 = (
    "^XA\n"
    "^A@N,40,40,E:ARI000.TTF\n"
    "^FO60,80\n"
    "^FDORDER-7788\n"
    "^FS\n"
    "^XZ"
)


def _zpl_json(zpl: str) -> str:
    return zpl.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


ShipmentZPLResponse = """{
  "bookingResponse": {
    "bookingId": "BOOK-789",
    "idInformation": [{
      "status": "OK",
      "ids": [
        {"idType": "itemId", "value": "00373500454541020957", "printId": "P1"},
        {"idType": "shipmentId", "value": "ORDER-7788", "printId": "P2"}
      ],
      "urls": [
        {"type": "TRACKING", "url": "https://tracking.postnord.com/se/?id=00373500454541020957"}
      ],
      "errorResponse": null
    }]
  },
  "labelPrintout": [{
    "printout": {"type": "LABEL", "labelFormat": "ZPL", "encoding": "none", "data": "%s"}
  }]
}""" % _zpl_json(RawZPL)

ShipmentZPLNoFormatResponse = ShipmentZPLResponse.replace(
    '"labelFormat": "ZPL", ', ""
)

ShipmentZPLMultiResponse = """{
  "bookingResponse": {
    "bookingId": "BOOK-789",
    "idInformation": [{
      "status": "OK",
      "ids": [
        {"idType": "itemId", "value": "00373500454541020957", "printId": "P1"}
      ],
      "urls": [],
      "errorResponse": null
    }]
  },
  "labelPrintout": [
    {"printout": {"type": "LABEL", "labelFormat": "ZPL", "encoding": "none", "data": "%s"}},
    {"printout": {"type": "LABEL", "labelFormat": "ZPL", "encoding": "none", "data": "%s"}}
  ]
}""" % (_zpl_json(RawZPL), _zpl_json(RawZPL2))

# Base64 data with the encoding element absent (the swagger documents only
# "base64", so the element can be omitted): the data passes through as is.
ShipmentNoEncodingResponse = ShipmentResponse.replace(
    '"labelFormat": "PDF", "encoding": "base64", ', '"labelFormat": "PDF", '
)

# Booking response whose label printout also carries a composed CN22
# (printoutComposition), the shape an export-letter booking with an embedded
# declaration returns.
CustomsBookingResponse = """{
  "bookingResponse": {
    "bookingId": "BOOK-UX1",
    "idInformation": [{
      "status": "OK",
      "ids": [
        {"idType": "itemId", "value": "00373500454541020957", "printId": "P1"},
        {"idType": "shipmentId", "value": "ORDER-7788", "printId": "P2"}
      ],
      "urls": [
        {"type": "TRACKING", "url": "https://tracking.postnord.com/se/?id=00373500454541020957"}
      ],
      "errorResponse": null
    }]
  },
  "labelPrintout": [{
    "printout": {"type": "LABEL", "labelFormat": "PDF", "encoding": "base64", "data": "JVBERi0xLjQK"},
    "printoutComposition": {"label": 1, "cn22": 1}
  }]
}"""

CustomsBookingZPLResponse = """{
  "bookingResponse": {
    "bookingId": "BOOK-UX2",
    "idInformation": [{
      "status": "OK",
      "ids": [
        {"idType": "itemId", "value": "00373500454541020957", "printId": "P1"}
      ],
      "urls": [],
      "errorResponse": null
    }]
  },
  "labelPrintout": [{
    "printout": {"type": "LABEL", "labelFormat": "ZPL", "encoding": "none", "data": "%s"},
    "printoutComposition": {"label": 1, "cn22": 1}
  }]
}""" % _zpl_json(RawZPL)

# A booking whose itemId entry carries no printId: the by-id fetch falls
# back to keying by the item id.
CustomsBookingNoPrintIdResponse = """{
  "bookingResponse": {
    "bookingId": "BOOK-UX4",
    "idInformation": [{
      "status": "OK",
      "ids": [
        {"idType": "itemId", "value": "00373500454541020957"},
        {"idType": "shipmentId", "value": "ORDER-7788"}
      ],
      "urls": [
        {"type": "TRACKING", "url": "https://tracking.postnord.com/se/?id=00373500454541020957"}
      ],
      "errorResponse": null
    }]
  },
  "labelPrintout": [{
    "printout": {"type": "LABEL", "labelFormat": "PDF", "encoding": "base64", "data": "JVBERi0xLjQK"},
    "printoutComposition": {"label": 1, "cn22": 1}
  }]
}"""

# A booking that allocated no item ids (inline fault, no label): the by-id
# customs fetch has no target and is skipped.
CustomsBookingNoIdsResponse = """{
  "bookingResponse": {
    "bookingId": "BOOK-UX3",
    "idInformation": [{
      "status": "ERROR",
      "ids": null,
      "urls": null,
      "errorResponse": {
        "compositeFault": {
          "faults": [
            {
              "explanationText": "customs declaration totalValue is mandatory",
              "faultCode": "CUSTOMS_VALIDATION"
            }
          ]
        }
      }
    }]
  }
}"""

# Parcel bookings with customsInvoice compose the invoice with the label
# (sandbox 2026-09-25: printoutComposition {label: 1, customsInvoice: 1}).
CustomsInvoiceBookingResponse = CustomsBookingResponse.replace(
    '"cn22": 1', '"customsInvoice": 1'
)
CustomsInvoiceBookingZPLResponse = CustomsBookingZPLResponse.replace(
    '"cn22": 1', '"customsInvoice": 1'
)

# By-id onlyCustomsDeclarations responses: a top-level labelPrintout array
# (per the /v3/labels/ids swagger) whose entries carry the composed kind.
CustomsPDFData = "Q04yMiBQREYgREFUQQ=="

# The itemIds members follow the /v3/labels/ids swagger itemIds_inner shape
# (one object per requested id with its own status), not a bare string array;
# reference is the references object, echoing the booking id with type IL
# (live by-id capture, 2026-09-21).
CustomsPrintoutsResponse = """[{
  "itemIds": [{
    "itemIds": "00373500454541020957",
    "status": "OK",
    "reference": {
      "item": [],
      "shipment": [{"referenceNo": "BOOK-UX1", "referenceType": "IL"}]
    }
  }],
  "printoutComposition": {"cn22": 1},
  "printout": {"labelFormat": "PDF", "encoding": "base64", "data": "%s"}
}]""" % CustomsPDFData

CustomsRawZPL = "^XA\n^FO50,50\n^FDCN22\n^FS\n^XZ"

# No labelFormat: the document format falls back to the requested label
# type, mirroring the observed /labels/zpl booking behavior.
CustomsPrintoutsZPLResponse = """[{
  "itemIds": [{"itemIds": "00373500454541020957", "status": "OK"}],
  "printoutComposition": {"cn22": 1},
  "printout": {"encoding": "none", "data": "%s"}
}]""" % _zpl_json(CustomsRawZPL)

# Composition keys in non-alphabetical serialization order: the joined
# document category must not depend on that order.
CustomsPrintoutsMultiKindResponse = """[{
  "itemIds": [{"itemIds": "00373500454541020957", "status": "OK"}],
  "printoutComposition": {"customsInvoice": 1, "cn22": 1},
  "printout": {"labelFormat": "PDF", "encoding": "base64", "data": "%s"}
}]""" % CustomsPDFData

# No printoutComposition: the standardized customs-declaration category
# fallback applies.
CustomsPrintoutsNoCompositionResponse = """[{
  "itemIds": [{"itemIds": "00373500454541020957", "status": "OK"}],
  "printout": {"labelFormat": "PDF", "encoding": "base64", "data": "%s"}
}]""" % CustomsPDFData

# Live capture (atapi2, 2026-09-21): the by-id fetch for a booked export
# letter returned an HTTP error status whose body still parses as a
# labelPrintout array, the failure reported per id inside itemIds —
# [{"itemIds":[{"itemIds":"UX304478474SE","status":"FAIL",
# "errorResponse":{"message":"id not found"}}]}] — with no printout at all.
# The requested id is replayed here as the booking's allocated item id.
CustomsPrintoutsIdNotFoundResponse = """[{
  "itemIds": [
    {
      "itemIds": "00373500454541020957",
      "status": "FAIL",
      "errorResponse": {"message": "id not found"}
    }
  ]
}]"""

# Mixed by-id outcome: one entry failed (no printout), another produced a
# data-bearing printout — the document attaches and the failure surfaces.
CustomsPrintoutsPartialFailureResponse = """[{
  "itemIds": [
    {
      "itemIds": "00373500454541020957",
      "status": "FAIL",
      "errorResponse": {"message": "id not found"}
    }
  ]
}, {
  "itemIds": [{"itemIds": "00373500454541999999", "status": "OK"}],
  "printoutComposition": {"cn22": 1},
  "printout": {"labelFormat": "PDF", "encoding": "base64", "data": "%s"}
}]""" % CustomsPDFData

# Live capture (2026-09-21): before a declaration exists, the printId-keyed
# onlyCustomsDeclarations fetch returns OK members, no errorResponse, no
# printout data, and an all-zero printoutComposition.
CustomsPrintoutsEmptyResponse = """[{
  "itemIds": [{"itemIds": "00373500454541020957", "status": "OK"}],
  "printoutComposition": {
    "label": 0,
    "cn22": 0,
    "cn23": 0,
    "customsInvoice": 0,
    "securityDeclarations": 0,
    "loadList": 0,
    "dpc": 0,
    "dangerousGoods": 0,
    "fraktsedel": 0,
    "routingDocument": 0,
    "datametrixbarcode": 0
  }
}]"""

CustomsRetrievalErrorResponse = """{
  "message": "Unable to print labels for the requested IDs",
  "compositeFault": {
    "faults": [
      {
        "explanationText": "No EDI found for item id 00373500454541020957",
        "faultCode": "EDI_NOT_FOUND"
      }
    ]
  }
}"""

# Non-JSON body (an intermediary's HTML error page) from the by-id fetch.
UnreadableBodyResponse = "<html>502 Bad Gateway</html>"

CustomsInvoicePrintoutsResponse = CustomsPrintoutsResponse.replace(
    '"cn22": 1', '"customsInvoice": 1'
)
CustomsInvoicePrintoutsZPLResponse = CustomsPrintoutsZPLResponse.replace(
    '"cn22": 1', '"customsInvoice": 1'
)
