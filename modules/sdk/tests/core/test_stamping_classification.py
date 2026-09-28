"""Document stamping: customs composition classification from section markers."""

import unittest

import karrio.core.models as models
import karrio.core.metadata as metadata
import karrio.core.utils.stamping as stamping

from .stamping_helpers import providers, zpl_doc_b64

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

# One ZPL format per composition: a single ^XA/^XZ whose field comments name
# the sections it carries, as a carrier composing label and CN22 emits them.
DECLARATION_SECTION = "\n".join(
    [
        "^FX ACME_CN22^FS",
        "^FO20,35",
        "^FDSender signature^FS",
    ]
)
LABEL_SECTION = "\n".join(
    [
        "^FX ACME_LABEL^FS",
        "^FO40,600",
        "^BY3^BCN,120,Y,N,N^FDRR123456785SE^FS",
    ]
)


def zpl_form(*sections: str) -> models.ShippingDocument:
    stream = "\n".join(["^XA", *sections, "^XZ"])
    return models.ShippingDocument(
        category="label", format="ZPL", base64=zpl_doc_b64(stream)
    )


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


class TestZplClassification(unittest.TestCase):
    def classify(self, document):
        return stamping.classify_customs_composition(document, sections=ACME_SECTIONS)

    def test_combined_label_and_declaration(self):
        result = self.classify(zpl_form(DECLARATION_SECTION, LABEL_SECTION))

        self.assertEqual(
            result,
            stamping.CustomsClassification(
                composition=stamping.CustomsComposition.label_with_declaration,
                kinds=("cn22", "label"),
                doc_type="label_cn22",
                page=None,
            ),
        )

    def test_lone_declaration(self):
        result = self.classify(zpl_form(DECLARATION_SECTION))

        self.assertEqual(
            result,
            stamping.CustomsClassification(
                composition=stamping.CustomsComposition.declaration,
                kinds=("cn22",),
                doc_type="cn22",
                page=None,
            ),
        )

    def test_label_without_declaration_is_not_customs_bearing(self):
        result = self.classify(zpl_form(LABEL_SECTION))

        self.assertEqual(result.composition, stamping.CustomsComposition.none)
        self.assertEqual(result.kinds, ("label",))
        self.assertIsNone(result.doc_type)
        self.assertIsNone(result.page)

    def test_document_without_markers_is_not_customs_bearing(self):
        result = self.classify(zpl_form("^FO10,10^GB100,100,2^FS"))

        self.assertEqual(result, stamping.CustomsClassification())
        self.assertEqual(result.composition, "none")

    def test_carrier_without_declared_sections_is_not_customs_bearing(self):
        document = zpl_form(DECLARATION_SECTION, LABEL_SECTION)

        with providers(sectioned_provider({"PDF": ACME_SECTIONS["PDF"]})):
            result = stamping.classify_customs_composition(document, carrier="acme")

        self.assertEqual(result.composition, stamping.CustomsComposition.none)

    def test_sections_resolve_from_the_carrier_plugin(self):
        document = zpl_form(DECLARATION_SECTION, LABEL_SECTION)

        with providers(sectioned_provider(ACME_SECTIONS)):
            result = stamping.classify_customs_composition(document, carrier="acme")

        self.assertEqual(result.doc_type, "label_cn22")

    def test_injected_sections_never_load_plugins(self):
        with providers() as collect:
            self.classify(zpl_form(DECLARATION_SECTION))

        collect.assert_not_called()

    def test_classification_leaves_the_document_unchanged(self):
        document = zpl_form(DECLARATION_SECTION, LABEL_SECTION)
        original = document.base64

        first = self.classify(document)
        second = self.classify(document)

        self.assertEqual(document.base64, original)
        self.assertEqual(first, second)

    def test_result_is_immutable(self):
        result = self.classify(zpl_form(DECLARATION_SECTION))

        with self.assertRaises(AttributeError):
            result.doc_type = "label_cn22"


if __name__ == "__main__":
    unittest.main()
