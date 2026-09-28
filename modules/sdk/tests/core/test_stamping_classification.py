"""Document stamping: customs composition classification from section markers."""

import unittest

import karrio.core.metadata as metadata
import karrio.core.utils.stamping as stamping

from .stamping_helpers import providers

# Synthetic section markers for the carrier-neutral "acme" plugin.
ACME_SECTIONS = {
    "ZPL": {
        "cn22": "^FX ACME_CN22^FS",
        "label": "^FX ACME_LABEL^FS",
    },
    "PDF": {
        "cn22": ("ACME DECLARATION", "CN22"),
        "label": ("Acme letter",),
    },
}


def sectioned_provider(document_sections: dict = None, carrier: str = "acme"):
    return metadata.PluginMetadata(
        id=carrier, label=carrier, document_sections=document_sections
    )


class TestPluginSections(unittest.TestCase):
    def test_plugin_metadata_declares_no_sections_by_default(self):
        self.assertIsNone(
            metadata.PluginMetadata(id="acme", label="Acme").document_sections
        )

    def test_sections_resolve_from_the_carrier_plugin(self):
        with providers(sectioned_provider(ACME_SECTIONS)):
            self.assertEqual(stamping._carrier_sections("acme"), ACME_SECTIONS)

    def test_undeclaring_carrier_resolves_no_sections(self):
        with providers(sectioned_provider(), sectioned_provider(carrier="other")):
            self.assertEqual(stamping._carrier_sections("acme"), {})
            self.assertEqual(stamping._carrier_sections("unknown"), {})

    def test_no_carrier_never_loads_plugins(self):
        with providers() as collect:
            self.assertEqual(stamping._carrier_sections(None), {})
            self.assertEqual(stamping._carrier_sections("*"), {})

        collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
