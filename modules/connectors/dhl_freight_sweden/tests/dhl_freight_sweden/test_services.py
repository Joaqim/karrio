"""DHL Freight (SE API Farm) service-level seeding tests.

``DEFAULT_SERVICES`` seeds the rate-sheet catalog consumed by universal
rating (the dashboard presents these as the carrier's shippable services).
These tests keep it aligned with the ``ShippingService`` product enum and
guard the zone invariants the rating mixin depends on.
"""

import unittest

from karrio.providers.dhl_freight_sweden import units


class TestDHLFreightServiceLevels(unittest.TestCase):
    def setUp(self):
        self.levels = {s.service_code: s for s in units.DEFAULT_SERVICES}

    def test_service_codes_prefixed_with_carrier_id(self):
        for member in units.ShippingService:
            self.assertTrue(
                member.name.startswith("dhl_freight_sweden_"),
                f"{member.name} breaks the carrier-id naming convention",
            )

    def test_option_codes_prefixed_with_carrier_id(self):
        unified_aliases = {"email_notification", "insurance"}
        for member in units.ShippingOption:
            self.assertTrue(
                member.name.startswith("dhl_freight_sweden_")
                or member.name in unified_aliases,
                f"{member.name} breaks the carrier-id naming convention",
            )

    def test_service_levels_cover_product_enum(self):
        self.assertEqual(
            set(self.levels.keys()),
            {member.name for member in units.ShippingService},
        )

    def test_carrier_service_codes_match_enum_values(self):
        for member in units.ShippingService:
            self.assertEqual(
                self.levels[member.name].carrier_service_code,
                member.value,
                f"carrier_service_code mismatch for {member.name}",
            )

    def test_every_service_has_a_zone(self):
        # The universal rating mixin drops services without a matching zone,
        # so a zoneless service silently never rates.
        for code, level in self.levels.items():
            self.assertTrue(
                level.zones,
                f"{code} has no zone and would never produce a rate",
            )

    def test_zone_partition(self):
        domestic = {
            "118", "401", "402", "502", "210", "102",
            "212", "103", "104", "209", "211",
        }
        nordic = {"109", "107", "112", "232"}
        international = {"202", "205", "233", "601", "SPI"}

        for _, level in self.levels.items():
            code = level.carrier_service_code
            self.assertEqual(level.currency, "SEK")

            if code in domestic:
                self.assertTrue(level.domicile)
                self.assertFalse(level.international)
                self.assertEqual(
                    [c for z in level.zones for c in (z.country_codes or [])],
                    ["SE"],
                )
            elif code in nordic:
                self.assertTrue(level.domicile)
                self.assertTrue(level.international)
                self.assertEqual(
                    sorted(c for z in level.zones for c in (z.country_codes or [])),
                    ["DK", "FI", "NO", "SE"],
                )
            elif code in international:
                self.assertFalse(level.domicile)
                self.assertTrue(level.international)
                # Unrestricted zone: no country list, flags do the gating.
                self.assertTrue(all(not z.country_codes for z in level.zones))
            else:  # pragma: no cover
                self.fail(f"unclassified product code: {code}")


if __name__ == "__main__":
    unittest.main()
