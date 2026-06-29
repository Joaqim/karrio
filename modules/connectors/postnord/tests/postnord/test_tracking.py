"""PostNord carrier tracking tests (Track & Trace v7)."""

import unittest
from unittest.mock import patch, ANY
from .fixture import gateway

import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models


class TestPostNordTracking(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.TrackingRequest = models.TrackingRequest(**TrackingPayload)

    def test_create_tracking_request(self):
        request = gateway.mapper.create_tracking_request(self.TrackingRequest)
        self.assertEqual(lib.to_dict(request.serialize()), TrackingRequest)

    def test_get_tracking(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Tracking.fetch(self.TrackingRequest).from_(gateway)
            self.assertEqual(
                mock.call_args[1]["url"],
                f"{gateway.settings.server_url}/rest/shipment/v7/trackandtrace/id/00373500454541020957/public?apikey=TEST_API_KEY&locale=en",
            )

    def test_parse_tracking_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = TrackingResponse
            parsed_response = (
                karrio.Tracking.fetch(self.TrackingRequest).from_(gateway).parse()
            )
            self.assertListEqual(
                lib.to_dict(parsed_response), ParsedTrackingResponse
            )

    def test_parse_tracking_response_in_transit(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = InTransitResponse
            parsed_response = (
                karrio.Tracking.fetch(self.TrackingRequest).from_(gateway).parse()
            )
            self.assertListEqual(
                lib.to_dict(parsed_response), ParsedInTransitResponse
            )

    def test_parse_error_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ErrorResponse
            parsed_response = (
                karrio.Tracking.fetch(self.TrackingRequest).from_(gateway).parse()
            )
            self.assertListEqual(lib.to_dict(parsed_response), ParsedErrorResponse)


if __name__ == "__main__":
    unittest.main()


TrackingPayload = {
    "tracking_numbers": ["00373500454541020957"],
}

TrackingRequest = [
    {
        "id": "00373500454541020957",
        "locale": "en",
    }
]

TrackingResponse = """{
  "TrackingInformationResponse": {
    "shipments": [
      {
        "shipmentId": "00373500454541020957",
        "assessedNumberOfItems": 1,
        "estimatedTimeOfArrival": "2026-06-25T12:00:00",
        "deliveryDate": "2026-06-25T15:42:00",
        "status": "DELIVERED",
        "items": [
          {
            "itemId": "00373500454541020957",
            "status": "DELIVERED",
            "eventStatus": "DELIVERED",
            "estimatedTimeOfArrival": "2026-06-25T12:00:00",
            "deliveryDate": "2026-06-25T15:42:00",
            "acceptor": {"name": "ANNA SVENSSON"},
            "signature": "ref-123",
            "events": [
              {
                "eventTime": "2026-06-24T08:15:00",
                "eventCode": "C01",
                "eventDescription": "The shipment item has been registered",
                "status": "CREATED",
                "location": {
                  "name": "PostNord Terminal",
                  "city": "Stockholm",
                  "postcode": "11122",
                  "countryCode": "SE"
                }
              },
              {
                "eventTime": "2026-06-25T15:42:00",
                "eventCode": "C20",
                "eventDescription": "The shipment item has been delivered",
                "status": "DELIVERED",
                "location": {
                  "name": "Hemleverans",
                  "city": "Stockholm",
                  "postcode": "11455",
                  "countryCode": "SE"
                }
              }
            ]
          }
        ]
      }
    ]
  }
}"""

InTransitResponse = """{
  "TrackingInformationResponse": {
    "shipments": [
      {
        "shipmentId": "00373500454541020957",
        "assessedNumberOfItems": 1,
        "estimatedTimeOfArrival": "2026-06-26T12:00:00",
        "status": "EN_ROUTE",
        "items": [
          {
            "itemId": "00373500454541020957",
            "status": "EN_ROUTE",
            "eventStatus": "EN_ROUTE",
            "estimatedTimeOfArrival": "2026-06-26T12:00:00",
            "events": [
              {
                "eventTime": "2026-06-24T08:15:00",
                "eventCode": "C01",
                "eventDescription": "The shipment item has been registered",
                "status": "CREATED",
                "location": {
                  "name": "PostNord Terminal",
                  "city": "Stockholm",
                  "postcode": "11122",
                  "countryCode": "SE"
                }
              },
              {
                "eventTime": "2026-06-25T06:30:00",
                "eventCode": "C10",
                "eventDescription": "The shipment item is en route",
                "status": "EN_ROUTE",
                "location": {
                  "name": "PostNord Terminal",
                  "city": "Goteborg",
                  "postcode": "40010",
                  "countryCode": "SE"
                }
              }
            ]
          }
        ]
      }
    ]
  }
}"""

ErrorResponse = """{
  "error": {
    "status_code": 403,
    "error_type": "Forbidden",
    "message": "Invalid API Key"
  }
}"""

ParsedTrackingResponse = [
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "tracking_number": "00373500454541020957",
            "delivered": True,
            "status": "delivered",
            "estimated_delivery": "2026-06-25",
            "events": [
                {
                    "date": "2026-06-24",
                    "time": "08:15 AM",
                    "code": "C01",
                    "description": "The shipment item has been registered",
                    "location": "PostNord Terminal, Stockholm 11122, SE",
                },
                {
                    "date": "2026-06-25",
                    "time": "15:42 PM",
                    "code": "C20",
                    "description": "The shipment item has been delivered",
                    "location": "Hemleverans, Stockholm 11455, SE",
                },
            ],
            "info": {
                "carrier_tracking_link": "https://tracking.postnord.com/se/?id=00373500454541020957",
                "shipment_package_count": 1,
                "signed_by": "ANNA SVENSSON",
            },
            "meta": {
                "tracking_url": "https://tracking.postnord.com/se/?id=00373500454541020957",
            },
        }
    ],
    [],
]

ParsedInTransitResponse = [
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "tracking_number": "00373500454541020957",
            "delivered": False,
            "status": "in_transit",
            "estimated_delivery": "2026-06-26",
            "events": [
                {
                    "date": "2026-06-24",
                    "time": "08:15 AM",
                    "code": "C01",
                    "description": "The shipment item has been registered",
                    "location": "PostNord Terminal, Stockholm 11122, SE",
                },
                {
                    "date": "2026-06-25",
                    "time": "06:30 AM",
                    "code": "C10",
                    "description": "The shipment item is en route",
                    "location": "PostNord Terminal, Goteborg 40010, SE",
                },
            ],
            "info": {
                "carrier_tracking_link": "https://tracking.postnord.com/se/?id=00373500454541020957",
                "shipment_package_count": 1,
            },
            "meta": {
                "tracking_url": "https://tracking.postnord.com/se/?id=00373500454541020957",
            },
        }
    ],
    [],
]

ParsedErrorResponse = [
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "tracking_number": "00373500454541020957",
            "delivered": False,
            "status": "in_transit",
            "info": {
                "carrier_tracking_link": "https://tracking.postnord.com/se/?id=00373500454541020957",
            },
            "meta": {
                "tracking_url": "https://tracking.postnord.com/se/?id=00373500454541020957",
            },
        }
    ],
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "code": "Forbidden",
            "level": "error",
            "message": "Invalid API Key: the PostNord API key is not authorized for this service/product",
            "details": {
                "tracking_number": "00373500454541020957",
                "status_code": 403,
            },
        }
    ],
]
