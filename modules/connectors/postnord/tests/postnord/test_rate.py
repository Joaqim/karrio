"""PostNord carrier rate tests.

PostNord has no live rate API; rating is served from Karrio's first-class
static-rate mechanism (universal rating mixin) against the connection's
service levels, whose per-merchant prices arrive via the server-side RateSheet
(modeled here by the fixture's ``services``).
"""

import unittest
from unittest.mock import patch, ANY
from .fixture import gateway

import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models


class TestPostNordRating(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.RateRequest = models.RateRequest(**RatePayload)

    def test_get_rates_makes_no_http_call(self):
        # Rating resolves the static RateSheet locally; no carrier HTTP call.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            karrio.Rating.fetch(self.RateRequest).from_(gateway)
            mock.assert_not_called()

    def test_parse_rate_response(self):
        parsed_response = (
            karrio.Rating.fetch(self.RateRequest).from_(gateway).parse()
        )
        self.assertListEqual(lib.to_dict(parsed_response), ParsedRateResponse)

    def test_parse_rate_response_no_matching_zone(self):
        # A destination outside every service zone yields empty rates and no
        # crash (DoD: rate quote + error handling). The fixture's zones only
        # cover SE, so a US recipient matches no zone.
        request = models.RateRequest(**NoZoneRatePayload)
        parsed_response = karrio.Rating.fetch(request).from_(gateway).parse()
        self.assertListEqual(lib.to_dict(parsed_response), NoZoneParsedRateResponse)


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

ParsedRateResponse = [
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

NoZoneParsedRateResponse = [
    [],
    [],
]
