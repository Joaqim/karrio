"""PostNord carrier pickup tests."""

import unittest
from unittest.mock import patch, ANY
from .fixture import gateway

import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models


class TestPostNordPickup(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.PickupRequest = models.PickupRequest(**PickupPayload)
        self.PickupByItemIdRequest = models.PickupRequest(**PickupByItemIdPayload)
        self.PickupCancelRequest = models.PickupCancelRequest(**PickupCancelPayload)

    def test_create_pickup_request(self):
        request = gateway.mapper.create_pickup_request(self.PickupRequest)
        self.assertEqual(lib.to_dict(request.serialize()), PickupRequest)

    def test_schedule_pickup(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Pickup.schedule(self.PickupRequest).from_(gateway)
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/pickups?apikey=TEST_API_KEY",
            )

    def test_parse_pickup_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = PickupResponse
            parsed_response = (
                karrio.Pickup.schedule(self.PickupRequest).from_(gateway).parse()
            )
            self.assertListEqual(lib.to_dict(parsed_response), ParsedPickupResponse)

    def test_parse_error_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ErrorResponse
            parsed_response = (
                karrio.Pickup.schedule(self.PickupRequest).from_(gateway).parse()
            )
            self.assertListEqual(lib.to_dict(parsed_response), ParsedErrorResponse)

    def test_create_pickup_by_item_id_request(self):
        request = gateway.mapper.create_pickup_request(self.PickupByItemIdRequest)
        self.assertEqual(lib.to_dict(request.serialize()), PickupByItemIdRequest)

    def test_schedule_pickup_by_item_id(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Pickup.schedule(self.PickupByItemIdRequest).from_(gateway)
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v3/pickups/ids?apikey=TEST_API_KEY",
            )

    def test_parse_pickup_by_item_id_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = PickupResponse
            parsed_response = (
                karrio.Pickup.schedule(self.PickupByItemIdRequest).from_(gateway).parse()
            )
            self.assertListEqual(lib.to_dict(parsed_response), ParsedPickupResponse)

    def test_parse_pickup_by_item_id_error_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = PickupByItemIdErrorResponse
            parsed_response = (
                karrio.Pickup.schedule(self.PickupByItemIdRequest).from_(gateway).parse()
            )
            self.assertListEqual(
                lib.to_dict(parsed_response), ParsedPickupByItemIdErrorResponse
            )

    def test_create_pickup_request_ignores_item_ids_outside_account_country(self):
        for country_code in ["DK", "NO"]:
            with self.subTest(country_code=country_code):
                payload = {
                    **PickupByItemIdPayload,
                    "address": {**PickupByItemIdPayload["address"], "country_code": country_code},
                }
                request = gateway.mapper.create_pickup_request(
                    models.PickupRequest(**payload)
                )
                serialized = lib.to_dict(request.serialize())
                self.assertEqual(
                    serialized["shipment"][0]["goodsItem"],
                    [{"items": [{"itemIdentification": {"itemId": "0"}}]}],
                )

    def test_cancel_pickup_unsupported(self):
        # PostNord has no pickup cancel endpoint: cancellation issues no HTTP
        # request and surfaces an explicit "not_supported" Message.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            parsed_response = (
                karrio.Pickup.cancel(self.PickupCancelRequest).from_(gateway).parse()
            )
            mock.assert_not_called()
            self.assertListEqual(
                lib.to_dict(parsed_response), ParsedCancelPickupResponse
            )


if __name__ == "__main__":
    unittest.main()


PickupPayload = {
    "pickup_date": "2026-06-25",
    "ready_time": "08:00:00",
    "closing_time": "16:00:00",
    "instruction": "Pick up at loading dock",
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
}

PickupByItemIdPayload = {
    **PickupPayload,
    "options": {
        "shipment_identifiers": ["SHIP-0001", "SHIP-0002"],
        "tracking_numbers": ["00370712345678901234", "00370712345678905678"],
    },
}

PickupCancelPayload = {
    "confirmation_number": "PICKUP-555",
}

PickupRequest = {
    "application": {"name": "Karrio", "applicationId": 2458},
    "messageDate": ANY,
    "messageFunction": "PickupBooking",
    "testIndicator": True,
    "updateIndicator": "Original",
    "shipment": [
        {
            "dateAndTimes": {
                "earliestPickupDate": "2026-06-25T08:00:00",
                "latestPickupDate": "2026-06-25T16:00:00",
            },
            "service": {"basicServiceCode": "20"},
            "freeText": [
                {"usageCode": "ZHD", "text": "Pick up at loading dock"}
            ],
            "goodsItem": [
                {
                    "items": [{"itemIdentification": {"itemId": "0"}}],
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

PickupByItemIdRequest = [
    {
        "itemId": "00370712345678901234",
        "earliestPickupDate": "2026-06-25T08:00:00",
        "latestPickupDate": "2026-06-25T16:00:00",
    },
    {
        "itemId": "00370712345678905678",
        "earliestPickupDate": "2026-06-25T08:00:00",
        "latestPickupDate": "2026-06-25T16:00:00",
    },
]

PickupResponse = """{
  "bookingId": "PICKUP-555",
  "idInformation": [
    {
      "status": "OK",
      "references": {
        "shipment": [
          {"referenceType": "IL", "referenceNo": "ILPN0001"}
        ]
      },
      "ids": [{"idType": "pickupId", "value": "PU-1"}]
    }
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

PickupByItemIdErrorResponse = """{
  "message": "General client indata error",
  "compositeFault": {
    "faults": [
      {"explanationText": "Edi not found for item Id: 00370712345678901234"}
    ]
  }
}"""

ParsedPickupResponse = [
    {
        "carrier_id": "postnord",
        "carrier_name": "postnord",
        "confirmation_number": "PICKUP-555",
        "id": "PU-1",
        "meta": {
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

ParsedPickupByItemIdErrorResponse = [
    None,
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "message": "Edi not found for item Id: 00370712345678901234",
            "details": {},
        }
    ],
]

ParsedCancelPickupResponse = [
    None,
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "code": "not_supported",
            "message": "PostNord has no pickup cancel endpoint; pickup bookings support only 'Original'.",
        }
    ],
]
