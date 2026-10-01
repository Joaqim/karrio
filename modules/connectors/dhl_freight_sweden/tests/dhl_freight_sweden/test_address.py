"""DHL Freight address validation tests (PostalCodes API route lookup).

Route fixtures were captured live from the sandbox on 2026-09-17
(GET /postalcodeapi/v1/postalcodes/SE/{pc}/route): 11120 Stockholm and
41103 Göteborg are generally bookable with home delivery, 98138 Kiruna is
bookable without home delivery (product 118 unavailable), and 99999
returns the PascalCase ``ErrorResult`` the live API emits where the
vendored spec declares camelCase.
"""

import unittest
from unittest.mock import patch
from .fixture import gateway

import karrio.lib as lib
import karrio.sdk as karrio
import karrio.core.models as models


class TestDHLFreightSwedenAddressValidation(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_create_address_validation_request(self):
        unscoped = gateway.mapper.create_address_validation_request(
            models.AddressValidationRequest(**AddressValidationParams)
        )
        self.assertEqual(
            lib.to_dict(unscoped.serialize()),
            dict(country_code="SE", postal_code="11120"),
        )
        self.assertEqual(unscoped.ctx, dict(service=None))

        scoped = gateway.mapper.create_address_validation_request(
            models.AddressValidationRequest(**ScopedAddressValidationParams)
        )
        self.assertEqual(
            lib.to_dict(scoped.serialize()),
            dict(country_code="SE", postal_code="98138", service="118"),
        )
        self.assertEqual(scoped.ctx, dict(service="118"))

    def test_validate_address(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.return_value = RouteResponseStockholm
            karrio.Address.validate(
                models.AddressValidationRequest(**ScopedStockholmParams)
            ).from_(gateway)

        self.assertEqual(
            mock.call_args.kwargs["url"],
            f"{gateway.settings.postal_code_api_url}/postalcodes/SE/11120/route",
        )
        self.assertEqual(mock.call_args.kwargs["method"], "GET")
        self.assertEqual(
            mock.call_args.kwargs["headers"], {"client-key": "TEST_CLIENT_KEY"}
        )
        self.assertIs(mock.call_args.kwargs["on_error"], lib.error_decoder)

    def test_parse_address_validation_response(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.return_value = RouteResponseStockholm
            scoped = (
                karrio.Address.validate(
                    models.AddressValidationRequest(**ScopedStockholmParams)
                )
                .from_(gateway)
                .parse()
            )

        self.assertListEqual(lib.to_dict(scoped), ParsedStockholmScoped)

        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.return_value = RouteResponseKiruna
            unscoped = (
                karrio.Address.validate(
                    models.AddressValidationRequest(**KirunaParams)
                )
                .from_(gateway)
                .parse()
            )
            scoped_not_servable = (
                karrio.Address.validate(
                    models.AddressValidationRequest(**ScopedKirunaParams)
                )
                .from_(gateway)
                .parse()
            )

        # Unscoped reads the general bookable flag; the product-118 scope
        # reads homeDeliveryParcel, so the same Kiruna route is servable
        # unscoped and unservable scoped.
        self.assertListEqual(lib.to_dict(unscoped), ParsedKirunaUnscoped)
        self.assertListEqual(lib.to_dict(scoped_not_servable), ParsedKirunaScoped)

    def test_parse_error_response(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.return_value = RouteLookupErrorResponse
            parsed = (
                karrio.Address.validate(
                    models.AddressValidationRequest(**NotFoundParams)
                )
                .from_(gateway)
                .parse()
            )

        self.assertListEqual(lib.to_dict(parsed), ParsedErrorResponse)


if __name__ == "__main__":
    unittest.main()


AddressValidationParams = {
    "address": {"postal_code": "11120", "country_code": "SE"},
}

ScopedAddressValidationParams = {
    "address": {"postal_code": "98138", "country_code": "SE"},
    "options": {"service": "dhl_freight_sweden_hemleverans_paket_b2c"},
}

ScopedStockholmParams = {
    "address": {"postal_code": "11120", "country_code": "SE"},
    "options": {"service": "118"},
}

KirunaParams = {
    "address": {"postal_code": "98138", "country_code": "SE"},
}

ScopedKirunaParams = {
    **KirunaParams,
    "options": {"service": "dhl_freight_sweden_hemleverans_paket_b2c"},
}

NotFoundParams = {
    "address": {"postal_code": "99999", "country_code": "SE"},
}

RouteResponseStockholm = """{
  "countryCode": "SE",
  "postalCode": "11120",
  "city": "STOCKHOLM",
  "lineHaul": "110",
  "terminalId": "4210",
  "deviating": "0",
  "updatedDate": "2006-01-11T00:00:00",
  "bookable": true,
  "homeDeliveryParcel": true
}"""

RouteResponseKiruna = """{
  "countryCode": "SE",
  "postalCode": "98138",
  "city": "KIRUNA",
  "lineHaul": "950",
  "terminalId": "4850",
  "deviating": "0",
  "updatedDate": "2026-07-02T22:00:03",
  "bookable": true,
  "homeDeliveryParcel": false
}"""

RouteLookupErrorResponse = """{"Status":400,"ErrorCode":16010,"UserMessage":"Post code '99999' not found."}"""

ParsedStockholmScoped = [
    {
        "carrier_id": "dhl_freight_sweden",
        "carrier_name": "dhl_freight_sweden",
        "success": True,
        "complete_address": {
            "city": "STOCKHOLM",
            "postal_code": "11120",
            "country_code": "SE",
            "residential": False,
        },
    },
    [],
]

ParsedKirunaUnscoped = [
    {
        "carrier_id": "dhl_freight_sweden",
        "carrier_name": "dhl_freight_sweden",
        "success": True,
        "complete_address": {
            "city": "KIRUNA",
            "postal_code": "98138",
            "country_code": "SE",
            "residential": False,
        },
    },
    [],
]

ParsedKirunaScoped = [
    {
        "carrier_id": "dhl_freight_sweden",
        "carrier_name": "dhl_freight_sweden",
        "success": False,
        "complete_address": {
            "city": "KIRUNA",
            "postal_code": "98138",
            "country_code": "SE",
            "residential": False,
        },
    },
    [],
]

ParsedErrorResponse = [
    None,
    [
        {
            "carrier_id": "dhl_freight_sweden",
            "carrier_name": "dhl_freight_sweden",
            "code": "16010",
            "message": "Post code '99999' not found.",
            "details": {},
        }
    ],
]
