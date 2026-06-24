"""PostNord carrier tracking tests."""

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
                f"{gateway.settings.server_url}/rest/links/v1/tracking/se/00373500454541020957?apikey=TEST_API_KEY&language=en",
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
        "country": "se",
        "id": "00373500454541020957",
        "language": "en",
    }
]

TrackingResponse = """{
  "url": "https://tracking.postnord.com/se/?id=00373500454541020957"
}"""

ErrorResponse = """{
  "faults": [
    {"explanationText": "Identifier not found", "faultCode": "PNCS-404"}
  ]
}"""

ParsedTrackingResponse = [
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
    [],
]

ParsedErrorResponse = [
    [],
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "code": "PNCS-404",
            "message": "Identifier not found",
            "details": {"tracking_number": "00373500454541020957"},
        }
    ],
]
