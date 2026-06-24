"""PostNord carrier shipment tests."""

import unittest
from unittest.mock import patch, ANY
from .fixture import gateway

import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models


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

    def test_create_shipment(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(self.ShipmentRequest).from_(gateway)
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/edi/labels/pdf?apikey=TEST_API_KEY",
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
}

ShipmentCancelPayload = {
    "shipment_identifier": "SHIP-0001",
}

ShipmentRequest = {
    "application": {"name": "Karrio", "applicationId": "2458"},
    "messageDate": ANY,
    "testIndicator": True,
    "updateIndicator": "Original",
    "shipment": [
        {
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
    "application": {"name": "Karrio", "applicationId": "2458"},
    "messageDate": ANY,
    "testIndicator": True,
    "updateIndicator": "Deletion",
    "shipment": [
        {"shipmentIdentification": {"shipmentId": "SHIP-0001"}},
    ],
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
  "errorResponse": {
    "message": "Unable to create shipment",
    "compositeFault": {
      "faults": [{
        "explanationText": "Invalid consignee",
        "faultCode": "PNCS-400",
        "paramValues": [{"param": "postalCode", "value": "00000"}]
      }]
    }
  }
}"""

ParsedShipmentResponse = [
    {
        "carrier_id": "postnord",
        "carrier_name": "postnord",
        "tracking_number": "00373500454541020957",
        "shipment_identifier": "SHIP-0001",
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
    {
        "carrier_id": "postnord",
        "carrier_name": "postnord",
        "operation": "Cancel Shipment",
        "success": True,
    },
    [],
]

ParsedErrorResponse = [
    None,
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "code": "PNCS-400",
            "message": "Invalid consignee",
            "details": {"params": {"postalCode": "00000"}},
        }
    ],
]
