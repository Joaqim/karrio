"""DHL Freight (SE API Farm) rate tests.

PRICE resolution is served from Karrio's static-rate mechanism (universal
rating mixin) against the service levels seeded in ``units.DEFAULT_SERVICES``.
The SE API Farm pricequote API is out of Phase 0 scope, so ``get_rates``
issues no carrier call; the rate=0.0 placeholders are overridden by the
merchant's negotiated prices at runtime.
"""

import unittest
from unittest.mock import patch
from .fixture import gateway

import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models


class TestDHLFreightRating(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_rating_capability_advertised(self):
        # The one-click shipment flow filters connections and gateways on the
        # "rating" capability; the Proxy must expose get_rates.
        self.assertIn("rating", gateway.capabilities)

    def test_get_rates_makes_no_http_call(self):
        request = models.RateRequest(**DomesticRatePayload)

        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            karrio.Rating.fetch(request).from_(gateway)

        mock.assert_not_called()

    def test_parse_rate_response_requested_service(self):
        request = models.RateRequest(**DomesticRatePayload)
        rates, messages = karrio.Rating.fetch(request).from_(gateway).parse()

        self.assertEqual(
            lib.to_dict(rates),
            [
                {
                    "carrier_id": "dhl_freight_sweden",
                    "carrier_name": "dhl_freight_sweden",
                    "currency": "SEK",
                    "service": "dhl_freight_sweden_paket",
                    "total_charge": 0.0,
                    "extra_charges": [
                        {"amount": 0.0, "currency": "SEK", "name": "Base Charge"}
                    ],
                    "meta": {
                        "carrier_service_code": "102",
                        "service_name": "Paket",
                        "shipping_charges": 0.0,
                        "shipping_currency": "SEK",
                    },
                }
            ],
        )
        self.assertEqual(messages, [])

    def test_parse_rate_response_domestic_full_catalog(self):
        # SE->SE: the 11 domestic products plus the 4 Nordic cross-border
        # parcels rate (their Nordic zones include SE); the 5 international
        # freight products are excluded because SE->SE is a domicile shipment.
        request = models.RateRequest(**FullCatalogRatePayload)
        rates, messages = karrio.Rating.fetch(request).from_(gateway).parse()

        offered = {rate.service for rate in rates}
        self.assertEqual(offered, DomesticAndNordicServices)
        self.assertEqual(messages, [])

    def test_parse_rate_response_international(self):
        # SE->DE: only the unrestricted international freight products rate;
        # the domestic and Nordic-gated services find no matching zone.
        request = models.RateRequest(**InternationalRatePayload)
        rates, messages = karrio.Rating.fetch(request).from_(gateway).parse()

        offered = {rate.service for rate in rates}
        self.assertEqual(offered, InternationalServices)
        self.assertEqual(messages, [])


if __name__ == "__main__":
    unittest.main()


_shipper = {
    "company_name": "Test Shipper AB",
    "person_name": "Sven Svensson",
    "address_line1": "Kungsgatan 1",
    "city": "Stockholm",
    "postal_code": "11143",
    "country_code": "SE",
    "phone_number": "+46 8 123 456",
    "email": "shipper@example.se",
}

_recipient_se = {
    "company_name": "Test Recipient AB",
    "person_name": "Anna Andersson",
    "address_line1": "Storgatan 2",
    "city": "Goteborg",
    "postal_code": "41103",
    "country_code": "SE",
    "phone_number": "+46 31 987 654",
    "email": "recipient@example.se",
}

_recipient_de = {
    **_recipient_se,
    "city": "Berlin",
    "postal_code": "10115",
    "country_code": "DE",
}

_parcel = {
    "weight": 5.0,
    "width": 20.0,
    "height": 15.0,
    "length": 30.0,
    "weight_unit": "KG",
    "dimension_unit": "CM",
}


def _payload(recipient: dict, services: list) -> dict:
    return {
        "shipper": _shipper,
        "recipient": recipient,
        "parcels": [_parcel],
        "services": services,
        "options": {},
    }


DomesticRatePayload = _payload(_recipient_se, ["dhl_freight_sweden_paket"])
FullCatalogRatePayload = _payload(_recipient_se, [])
InternationalRatePayload = _payload(_recipient_de, [])

DomesticAndNordicServices = {
    "dhl_freight_sweden_hemleverans_paket_b2c",
    "dhl_freight_sweden_home_delivery_b2c",
    "dhl_freight_sweden_home_delivery_c2b",
    "dhl_freight_sweden_home_delivery_c2b_502",
    "dhl_freight_sweden_pall",
    "dhl_freight_sweden_paket",
    "dhl_freight_sweden_parti",
    "dhl_freight_sweden_service_point_b2c",
    "dhl_freight_sweden_service_point_c2b",
    "dhl_freight_sweden_special",
    "dhl_freight_sweden_stycke",
    "dhl_freight_sweden_euroconnect_plus",
    "dhl_freight_sweden_parcel_connect_b2c",
    "dhl_freight_sweden_parcel_return_connect_c2b",
    "dhl_freight_sweden_parcel_connect_plus",
}

InternationalServices = {
    "dhl_freight_sweden_road_freight_standard",
    "dhl_freight_sweden_road_freight_direct",
    "dhl_freight_sweden_road_freight_priority",
    "dhl_freight_sweden_home_delivery_international_b2c",
    "dhl_freight_sweden_standard_pallet_international",
}
