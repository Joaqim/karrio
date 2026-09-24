"""PostNord carrier rate tests.

PRICE resolution is served from Karrio's first-class static-rate mechanism
(universal rating mixin) against the connection's service levels, whose
per-merchant prices arrive via the server-side RateSheet (modeled here by the
fixture's ``services``).
"""

import unittest
from unittest.mock import patch
from .fixture import (
    gateway,
    gateway_default_catalog,
    gateway_letters_off,
    gateway_letters_on,
    gateway_letters_z11,
)

import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models


class TestPostNordRating(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.RateRequest = models.RateRequest(**RatePayload)

    def test_get_rates_makes_no_http_call(self):
        # Rating resolves static prices, so rate() issues no carrier call.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            karrio.Rating.fetch(self.RateRequest).from_(gateway)

        mock.assert_not_called()

    def test_parse_rate_response(self):
        # Static output with the service-level transit_days.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            parsed_response = (
                karrio.Rating.fetch(self.RateRequest).from_(gateway).parse()
            )

        mock.assert_not_called()
        self.assertListEqual(lib.to_dict(parsed_response), StaticParsedRateResponse)

    def test_parse_rate_response_no_matching_zone(self):
        # A destination outside every service zone yields empty rates and no
        # crash. The fixture's zones only cover SE, so a US recipient matches no
        # zone.
        request = models.RateRequest(**NoZoneRatePayload)
        parsed_response = karrio.Rating.fetch(request).from_(gateway).parse()

        self.assertListEqual(lib.to_dict(parsed_response), NoZoneParsedRateResponse)

    def test_parse_rate_response_mypack_collect_cross_border(self):
        # MyPack Collect (carrier code 19) is a Nordic cross-border
        # service, so a SE->FI request must be covered. The full DEFAULT_SERVICES
        # catalog is exercised via the empty-services gateway; a rate is returned
        # and no destination_not_supported message is surfaced.
        request = models.RateRequest(**MyPackCollectCrossBorderPayload)
        rates, messages = (
            karrio.Rating.fetch(request).from_(gateway_default_catalog).parse()
        )

        offered = [rate.service for rate in rates]
        self.assertIn("postnord_mypack_collect", offered)
        self.assertNotIn("destination_not_supported", [m.code for m in messages])

    def test_parse_rate_response_home_services_cross_border(self):
        # Home Small (11), MyPack Home Small (30), and MyPack Home
        # (Norway, 32) carry Nordic zones, so a SE->NO request must be covered.
        # All three resolve from DEFAULT_SERVICES via the empty-services gateway
        # and no destination_not_supported message is surfaced.
        request = models.RateRequest(**HomeServicesCrossBorderPayload)
        rates, messages = (
            karrio.Rating.fetch(request).from_(gateway_default_catalog).parse()
        )

        offered = [rate.service for rate in rates]
        self.assertIn("postnord_home_small", offered)
        self.assertIn("postnord_mypack_home_small", offered)
        self.assertIn("postnord_mypack_home_no", offered)
        self.assertNotIn("destination_not_supported", [m.code for m in messages])

    def test_letter_services_hidden_by_default(self):
        # Gated letter products (34, UX) are withheld unless their opt-in toggle
        # is enabled; only the ungated international parcel service is offered.
        request = models.RateRequest(**InternationalRatePayload)
        rates, _ = karrio.Rating.fetch(request).from_(gateway_letters_off).parse()

        offered = {rate.service for rate in rates}
        self.assertEqual(offered, {"postnord_postpaket_utrikes"})

    def test_letter_services_offered_when_enabled(self):
        # With both toggles on and the Sweden issuer (Z12), both letter products
        # join the international parcel service.
        request = models.RateRequest(**InternationalRatePayload)
        rates, _ = karrio.Rating.fetch(request).from_(gateway_letters_on).parse()

        offered = {rate.service for rate in rates}
        self.assertEqual(
            offered,
            {
                "postnord_postpaket_utrikes",
                "postnord_tracked_letter",
                "postnord_export_letter",
            },
        )

    def test_export_letter_requires_sweden_issuer(self):
        # Under the Denmark issuer (Z11) the export letter is withheld even with
        # its toggle on; the tracked letter (no issuer restriction) is offered.
        request = models.RateRequest(**InternationalRatePayload)
        rates, _ = karrio.Rating.fetch(request).from_(gateway_letters_z11).parse()

        offered = {rate.service for rate in rates}
        self.assertIn("postnord_tracked_letter", offered)
        self.assertNotIn("postnord_export_letter", offered)


if __name__ == "__main__":
    unittest.main()


RatePayload = {
    "shipper": {
        "address_line1": "Sandhamnsgatan 61",
        "city": "Stockholm",
        "postal_code": "11528",
        "country_code": "SE",
        "person_name": "John Sender",
        "company_name": "ACME Sender AB",
        "phone_number": "+46701234567",
        "email": "sender@example.com",
    },
    "recipient": {
        "address_line1": "Terminalvagen 24",
        "city": "Solna",
        "postal_code": "17173",
        "country_code": "SE",
        "person_name": "Jane Receiver",
        "company_name": "Receiver Co",
        "phone_number": "+46709876543",
        "email": "receiver@example.com",
    },
    "parcels": [
        {
            "weight": 1.5,
            "width": 20.0,
            "height": 10.0,
            "length": 30.0,
            "weight_unit": "KG",
            "dimension_unit": "CM",
            "packaging_type": "small_box",
        }
    ],
    "services": ["postnord_parcel"],
}

# International shipment (SE->DE) requesting all services, used to observe which
# international-flagged services (including gated letter products) are offered.
InternationalRatePayload = {
    **RatePayload,
    "recipient": {
        "address_line1": "Friedrichstrasse 43",
        "city": "Berlin",
        "postal_code": "10117",
        "country_code": "DE",
        "person_name": "Jane Receiver",
        "company_name": "Receiver GmbH",
        "phone_number": "+493012345678",
        "email": "receiver@example.com",
    },
    "services": [],
}

# Static service-level transit_days (2) and no messages.
StaticParsedRateResponse = [
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "currency": "SEK",
            "service": "postnord_parcel",
            "total_charge": 89.0,
            "transit_days": 2,
            "extra_charges": [
                {
                    "amount": 89.0,
                    "currency": "SEK",
                    "name": "Base Charge",
                }
            ],
            "meta": {
                "carrier_service_code": "18",
                "service_name": "PostNord Parcel",
                "shipping_charges": 89.0,
                "shipping_currency": "SEK",
            },
        }
    ],
    [],
]

NoZoneRatePayload = {
    **RatePayload,
    "recipient": {
        "address_line1": "350 5th Ave",
        "city": "New York",
        "postal_code": "10118",
        "country_code": "US",
        "person_name": "Jane Receiver",
        "company_name": "Receiver Co",
        "phone_number": "+12125551234",
        "email": "receiver@example.com",
    },
    "services": [],
}

# Nordic cross-border shipment (SE->FI) explicitly requesting MyPack Collect.
# Kemi is a Finnish city; the recipient country_code FI must match the service's
# Nordic zone.
MyPackCollectCrossBorderPayload = {
    **RatePayload,
    "recipient": {
        "address_line1": "Valtakatu 1",
        "city": "Kemi",
        "postal_code": "94100",
        "country_code": "FI",
        "person_name": "Jane Receiver",
        "company_name": "Receiver Oy",
        "phone_number": "+358401234567",
        "email": "receiver@example.com",
    },
    "services": ["postnord_mypack_collect"],
}

# Nordic cross-border shipment (SE->NO) requesting the three home/mypack-home
# services with Nordic zones.
HomeServicesCrossBorderPayload = {
    **RatePayload,
    "recipient": {
        "address_line1": "Karl Johans gate 1",
        "city": "Oslo",
        "postal_code": "0150",
        "country_code": "NO",
        "person_name": "Jane Receiver",
        "company_name": "Receiver AS",
        "phone_number": "+4721234567",
        "email": "receiver@example.com",
    },
    "services": [
        "postnord_home_small",
        "postnord_mypack_home_small",
        "postnord_mypack_home_no",
    ],
}

NoZoneParsedRateResponse = [
    [],
    [],
]
