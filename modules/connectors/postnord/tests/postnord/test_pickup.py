"""PostNord carrier pickup tests."""

import unittest
import uuid
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
        serialized = lib.to_dict(request.serialize())
        self.assertEqual(serialized, PickupRequest)
        self.assertEqual(uuid.UUID(serialized["messageId"]).version, 4)

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

    def test_parse_pickup_response_without_identifying_references(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = PickupWindowOnlyResponse
            parsed_response = (
                karrio.Pickup.schedule(self.PickupRequest).from_(gateway).parse()
            )
            self.assertListEqual(
                lib.to_dict(parsed_response), ParsedPickupWindowOnlyResponse
            )

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
        for country_code in ["DK", "FI"]:
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
                    [
                        {
                            "packageTypeCode": "PC",
                            "items": [{"itemIdentification": {"itemId": "0"}}],
                        }
                    ],
                )

    def test_create_pickup_request_collection_request_service_override(self):
        request = gateway.mapper.create_pickup_request(
            models.PickupRequest(**{**PickupPayload, "options": {"service": "CR"}})
        )
        self.assertEqual(
            lib.to_dict(request.serialize())["shipment"][0]["service"],
            {"basicServiceCode": "CR"},
        )

    def test_schedule_pickup_outside_nordic_pickup_countries_rejected(self):
        payload = {
            **PickupPayload,
            "address": {**PickupPayload["address"], "country_code": "NO"},
        }
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            parsed_response = (
                karrio.Pickup.schedule(models.PickupRequest(**payload))
                .from_(gateway)
                .parse()
            )
            mock.assert_not_called()
        self.assertListEqual(
            lib.to_dict(parsed_response), ParsedPickupCountryErrorResponse
        )

    def test_schedule_pickup_unknown_service_rejected(self):
        payload = {**PickupPayload, "options": {"service": "20"}}
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            parsed_response = (
                karrio.Pickup.schedule(models.PickupRequest(**payload))
                .from_(gateway)
                .parse()
            )
            mock.assert_not_called()
        self.assertListEqual(
            lib.to_dict(parsed_response), ParsedPickupServiceErrorResponse
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
    "instruction": "Pickup instruction",
    "shipment_identifiers": ["SHIP-0001", "SHIP-0002"],
    "address": {
        "address_line1": "Testgatan 1",
        "city": "Stockholm",
        "postal_code": "11759",
        "country_code": "SE",
        "person_name": "Klaus Consignor",
        "company_name": "Consignor AB",
        "phone_number": "+467011111",
        "email": "me@orderingparty.com",
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
    "messageId": ANY,
    "testIndicator": True,
    "updateIndicator": "Original",
    "shipment": [
        {
            "dateAndTimes": {
                "earliestPickupDate": "2026-06-25T08:00:00",
                "latestPickupDate": "2026-06-25T16:00:00",
            },
            "service": {"basicServiceCode": "0"},
            "freeText": [
                {"usageCode": "ADS", "text": "Pickup instruction"}
            ],
            "goodsItem": [
                {
                    "packageTypeCode": "PC",
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
                            "name": "Klaus Consignor",
                            "companyName": "Consignor AB",
                        },
                        "address": {
                            "streets": ["Testgatan 1"],
                            "postalCode": "11759",
                            "city": "Stockholm",
                            "countryCode": "SE",
                        },
                        "contact": {
                            "contactName": "Klaus Consignor",
                            "emailAddress": "me@orderingparty.com",
                            "phoneNo": "+467011111",
                            "smsNo": "+467011111",
                        },
                    },
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

# Documented 201 of the "Book Pickups SE_Minimum requirements" example in
# PostNord's guide (https://guide.developer.postnord.com/, Shipment / Booking /
# Booking APIs v3 / Book Pickups).
PickupResponse = """{
  "bookingId": "3SBZN5EWG327PSQHXBYV5X4GLQLJMF",
  "idInformation": [
    {
      "status": "OK",
      "references": {
        "item": [
          {"referenceNo": "CR511599F", "referenceType": "ZGI"},
          {"referenceNo": "511599", "referenceType": "ZDI"}
        ],
        "shipment": [
          {"referenceNo": "customer referenceNo", "referenceType": "CU"},
          {"referenceType": "ZET", "referenceNo": "2021-06-22T08:00:00+02:00"},
          {"referenceType": "ZLT", "referenceNo": "2021-06-22T16:00:00+02:00"}
        ]
      },
      "ids": [{"idType": "pickupId", "value": "CR511599F"}],
      "urls": [
        {
          "type": "TRACKING",
          "url": "https://atapi2.postnord.com/rest/shipment/v5/trackandtrace/findByIdentifier.json?id=CR511599F&apikey=undefined"
        }
      ]
    }
  ]
}"""

# Shape of the sandbox's 201 to a domestic pickup booking (basicServiceCode 0)
# on 2026-10-13: only the pickup window as shipment references.
PickupWindowOnlyResponse = """{
  "bookingId": "ILPN0010L40WFRAAETQQOHAHWWWHHK",
  "idInformation": [
    {
      "status": "OK",
      "references": {
        "item": [{"referenceNo": "PB015606512T", "referenceType": "ZGI"}],
        "shipment": [
          {"referenceType": "ZET", "referenceNo": "2026-10-14T08:00:00+02:00"},
          {"referenceType": "ZLT", "referenceNo": "2026-10-14T16:00:00+02:00"}
        ]
      },
      "ids": [{"idType": "pickupId", "value": "PB015606512T"}],
      "urls": [
        {
          "type": "TRACKING",
          "url": "https://atmypickups.postnord.com/tracking/PB015606512T?lang=sv"
        }
      ]
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
        "confirmation_number": "3SBZN5EWG327PSQHXBYV5X4GLQLJMF",
        "id": "CR511599F",
        "meta": {
            "pickup_ids": ["CR511599F"],
            "references": ["customer referenceNo"],
        },
    },
    [],
]

ParsedPickupWindowOnlyResponse = [
    {
        "carrier_id": "postnord",
        "carrier_name": "postnord",
        "confirmation_number": "ILPN0010L40WFRAAETQQOHAHWWWHHK",
        "id": "PB015606512T",
        "meta": {"pickup_ids": ["PB015606512T"]},
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
            "details": {"summary": "Unable to book pickup"},
        }
    ],
]

ParsedPickupCountryErrorResponse = [
    None,
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "code": "SHIPPING_SDK_FIELD_ERROR",
            "message": ANY,
            "details": {
                "address.country_code": (
                    "PostNord pickups are booked from SE, FI or DK only; "
                    "a collection request from NO needs a consignee, which is "
                    "not supported"
                ),
            },
        }
    ],
]

ParsedPickupServiceErrorResponse = [
    None,
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "code": "SHIPPING_SDK_FIELD_ERROR",
            "message": ANY,
            "details": {
                "options.service": (
                    "PostNord pickup service must be 0 (pickup) or CR "
                    "(collection request), got 20"
                ),
            },
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

ParsedPickupByItemIdErrorResponse = [
    None,
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "message": "Edi not found for item Id: 00370712345678901234",
            "details": {"summary": "General client indata error"},
        }
    ],
]
