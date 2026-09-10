"""DHL Freight (SE API Farm) rate tests.

PRICE resolution is served from Karrio's static-rate mechanism (universal
rating mixin) against the service levels seeded in ``units.DEFAULT_SERVICES``.
The SE API Farm pricequote API is out of Phase 0 scope, so ``get_rates``
issues no carrier call; the rate=0.0 placeholders are overridden by the
merchant's negotiated prices at runtime.

Zone coverage follows the DHL Product API destination footprint (fetched
2026-09-10, test host): the outbound parcel family (109/112/232) rates to
its from-SE Europe country lists, and 107 — the reverse lane to Sweden —
rates when the recipient is in Sweden.
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

    def _fetch_rates_without_origin_gate(self, payload: dict):
        # ``karrio.Rating.fetch`` aborts any request whose shipper country
        # differs from ``account_country_code`` ("SE") with
        # SHIPPING_SDK_ORIGIN_NOT_SERVICED_ERROR, so the return lane is driven
        # through the gateway's own rate pipeline instead; this exercises the
        # same mapper/proxy calls the unified interface makes after its check.
        request = gateway.mapper.create_rate_request(models.RateRequest(**payload))
        response = gateway.proxy.get_rates(request)
        return gateway.mapper.parse_rate_response(response)

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
        # SE->SE: the 11 domestic products plus the return-lane product 107
        # rate (delivery in Sweden classifies as domicile via the account
        # country, and 107's Sweden zone matches the recipient); the outbound
        # parcels 109/112/232 no longer rate because their Europe zones
        # exclude SE, and the international freight products require an
        # international lane.
        request = models.RateRequest(**FullCatalogRatePayload)
        rates, messages = karrio.Rating.fetch(request).from_(gateway).parse()

        offered = {rate.service for rate in rates}
        self.assertEqual(offered, DomesticServices | {ReturnConnectService})
        self.assertNotIn(ParcelConnectService, offered)
        self.assertNotIn(ParcelConnectPlusService, offered)
        self.assertNotIn(EuroconnectService, offered)
        self.assertEqual(messages, [])

    def test_parse_rate_response_international(self):
        # SE->DE: the unrestricted international freight products plus the
        # three outbound parcels (DE is in every Europe footprint) rate; the
        # domestic products and the SE-only return lane find no match.
        request = models.RateRequest(**InternationalRatePayload)
        rates, messages = karrio.Rating.fetch(request).from_(gateway).parse()

        offered = {rate.service for rate in rates}
        self.assertEqual(offered, InternationalFreightServices | OutboundParcelServices)
        self.assertEqual(messages, [])

    def test_parse_rate_response_poland_offers_parcel_family(self):
        # SE->PL: the lane that surfaced the gap (live-confirmed 2026-09-10 —
        # only 202/205/233/601/SPI were offered); PL is in all three Europe
        # footprints, so the parcel family must now rate, while the domestic
        # products (e.g. Paket 102) must not.
        request = models.RateRequest(**PolandRatePayload)
        rates, messages = karrio.Rating.fetch(request).from_(gateway).parse()

        offered = {rate.service for rate in rates}
        self.assertEqual(offered, InternationalFreightServices | OutboundParcelServices)
        self.assertNotIn(DomesticPaketService, offered)
        self.assertEqual(messages, [])

    def test_parse_rate_response_denmark_regression(self):
        # SE->DK: a Nordic neighbour served before the fix must keep the
        # parcel family; DK is in all three Europe footprints.
        request = models.RateRequest(**DenmarkRatePayload)
        rates, messages = karrio.Rating.fetch(request).from_(gateway).parse()

        offered = {rate.service for rate in rates}
        self.assertEqual(offered, InternationalFreightServices | OutboundParcelServices)
        self.assertEqual(messages, [])

    def test_parse_rate_response_switzerland_euroconnect_only(self):
        # SE->CH: only 232 covers Switzerland (CH is absent from the
        # Parcel Connect footprints), so 109/112 must not rate.
        request = models.RateRequest(**SwitzerlandRatePayload)
        rates, messages = karrio.Rating.fetch(request).from_(gateway).parse()

        offered = {rate.service for rate in rates}
        self.assertEqual(offered, InternationalFreightServices | {EuroconnectService})
        self.assertNotIn(ParcelConnectService, offered)
        self.assertNotIn(ParcelConnectPlusService, offered)
        self.assertEqual(messages, [])

    def test_parse_rate_response_return_lane(self):
        # PL->SE: the Parcel Return Connect lane. The rating mixin classifies
        # delivery in the account country (SE) as domicile, so 107 surfaces
        # through its domicile flag with the Sweden zone matching the
        # recipient; the outbound parcels exclude SE and the freight products
        # require an international lane.
        rates, messages = self._fetch_rates_without_origin_gate(ReturnLaneRatePayload)

        offered = {rate.service for rate in rates}
        self.assertEqual(offered, DomesticServices | {ReturnConnectService})
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

_shipper_pl = {
    **_shipper,
    "company_name": "Test Shipper Sp. z o.o.",
    "person_name": "Jan Kowalski",
    "address_line1": "Ulica Kwiatowa 3",
    "city": "Warszawa",
    "postal_code": "00-001",
    "country_code": "PL",
    "phone_number": "+48 22 123 456",
    "email": "shipper@example.pl",
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

_recipient_pl = {
    **_recipient_se,
    "company_name": "Test Recipient Sp. z o.o.",
    "person_name": "Piotr Nowak",
    "address_line1": "Ulica Marszalkowska 5",
    "city": "Warszawa",
    "postal_code": "00-950",
    "country_code": "PL",
    "email": "recipient@example.pl",
}

_recipient_dk = {
    **_recipient_se,
    "company_name": "Test Recipient ApS",
    "person_name": "Mette Hansen",
    "address_line1": "Vesterbrogade 4",
    "city": "Kobenhavn",
    "postal_code": "1620",
    "country_code": "DK",
    "email": "recipient@example.dk",
}

_recipient_ch = {
    **_recipient_se,
    "company_name": "Test Recipient AG",
    "person_name": "Luca Bianchi",
    "address_line1": "Bahnhofstrasse 6",
    "city": "Zurich",
    "postal_code": "8001",
    "country_code": "CH",
    "email": "recipient@example.ch",
}

_parcel = {
    "weight": 5.0,
    "width": 20.0,
    "height": 15.0,
    "length": 30.0,
    "weight_unit": "KG",
    "dimension_unit": "CM",
}


def _payload(shipper: dict, recipient: dict, services: list) -> dict:
    return {
        "shipper": shipper,
        "recipient": recipient,
        "parcels": [_parcel],
        "services": services,
        "options": {},
    }


DomesticRatePayload = _payload(_shipper, _recipient_se, ["dhl_freight_sweden_paket"])
FullCatalogRatePayload = _payload(_shipper, _recipient_se, [])
InternationalRatePayload = _payload(_shipper, _recipient_de, [])
PolandRatePayload = _payload(_shipper, _recipient_pl, [])
DenmarkRatePayload = _payload(_shipper, _recipient_dk, [])
SwitzerlandRatePayload = _payload(_shipper, _recipient_ch, [])
ReturnLaneRatePayload = _payload(_shipper_pl, _recipient_se, [])

DomesticServices = {
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
}
DomesticPaketService = "dhl_freight_sweden_paket"
OutboundParcelServices = {
    "dhl_freight_sweden_parcel_connect_b2c",
    "dhl_freight_sweden_parcel_connect_plus",
    "dhl_freight_sweden_euroconnect_plus",
}
ReturnConnectService = "dhl_freight_sweden_parcel_return_connect_c2b"
ParcelConnectService = "dhl_freight_sweden_parcel_connect_b2c"
ParcelConnectPlusService = "dhl_freight_sweden_parcel_connect_plus"
EuroconnectService = "dhl_freight_sweden_euroconnect_plus"
InternationalFreightServices = {
    "dhl_freight_sweden_road_freight_standard",
    "dhl_freight_sweden_road_freight_direct",
    "dhl_freight_sweden_road_freight_priority",
    "dhl_freight_sweden_home_delivery_international_b2c",
    "dhl_freight_sweden_standard_pallet_international",
}
