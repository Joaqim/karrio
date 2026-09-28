"""Document stamping: customs composition classification from section markers."""

import unittest

import karrio.core.models as models
import karrio.core.metadata as metadata
import karrio.core.utils.stamping as stamping

from .stamping_helpers import (
    b64,
    blank_pdf_b64,
    page_count,
    png_document,
    providers,
    signature_png_b64,
    text_pdf_b64,
    zpl_doc_b64,
)

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


DECLARATION_LINES = ["ACME DECLARATION", "CN22", "Sender signature"]
LABEL_LINES = ["Acme letter", "RR123456785SE"]


def pdf_form(*pages) -> models.ShippingDocument:
    return models.ShippingDocument(
        category="label", format="PDF", base64=text_pdf_b64(*pages)
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


class TestPdfClassification(unittest.TestCase):
    def classify(self, document):
        return stamping.classify_customs_composition(document, sections=ACME_SECTIONS)

    def test_combined_label_and_declaration_on_one_page(self):
        result = self.classify(pdf_form(DECLARATION_LINES + LABEL_LINES))

        self.assertEqual(
            result,
            stamping.CustomsClassification(
                composition=stamping.CustomsComposition.label_with_declaration,
                kinds=("cn22", "label"),
                doc_type="label_cn22",
                page=1,
            ),
        )

    def test_lone_declaration(self):
        result = self.classify(pdf_form(DECLARATION_LINES))

        self.assertEqual(
            result,
            stamping.CustomsClassification(
                composition=stamping.CustomsComposition.declaration,
                kinds=("cn22",),
                doc_type="cn22",
                page=1,
            ),
        )

    def test_multi_page_names_the_declaration_page(self):
        result = self.classify(
            pdf_form(LABEL_LINES, DECLARATION_LINES, DECLARATION_LINES)
        )

        self.assertEqual(
            result.composition, stamping.CustomsComposition.label_with_declaration
        )
        self.assertEqual(result.page, 2)

    def test_lone_declaration_after_an_unmarked_page(self):
        result = self.classify(pdf_form(["Terms and conditions"], DECLARATION_LINES))

        self.assertEqual(result.doc_type, "cn22")
        self.assertEqual(result.page, 2)

    def test_marker_broken_across_lines_still_matches(self):
        result = self.classify(pdf_form(["ACME", "DECLARATION", "CN22"]))

        self.assertEqual(result.doc_type, "cn22")

    def test_text_matching_no_marker_is_not_customs_bearing(self):
        result = self.classify(pdf_form(["Commercial invoice"]))

        self.assertEqual(result, stamping.CustomsClassification())

    def test_label_without_declaration_is_not_customs_bearing(self):
        result = self.classify(pdf_form(LABEL_LINES))

        self.assertEqual(result.composition, stamping.CustomsComposition.none)
        self.assertEqual(result.kinds, ("label",))
        self.assertIsNone(result.page)

    def test_partial_declaration_markers_are_not_customs_bearing(self):
        result = self.classify(pdf_form(["ACME DECLARATION"] + LABEL_LINES))

        self.assertEqual(result.composition, stamping.CustomsComposition.none)

    def test_declaration_markers_split_across_pages_do_not_match(self):
        result = self.classify(pdf_form(["ACME DECLARATION"], ["CN22"]))

        self.assertEqual(result.composition, stamping.CustomsComposition.none)

    def test_pages_without_text_are_not_customs_bearing(self):
        document = models.ShippingDocument(
            category="label", format="PDF", base64=blank_pdf_b64(pages=2)
        )

        self.assertEqual(self.classify(document), stamping.CustomsClassification())

    def test_unparseable_pdf_is_not_customs_bearing(self):
        document = models.ShippingDocument(
            category="label", format="PDF", base64=b64(b"%PDF-1.4 garbage")
        )

        self.assertEqual(self.classify(document), stamping.CustomsClassification())

    def test_classification_leaves_the_document_unchanged(self):
        document = pdf_form(DECLARATION_LINES + LABEL_LINES)
        original = document.base64

        self.classify(document)

        self.assertEqual(document.base64, original)
        self.assertEqual(page_count(document.base64), 1)


class TestUnsupportedFormats(unittest.TestCase):
    def test_png_is_rejected_naming_the_format(self):
        with self.assertRaisesRegex(ValueError, r"detected as 'PNG'"):
            stamping.classify_customs_composition(
                png_document(), sections=ACME_SECTIONS
            )

    def test_detected_format_outranks_the_declared_format(self):
        document = models.ShippingDocument(
            category="label", format="ZPL", base64=signature_png_b64()
        )

        with self.assertRaisesRegex(ValueError, r"detected as 'PNG'"):
            stamping.classify_customs_composition(document, sections=ACME_SECTIONS)

    def test_unrecognized_bytes_are_rejected(self):
        document = models.ShippingDocument(
            category="label", format="GIF", base64=b64(b"GIF89a not a label")
        )

        with self.assertRaisesRegex(ValueError, r"detected as 'GIF'"):
            stamping.classify_customs_composition(document, sections=ACME_SECTIONS)


if __name__ == "__main__":
    unittest.main()
