"""PostNord service points tests (connector-local capability)."""

import unittest
from unittest.mock import patch
from .fixture import gateway

import karrio.lib as lib
import karrio.providers.postnord.service_points as service_points


class TestPostNordServicePoints(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_create_service_points_request(self):
        request = service_points.service_points_request(SearchParams, gateway.settings)
        self.assertEqual(lib.to_dict(request.serialize()), ServicePointsQuery)
        self.assertEqual(
            request.ctx["path"],
            "/rest/businesslocation/v5/servicepoints/nearest/byaddress",
        )

    def test_create_service_points_by_coordinates_request(self):
        request = service_points.service_points_request(CoordinateParams, gateway.settings)
        self.assertEqual(lib.to_dict(request.serialize()), CoordinateQuery)
        self.assertEqual(
            request.ctx["path"],
            "/rest/businesslocation/v5/servicepoints/nearest/bycoordinates",
        )

    def test_find_service_points(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            request = service_points.service_points_request(SearchParams, gateway.settings)
            gateway.proxy.find_service_points(request)
            url = mock.call_args.kwargs["url"]
        self.assertIn("/v5/servicepoints/nearest/byaddress", url)
        self.assertIn("apikey=TEST_API_KEY", url)
        self.assertIn("countryCode=SE", url)
        self.assertIn("postalCode=11528", url)
        self.assertEqual(mock.call_args.kwargs["method"], "GET")

    def test_parse_service_points_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ServicePointsResponse
            request = service_points.service_points_request(SearchParams, gateway.settings)
            parsed = service_points.parse_service_points_response(
                gateway.proxy.find_service_points(request), gateway.settings
            )
            self.assertListEqual(lib.to_dict(parsed), ParsedServicePoints)

    def test_parse_error_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ErrorResponse
            request = service_points.service_points_request(SearchParams, gateway.settings)
            parsed = service_points.parse_service_points_response(
                gateway.proxy.find_service_points(request), gateway.settings
            )
            self.assertListEqual(lib.to_dict(parsed), ParsedErrorResponse)


if __name__ == "__main__":
    unittest.main()


SearchParams = {
    "country_code": "SE",
    "postal_code": "11528",
    "number_of_points": 3,
    "type_id": "25",
    "context": "optionalservicepoint",
}

CoordinateParams = {
    "country_code": "SE",
    "northing": 59.3293,
    "easting": 18.0686,
    "number_of_points": 2,
}

ServicePointsQuery = {
    "returnType": "json",
    "countryCode": "SE",
    "numberOfServicePoints": 3,
    "typeId": "25",
    "context": "optionalservicepoint",
    "postalCode": "11528",
}

CoordinateQuery = {
    "returnType": "json",
    "countryCode": "SE",
    "numberOfServicePoints": 2,
    "northing": 59.3293,
    "easting": 18.0686,
}

ServicePointsResponse = """{
  "servicePointInformationResponse": {
    "servicePoints": [
      {
        "servicePointId": "1003369",
        "name": "ICA Supermarket City",
        "routeDistance": 412,
        "deliveryAddress": {
          "countryCode": "SE",
          "city": "STOCKHOLM",
          "streetName": "Kungsgatan",
          "streetNumber": "12",
          "postalCode": "11135"
        },
        "coordinates": [
          {
            "countryCode": "SE",
            "northing": 59.33459,
            "easting": 18.06324,
            "srId": "EPSG:4326"
          }
        ],
        "openingHours": {
          "postalServices": [
            {"openDay": "MONDAY", "openTime": "08:00", "closeTime": "22:00"}
          ]
        },
        "type": {
          "groupTypeId": 25,
          "groupTypeName": "Service point",
          "typeId": 25,
          "typeName": "Servicepoint"
        }
      },
      {
        "servicePointId": "1003370",
        "name": "Pressbyran Central",
        "routeDistance": 850,
        "visitingAddress": {
          "countryCode": "SE",
          "city": "STOCKHOLM",
          "streetName": "Vasagatan",
          "postalCode": "11120"
        },
        "coordinates": [],
        "type": {
          "typeId": 2,
          "typeName": "Parcel Box Location"
        }
      }
    ]
  }
}"""

ParsedServicePoints = [
    [
        {
            "id": "1003369",
            "name": "ICA Supermarket City",
            "type": "Servicepoint",
            "address": {
                "address_line1": "Kungsgatan 12",
                "city": "STOCKHOLM",
                "postal_code": "11135",
                "country_code": "SE",
            },
            "coordinates": {
                "northing": 59.33459,
                "easting": 18.06324,
                "sr_id": "EPSG:4326",
            },
            "opening_hours": {
                "postalServices": [
                    {"openDay": "MONDAY", "openTime": "08:00", "closeTime": "22:00"}
                ]
            },
            "distance": 412,
        },
        {
            "id": "1003370",
            "name": "Pressbyran Central",
            "type": "Parcel Box Location",
            "address": {
                "address_line1": "Vasagatan",
                "city": "STOCKHOLM",
                "postal_code": "11120",
                "country_code": "SE",
            },
            "distance": 850,
        },
    ],
    [],
]

ErrorResponse = """{
  "servicePointInformationResponse": {
    "compositeFault": {
      "faults": [
        {
          "explanationText": "Missing parameter",
          "faultCode": "API-005",
          "paramValues": [
            {"param": "countryCode", "value": "null"}
          ]
        }
      ]
    }
  }
}"""

ParsedErrorResponse = [
    [],
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "code": "API-005",
            "message": "Missing parameter",
            "details": {"params": {"countryCode": "null"}},
        }
    ],
]
