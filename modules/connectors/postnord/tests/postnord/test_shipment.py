"""PostNord carrier shipment tests."""

import base64
import unittest
from unittest.mock import patch, ANY

import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models

from .fixture import gateway, gateway_small_label, gateway_zpl_label, gateway_with_language


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
        # inline fault surfaced as a message alongside them (PRD edge case).
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
        # No label_type anywhere: PDF endpoint, as before (exact URL).
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
