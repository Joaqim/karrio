"""DHL Freight references-payload regression tests.

The SDK references payload feeds the dashboard's generic connection-config
renderer, which handles only string, string-enum, and boolean types. An
enum class whose name contains "Address" trips the Address-model heuristic
in ``karrio.references.parse_type`` and emits ``type: "Address"``, which
the renderer silently drops — the Connection configuration dialog then
shows no address-validation option.
"""

import unittest

import karrio.references as references


class TestDHLFreightSwedenReferences(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_address_validation_connection_config_classifies_as_string_enum(self):
        config = (
            references.collect_references()["connection_configs"]["dhl_freight_sweden"][
                "address_validation"
            ]
        )

        self.assertEqual(config["type"], "string")
        self.assertEqual(config["enum"], ["off", "warn", "enforce"])


if __name__ == "__main__":
    unittest.main()
