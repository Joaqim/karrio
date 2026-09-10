"""DHL Freight service point locator tests (connector-local capability).

The two fixture points were captured live from the sandbox on 2026-09-10
(POST /servicepoint/findnearestservicepoints, Warszawa 00-251: one
unfiltered call returning parcelshops, one ``locationTypes: ["locker"]``
call returning parcelstations). ``ServicePointsResponse`` merges one point
from each capture, trimmed to the fields the normalizer consumes; all
point values are verbatim from the captures. ``ErrorResponse`` is
constructed to the spec's in-band ``status``/``errorMessage`` shape (the
endpoint declares no 4xx responses).
"""

import unittest
from unittest.mock import patch
from .fixture import gateway

import karrio.lib as lib
import karrio.providers.dhl_freight_sweden.service_points as service_points


class TestDHLFreightSwedenServicePoints(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_create_service_points_request(self):
        request = service_points.service_points_request(
            ServicePointsParams, gateway.settings
        )
        self.assertEqual(lib.to_dict(request.serialize()), ServicePointsRequest)

    def test_find_service_points(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.return_value = "{}"
            request = service_points.service_points_request(
                ServicePointsParams, gateway.settings
            )
            gateway.proxy.find_service_points(request)
            url = mock.call_args.kwargs["url"]
        self.assertIn(
            "/servicepointlocatorapi/v1/servicepoint/findnearestservicepoints", url
        )
        self.assertEqual(mock.call_args.kwargs["method"], "POST")
        self.assertEqual(
            mock.call_args.kwargs["headers"],
            {
                "Content-Type": "application/json",
                "client-key": "TEST_CLIENT_KEY",
            },
        )
        self.assertEqual(
            lib.to_dict(mock.call_args.kwargs["data"]), ServicePointsRequest
        )

    def test_parse_service_points_response(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.return_value = ServicePointsResponse
            request = service_points.service_points_request(
                ServicePointsParams, gateway.settings
            )
            parsed = service_points.parse_service_points_response(
                gateway.proxy.find_service_points(request), gateway.settings
            )
            self.assertListEqual(lib.to_dict(parsed), ParsedServicePoints)

    def test_parse_service_points_error(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.return_value = ErrorResponse
            request = service_points.service_points_request(
                ServicePointsParams, gateway.settings
            )
            parsed = service_points.parse_service_points_response(
                gateway.proxy.find_service_points(request), gateway.settings
            )
            self.assertListEqual(lib.to_dict(parsed), ParsedErrorResponse)


ServicePointsParams = {
    "address": {
        "street": "Nowogrodzka",
        "street_number": "31",
        "city": "Warszawa",
        "postal_code": "00-251",
        "country_code": "PL",
    },
    "location_types": ["locker"],
    "max_items": 2,
    "distance": {"value": 10, "unit": "km"},
    "piece": {"length": 60, "width": 40, "height": 40, "weight": 25},
}

ServicePointsRequest = {
    "address": {
        "street": "Nowogrodzka",
        "streetNumber": "31",
        "cityName": "Warszawa",
        "postalCode": "00-251",
        "countryCode": "PL",
    },
    "locationTypes": ["locker"],
    "maxNumberOfItems": 2,
    "distance": 10,
    "distanceUnit": "km",
    "piece": {"width": 40, "height": 40, "length": 60, "weight": 25},
}

ServicePointsResponse = """{
  "status": "OK",
  "servicePoints": [
    {
      "id": "101",
      "servicePointId": "8005-PL-4516440",
      "street": "SENATORSKA 2",
      "name": "DHL Parcelshop",
      "shopName": "ŻABKA",
      "cityName": "WARSZAWA",
      "postalCode": "00-075",
      "countryCode": "PL",
      "distance": 0.06,
      "distanceUnit": "km",
      "locationType": "servicepoint",
      "serviceTypes": [
        "parcel:pick-up",
        "cash-on-delivery",
        "parcel:drop-off"
      ],
      "latitude": 52.246463,
      "longitude": 21.012219
    },
    {
      "id": "501",
      "servicePointId": "8005-PL-4599334",
      "street": "Plac Bankowy 2",
      "name": "DHL Parcelstation",
      "shopName": "Automat DHL BOX 24/7",
      "cityName": "Warszawa",
      "postalCode": "00-095",
      "countryCode": "PL",
      "distance": 0.66,
      "distanceUnit": "km",
      "locationType": "locker",
      "serviceTypes": [
        "parcel:drop-off-unregistered",
        "cash-on-delivery",
        "parcel:pick-up-unregistered"
      ],
      "latitude": 52.244046,
      "longitude": 21.00276
    }
  ]
}"""

ParsedServicePoints = [
    [
        {
            "id": "101",
            "service_point_id": "8005-PL-4516440",
            "name": "DHL Parcelshop",
            "shop_name": "ŻABKA",
            "type": "servicepoint",
            "address": {
                "street": "SENATORSKA 2",
                "city": "WARSZAWA",
                "postal_code": "00-075",
                "country_code": "PL",
            },
            "coordinates": {"latitude": 52.246463, "longitude": 21.012219},
            "distance": 0.06,
            "distance_unit": "km",
            "service_types": [
                "parcel:pick-up",
                "cash-on-delivery",
                "parcel:drop-off",
            ],
        },
        {
            "id": "501",
            "service_point_id": "8005-PL-4599334",
            "name": "DHL Parcelstation",
            "shop_name": "Automat DHL BOX 24/7",
            "type": "locker",
            "address": {
                "street": "Plac Bankowy 2",
                "city": "Warszawa",
                "postal_code": "00-095",
                "country_code": "PL",
            },
            "coordinates": {"latitude": 52.244046, "longitude": 21.00276},
            "distance": 0.66,
            "distance_unit": "km",
            "service_types": [
                "parcel:drop-off-unregistered",
                "cash-on-delivery",
                "parcel:pick-up-unregistered",
            ],
        },
    ],
    [],
]

ErrorResponse = """{
  "status": "Error",
  "errorMessage": "No servicepoints found for the given address",
  "servicePoints": []
}"""

ParsedErrorResponse = [
    [],
    [
        {
            "carrier_id": "dhl_freight_sweden",
            "carrier_name": "dhl_freight_sweden",
            "code": "Error",
            "message": "No servicepoints found for the given address",
            "details": {},
        }
    ],
]


if __name__ == "__main__":
    unittest.main()
