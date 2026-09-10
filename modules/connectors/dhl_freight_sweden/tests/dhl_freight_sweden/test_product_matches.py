"""DHL Freight product matches tests (connector-local capability).

``ProductMatchesResponse`` was captured live from the sandbox on 2026-09-10
(POST /productmatches, Consignor SE 11120 -> Consignee PL 00001, one 2.5 kg
piece) and is trimmed to the fields the normalizer consumes; all values are
verbatim from the capture. ``ProductMatchRequest`` is the exact body of that
call.
"""

import unittest
from unittest.mock import patch
from .fixture import gateway

import karrio.lib as lib
import karrio.core.errors as errors
import karrio.providers.dhl_freight_sweden.product_matches as product_matches


class TestDHLFreightSwedenProductMatches(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_create_product_matches_request(self):
        request = product_matches.product_matches_request(
            ProductMatchParams, gateway.settings
        )
        self.assertEqual(lib.to_dict(request.serialize()), ProductMatchRequest)

    def test_create_product_matches_missing_parties(self):
        with self.assertRaises(errors.ShippingSDKDetailedError) as context:
            product_matches.product_matches_request(
                MissingPartiesParams, gateway.settings
            )

        exception = context.exception
        self.assertEqual(exception.code, "SHIPPING_SDK_FIELD_ERROR")
        self.assertIn("Consignor", str(exception))
        self.assertIn("Consignee", str(exception))
        self.assertEqual(
            exception.details,
            {
                "recipient": dict(
                    code="required",
                    message="postal code and country code are required",
                )
            },
        )

    def test_find_product_matches(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.return_value = "[]"
            request = product_matches.product_matches_request(
                ProductMatchParams, gateway.settings
            )
            gateway.proxy.find_product_matches(request)
            url = mock.call_args.kwargs["url"]
        self.assertIn("/productapi/v1/productmatches", url)
        self.assertEqual(mock.call_args.kwargs["method"], "POST")
        self.assertEqual(
            mock.call_args.kwargs["headers"],
            {
                "Content-Type": "application/json",
                "client-key": "TEST_CLIENT_KEY",
            },
        )
        self.assertEqual(
            lib.to_dict(mock.call_args.kwargs["data"]), ProductMatchRequest
        )

    def test_parse_product_matches_response(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.return_value = ProductMatchesResponse
            request = product_matches.product_matches_request(
                ProductMatchParams, gateway.settings
            )
            parsed = product_matches.parse_product_matches_response(
                gateway.proxy.find_product_matches(request), gateway.settings
            )
            self.assertListEqual(lib.to_dict(parsed), ParsedProductMatches)

    def test_parse_product_matches_error(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.return_value = ErrorResponse
            request = product_matches.product_matches_request(
                ProductMatchParams, gateway.settings
            )
            parsed = product_matches.parse_product_matches_response(
                gateway.proxy.find_product_matches(request), gateway.settings
            )
            self.assertListEqual(lib.to_dict(parsed), ParsedErrorResponse)


ProductMatchParams = {
    "shipper": {"postal_code": "11120", "country_code": "SE"},
    "recipient": {"postal_code": "00001", "country_code": "PL"},
    "parcels": [
        {"package_type": "PC", "weight": 2.5, "length": 40, "width": 30, "height": 15}
    ],
    "total_weight": 2.5,
    "total_number_of_pieces": 1,
    "import_export": "E",
}

MissingPartiesParams = {
    "shipper": {"postal_code": "11120", "country_code": "SE"},
}

ProductMatchRequest = {
    "parties": [
        {"type": "Consignor", "address": {"countryCode": "SE", "postalCode": "11120"}},
        {"type": "Consignee", "address": {"countryCode": "PL", "postalCode": "00001"}},
    ],
    "pieces": [
        {"packageType": "PC", "weight": 2.5, "length": 40, "width": 30, "height": 15}
    ],
    "totalWeight": 2.5,
    "totalNumberOfPieces": 1,
    "importExport": "E",
}

ProductMatchesResponse = """[
  {
    "product": {
      "code": "109",
      "name": "DHL Parcel Connect",
      "shortName": null,
      "isDomestic": false,
      "active": true,
      "isDefault": true,
      "hidden": false,
      "transportationMode": {
        "name": "Road"
      },
      "subCategories": [
        {
          "code": "Groupage",
          "name": "Stycke"
        },
        {
          "code": "Parcel",
          "name": "Paket"
        },
        {
          "code": "Un-palletized",
          "name": "Opallat"
        },
        {
          "code": "Package",
          "name": "Paket"
        }
      ],
      "fromCountries": [
        {
          "country": {
            "countryCode": "SE",
            "englishName": "Sweden",
            "customs": false
          }
        }
      ],
      "toCountries": [
        {
          "country": {
            "englishName": "France",
            "countryCode": "FR",
            "customs": false
          },
          "postalCodeExcludes": "97*,98*,99*"
        },
        {
          "country": {
            "englishName": "Norway",
            "countryCode": "NO",
            "customs": true
          },
          "postalCodeExcludes": "917*,8099"
        }
      ],
      "payerCodes": [
        {
          "code": "CPT",
          "name": "Carriage Paid To",
          "customs": false
        },
        {
          "code": "022",
          "name": "022: Consignor pays freight cost and export customs clearance",
          "customs": false
        }
      ],
      "rulesForCountryAndDeliveryTypes": [
        {
          "shipment": {
            "actualWeightMin": 0.1,
            "actualWeightMax": 25.0,
            "volumeMax": 0.096,
            "numberOfPiecesMin": 1.0,
            "numberOfPiecesMax": 1.0
          },
          "piece": {
            "actualWeightMin": 0.1,
            "actualWeightMax": 25.0,
            "lengthMin": 15.0,
            "lengthMax": 60.0,
            "widthMin": 11.0,
            "widthMax": 40.0,
            "heightMin": 2.0,
            "heightMax": 40.0,
            "volumeMax": 0.096
          },
          "country": {
            "englishName": "Poland",
            "countryCode": "PL",
            "customs": false
          },
          "deliveryType": {
            "code": "parcelStation",
            "name": "Parcelstation"
          }
        }
      ]
    }
  },
  {
    "product": {
      "code": "601",
      "name": "DHL Home Delivery International",
      "shortName": "HOME DELIVERY INT.",
      "isDomestic": false,
      "active": true,
      "isDefault": false,
      "hidden": false,
      "transportationMode": {
        "name": "Road"
      },
      "subCategories": [],
      "fromCountries": [
        {
          "country": {
            "countryCode": "DE",
            "englishName": "Germany",
            "customs": false
          }
        },
        {
          "country": {
            "countryCode": "GR",
            "englishName": "Greece",
            "customs": false
          }
        }
      ],
      "toCountries": [
        {
          "country": {
            "englishName": "United Kingdom",
            "countryCode": "GB",
            "customs": true
          },
          "postalCodeExcludes": "GY*,JE*"
        },
        {
          "country": {
            "englishName": "Spain",
            "countryCode": "ES",
            "customs": false
          },
          "postalCodeExcludes": "35*,38*,51*,52*"
        }
      ],
      "payerCodes": [
        {
          "code": "CPT",
          "name": "Carriage Paid To",
          "customs": false
        },
        {
          "code": "FCA",
          "name": "Free Carrier",
          "customs": false
        }
      ],
      "rulesForCountryAndDeliveryTypes": []
    }
  }
]"""

ParsedProductMatches = [
    [
        {
            "code": "109",
            "name": "DHL Parcel Connect",
            "is_domestic": False,
            "active": True,
            "is_default": True,
            "hidden": False,
            "from_countries": ["SE"],
            "to_countries": ["FR", "NO"],
            "to_country_postal_excludes": [
                {"country_code": "FR", "postal_code_excludes": "97*,98*,99*"},
                {"country_code": "NO", "postal_code_excludes": "917*,8099"},
            ],
            "payer_codes": ["CPT", "022"],
            "transportation_mode": {"name": "Road"},
            "sub_categories": [
                {"code": "Groupage", "name": "Stycke"},
                {"code": "Parcel", "name": "Paket"},
                {"code": "Un-palletized", "name": "Opallat"},
                {"code": "Package", "name": "Paket"},
            ],
            "rules_for_country_delivery_types": [
                {
                    "country_code": "PL",
                    "delivery_type": "parcelStation",
                    "shipment": {
                        "actualWeightMin": 0.1,
                        "actualWeightMax": 25.0,
                        "volumeMax": 0.096,
                        "numberOfPiecesMin": 1.0,
                        "numberOfPiecesMax": 1.0,
                    },
                    "piece": {
                        "actualWeightMin": 0.1,
                        "actualWeightMax": 25.0,
                        "lengthMin": 15.0,
                        "lengthMax": 60.0,
                        "widthMin": 11.0,
                        "widthMax": 40.0,
                        "heightMin": 2.0,
                        "heightMax": 40.0,
                        "volumeMax": 0.096,
                    },
                }
            ],
        },
        {
            "code": "601",
            "name": "DHL Home Delivery International",
            "short_name": "HOME DELIVERY INT.",
            "is_domestic": False,
            "active": True,
            "is_default": False,
            "hidden": False,
            "from_countries": ["DE", "GR"],
            "to_countries": ["GB", "ES"],
            "to_country_postal_excludes": [
                {"country_code": "GB", "postal_code_excludes": "GY*,JE*"},
                {"country_code": "ES", "postal_code_excludes": "35*,38*,51*,52*"},
            ],
            "payer_codes": ["CPT", "FCA"],
            "transportation_mode": {"name": "Road"},
        },
    ],
    [],
]

ErrorResponse = """{
  "error": "One or more validation errors occurred.",
  "errors": [
    {
      "field": "$.parties[1].address.postalCode",
      "errorCode": 22001,
      "message": "The Consignee address postal code is required"
    }
  ]
}"""

ParsedErrorResponse = [
    [],
    [
        {
            "carrier_id": "dhl_freight_sweden",
            "carrier_name": "dhl_freight_sweden",
            "code": "22001",
            "message": "The Consignee address postal code is required",
            "details": {"field": "$.parties[1].address.postalCode"},
        }
    ],
]


if __name__ == "__main__":
    unittest.main()
