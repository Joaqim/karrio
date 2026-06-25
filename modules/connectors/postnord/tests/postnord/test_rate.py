"""PostNord carrier rate tests.

PRICE resolution is served from Karrio's first-class static-rate mechanism
(universal rating mixin) against the connection's service levels, whose
per-merchant prices arrive via the server-side RateSheet (modeled here by the
fixture's ``services``).

Transit-time enrichment is opt-in via the ``enable_transit_times`` connection
config flag (default off), because PostNord returns 403 "Invalid API Key" on the
Transit Time API for keys not subscribed to that product. With the default
gateway no carrier call is made and rates use their static transit days. With
``gateway_with_transit`` the Transit Time V2 API
(``GET /rest/transport/v2/transittime/addresstoaddress``) is called once per
request to enrich transit days, add an estimated delivery date, and drop
services PostNord reports as not bookable. A transit outage degrades gracefully:
prices are still returned with their static transit days and a warning Message.
"""

import unittest
from unittest.mock import patch
from .fixture import gateway, gateway_with_transit

import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models


class TestPostNordRating(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.RateRequest = models.RateRequest(**RatePayload)

    def test_get_rates_makes_no_http_call(self):
        # Default gateway: transit enrichment is off, so rate() issues no
        # carrier call (restores the pre-transit no-carrier-call invariant).
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            karrio.Rating.fetch(self.RateRequest).from_(gateway)

        mock.assert_not_called()

    def test_parse_rate_response(self):
        # Default gateway: static output with the service-level transit_days and
        # no estimated_delivery enrichment.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            parsed_response = (
                karrio.Rating.fetch(self.RateRequest).from_(gateway).parse()
            )

        mock.assert_not_called()
        self.assertListEqual(lib.to_dict(parsed_response), StaticParsedRateResponse)

    def test_parse_rate_response_no_matching_zone(self):
        # A destination outside every service zone yields empty rates and no
        # crash. The fixture's zones only cover SE, so a US recipient matches no
        # zone. No transit dependency on the default gateway.
        request = models.RateRequest(**NoZoneRatePayload)
        parsed_response = karrio.Rating.fetch(request).from_(gateway).parse()

        self.assertListEqual(lib.to_dict(parsed_response), NoZoneParsedRateResponse)

    def test_get_rates_issues_transit_call(self):
        # Opt-in gateway: rate() calls the Transit Time V2 API once per request.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "[]"
            karrio.Rating.fetch(self.RateRequest).from_(gateway_with_transit)
            url = mock.call_args.kwargs["url"]

        self.assertIn(
            "https://atapi2.postnord.com/rest/transport/v2/transittime/addresstoaddress",
            url,
        )
        self.assertIn("apikey=TEST_API_KEY", url)
        self.assertIn("originPostalCode=11528", url)
        self.assertIn("originCountryCode=SE", url)
        self.assertIn("destinationPostalCode=17173", url)
        self.assertIn("destinationCountryCode=SE", url)
        # Comma-separated carrier_service_codes of the catalog services.
        self.assertIn("serviceCodes=18", url)
        self.assertEqual(mock.call_args.kwargs["method"], "GET")

    def test_parse_rate_response_transit_enriched(self):
        # Opt-in gateway: transit enrichment overrides transit_days and adds
        # estimated_delivery; the service (17) marked isBookable=false is dropped.
        request = models.RateRequest(**AllServicesRatePayload)
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = TransitTimeResponse
            parsed_response = (
                karrio.Rating.fetch(request).from_(gateway_with_transit).parse()
            )

        self.assertListEqual(lib.to_dict(parsed_response), EnrichedParsedRateResponse)

    def test_parse_rate_response_transit_degraded(self):
        # Opt-in gateway: when the transit call fails, prices are still returned
        # with their static transit_days, no bookability filtering, and exactly
        # one warning Message.
        request = models.RateRequest(**AllServicesRatePayload)
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.side_effect = Exception("transit api unavailable")
            parsed_response = (
                karrio.Rating.fetch(request).from_(gateway_with_transit).parse()
            )

        self.assertListEqual(
            lib.to_dict(parsed_response), DegradedParsedRateResponse
        )


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

# Request both catalog services so isBookable filtering is observable.
AllServicesRatePayload = {
    **RatePayload,
    "services": [],
}

# Transit Time V2 array body: code 18 gets a 1-day departure->arrival span and
# is bookable; code 17 is marked not bookable and must be dropped.
TransitTimeResponse = lib.to_json(
    [
        {
            "service": {"basicServiceCode": "18", "name": "PostNord Parcel"},
            "estimatedTimeOfArrival": {
                "dateOfDeparture": "2024-08-23",
                "timeOfDeparture": "2024-08-23T19:15:00",
                "timeOfArrival": "2024-08-24T21:00:00",
            },
            "isSupported": True,
            "isBookable": True,
        },
        {
            "service": {"basicServiceCode": "17", "name": "PostNord MyPack Home"},
            "estimatedTimeOfArrival": {
                "dateOfDeparture": "2024-08-23",
                "timeOfArrival": "2024-08-26T21:00:00",
            },
            "isSupported": True,
            "isBookable": False,
        },
    ]
)

# Default path (transit off): static service-level transit_days (2), no
# estimated_delivery, and no messages.
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

# Opt-in path (transit on): code 18 transit_days overridden to 1 with an
# estimated_delivery; code 17 dropped as not bookable.
EnrichedParsedRateResponse = [
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "currency": "SEK",
            "service": "postnord_parcel",
            "total_charge": 89.0,
            "transit_days": 1,
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
                "estimated_delivery": "2024-08-24",
            },
        }
    ],
    [],
]

DegradedParsedRateResponse = [
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
        },
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "currency": "SEK",
            "service": "postnord_mypack_home",
            "total_charge": 99.0,
            "transit_days": 2,
            "extra_charges": [
                {
                    "amount": 99.0,
                    "currency": "SEK",
                    "name": "Base Charge",
                }
            ],
            "meta": {
                "carrier_service_code": "17",
                "service_name": "PostNord MyPack Home",
                "shipping_charges": 99.0,
                "shipping_currency": "SEK",
            },
        },
    ],
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "code": "transit_time_unavailable",
            "level": "warning",
            "message": (
                "PostNord transit-time enrichment was unavailable; rates use "
                "static transit days and no serviceability filtering."
            ),
        }
    ],
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
