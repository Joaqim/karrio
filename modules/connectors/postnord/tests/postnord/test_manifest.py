"""PostNord carrier manifest tests.

PostNord has no scan-form / end-of-day manifest endpoint, so the Manifest
operation is explicitly unsupported: it issues no HTTP request and resolves to
an explicit "not_supported" Message directing callers to Pickup scheduling.
"""

import unittest
from unittest.mock import patch
from .fixture import gateway

import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models


class TestPostNordManifest(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.ManifestRequest = models.ManifestRequest(**ManifestPayload)

    def test_create_manifest(self):
        # The unsupported manifest operation must not perform an HTTP request.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            karrio.Manifest.create(self.ManifestRequest).from_(gateway)
            mock.assert_not_called()

    def test_parse_manifest_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            parsed_response = (
                karrio.Manifest.create(self.ManifestRequest).from_(gateway).parse()
            )
            mock.assert_not_called()
            self.assertListEqual(
                lib.to_dict(parsed_response), ParsedManifestResponse
            )


if __name__ == "__main__":
    unittest.main()


ManifestPayload = {
    "shipment_identifiers": ["SHIP-0001", "SHIP-0002"],
    "address": {
        "address_line1": "Sandhamnsgatan 61",
        "city": "Stockholm",
        "postal_code": "11528",
        "country_code": "SE",
        "person_name": "John Sender",
        "company_name": "ACME Sender AB",
        "phone_number": "+46701234567",
        "email": "sender@example.com",
    },
}

ParsedManifestResponse = [
    None,
    [
        {
            "carrier_id": "postnord",
            "carrier_name": "postnord",
            "code": "not_supported",
            "message": "PostNord has no manifest/scan-form endpoint; use Pickup scheduling instead.",
        }
    ],
]
