"""PostNord carrier manifest tests."""

import unittest
from unittest.mock import patch, ANY
from .fixture import gateway

import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models


class TestPostNordManifest(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.ManifestRequest = models.ManifestRequest(**ManifestPayload)

    def test_create_manifest_request(self):
        request = gateway.mapper.create_manifest_request(self.ManifestRequest)
        self.assertEqual(lib.to_dict(request.serialize()), ManifestRequest)

    def test_create_manifest(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Manifest.create(self.ManifestRequest).from_(gateway)
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/pickups?apikey=TEST_API_KEY",
            )

    def test_parse_manifest_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ManifestResponse
            parsed_response = (
                karrio.Manifest.create(self.ManifestRequest).from_(gateway).parse()
            )
            self.assertListEqual(
                lib.to_dict(parsed_response), ParsedManifestResponse
            )

    def test_parse_error_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ErrorResponse
            parsed_response = (
                karrio.Manifest.create(self.ManifestRequest).from_(gateway).parse()
            )
            self.assertListEqual(lib.to_dict(parsed_response), ParsedErrorResponse)


if __name__ == "__main__":
    unittest.main()


ManifestPayload = {
    "shipment_identifiers": ["SHIP-0001", "SHIP-0002"],
    "address": {
        "address_line1": "Sandhamnsgatan 61",
        "city": "Stockholm",
        "postal_code": "11528",
        "country_code": "SE",
        "person_name": "John Sender",
        "company_name": "ACME Sender AB",
        "phone_number": "+46701234567",
        "email": "sender@example.com",
    },
    "options": {
        "earliest_pickup_date": "2026-06-25T08:00:00",
        "latest_pickup_date": "2026-06-25T16:00:00",
    },
}

ManifestRequest = {
    "application": {"name": "Karrio", "applicationId": 2458},
    "messageDate": ANY,
    "testIndicator": True,
    "updateIndicator": "Original",
    "shipment": [
        {
            "dateAndTimes": {
                "earliestPickupDate": "2026-06-25T08:00:00",
                "latestPickupDate": "2026-06-25T16:00:00",
            },
            "service": {"basicServiceCode": "20"},
            "goodsItem": [
                {
                    "items": [
                        {"itemIdentification": {"itemId": "SHIP-0001"}},
                        {"itemIdentification": {"itemId": "SHIP-0002"}},
                    ],
                }
            ],
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
                            "name": "John Sender",
                            "companyName": "ACME Sender AB",
                        },
                        "address": {
                            "streets": ["Sandhamnsgatan 61"],
                            "postalCode": "11528",
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
                "pickupParty": {
                    "party": {
                        "nameIdentification": {
                            "name": "John Sender",
                            "companyName": "ACME Sender AB",
                        },
                        "address": {
                            "streets": ["Sandhamnsgatan 61"],
                            "postalCode": "11528",
                            "city": "Stockholm",
                            "countryCode": "SE",
                        },
                        "contact": {
                            "contactName": "John Sender",
                            "emailAddress": "sender@example.com",
                            "phoneNo": "+46701234567",
                            "smsNo": "+46701234567",
                        },
                    }
                },
            },
        }
    ],
}

ManifestResponse = """{
  "bookingId": "PICKUP-555",
  "references": {
    "shipment": [
      {"referenceType": "IL", "referenceNo": "ILPN0001"}
    ]
  },
  "idInformation": [
    {"status": "OK", "ids": [{"idType": "pickupId", "value": "PU-1"}]}
  ]
}"""

ErrorResponse = """{
  "errorResponse": {
    "message": "Unable to book pickup",
    "compositeFault": {
      "faults": [{
        "explanationText": "No pickup slot available",
        "faultCode": "PNCS-409"
      }]
    }
  }
}"""

ParsedManifestResponse = [
    {
        "carrier_id": "postnord",
        "carrier_name": "postnord",
        "doc": {},
        "meta": {
            "booking_id": "PICKUP-555",
            "pickup_ids": ["PU-1"],
            "references": ["ILPN0001"],
        },
    },
    [],
]

ParsedErrorResponse = [
    None,
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "code": "PNCS-409",
            "message": "No pickup slot available",
            "details": {},
        }
    ],
]
