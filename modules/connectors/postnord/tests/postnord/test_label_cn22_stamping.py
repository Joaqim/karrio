"""PostNord combined label + CN22 printouts: live fixtures, classification, seeds.

The combined fixtures are live export-letter (UX) captures: the ZPL from a
booking and from a by-printId fetch without ``definePrintout``, the PDF from the
same by-printId fetch. The lone CN22 PDF is the ``definePrintout=
onlyCustomsDeclarations`` capture already vendored as ``postnord_cn22.pdf``.
"""

import io
import re
import base64
import unittest

import pypdf

import karrio.lib as lib
import karrio.references as references
import karrio.core.models as models
import karrio.core.utils.stamping as stamping
import karrio.providers.postnord.stamping as postnord_stamping

from postnord.test_cn22_stamping import (
    KEYWORD,
    _decode_zpl,
    _grf_fields,
    _read_b64,
    _signature_png_b64,
)

COMBINED_ZPL_FIXTURES = (
    "postnord_label_cn22_booking.zpl",
    "postnord_label_cn22_printid.zpl",
)
COMBINED_PDF_FIXTURE = "postnord_label_cn22_printid.pdf"
LONE_ZPL_FIXTURE = "postnord_cn22.zpl"
LONE_PDF_FIXTURE = "postnord_cn22.pdf"

ZPL_CN22_MARKER = "^FX CUSTOMS_CN22_ROTATED^FS"
ZPL_LABEL_MARKER = "^FX SE_INTERNATIONAL_LETTER_LABEL^FS"
PDF_CN22_TEXT = ("CUSTOMS DECLARATION", "CN22")
PDF_LABEL_TEXT = ("Brev utrikes", "Parcel ID")


def _document(name: str, document_format: str) -> models.ShippingDocument:
    return models.ShippingDocument(
        category="label", format=document_format, base64=_read_b64(name)
    )


def _zpl_stream(name: str) -> str:
    return base64.b64decode(_read_b64(name)).decode("utf-8")


def _pdf_pages(document_b64: str):
    return pypdf.PdfReader(io.BytesIO(base64.b64decode(document_b64))).pages


def _page_text(document_b64: str) -> str:
    # PostNord's text runs break mid-phrase ("CUSTOMS \nDECLARATIONCN22").
    return " ".join(_pdf_pages(document_b64)[0].extract_text().split())


class TestPostnordCombinedFixtures(unittest.TestCase):
    def test_combined_zpl_fixtures_are_one_format_with_both_sections(self):
        for name in COMBINED_ZPL_FIXTURES:
            with self.subTest(fixture=name):
                stream = _zpl_stream(name)

                self.assertTrue(stream.startswith("^XA"))
                self.assertEqual(stream.count("^XZ"), 1)
                self.assertEqual(stream.count(ZPL_CN22_MARKER), 1)
                self.assertEqual(stream.count(ZPL_LABEL_MARKER), 1)
                self.assertLess(
                    stream.index(ZPL_CN22_MARKER), stream.index(ZPL_LABEL_MARKER)
                )
                self.assertEqual(stream.count(KEYWORD), 1)

    def test_combined_zpl_cn22_section_carries_no_label_marker(self):
        for name in COMBINED_ZPL_FIXTURES:
            with self.subTest(fixture=name):
                stream = _zpl_stream(name)
                cn22_section = stream[: stream.index(ZPL_LABEL_MARKER)]

                self.assertIn(KEYWORD, cn22_section)
                self.assertNotIn("SE_INTERNATIONAL_LETTER_LABEL", cn22_section)
                # The label section carries PostNord's own ^GFA logo graphics.
                self.assertNotIn("^GFA", cn22_section)

    def test_lone_zpl_fixture_carries_no_label_section(self):
        stream = _zpl_stream(LONE_ZPL_FIXTURE)

        self.assertEqual(stream.count(ZPL_CN22_MARKER), 1)
        self.assertNotIn(ZPL_LABEL_MARKER, stream)

    def test_combined_pdf_fixture_is_one_a4_page_with_both_sections(self):
        document = _document(COMBINED_PDF_FIXTURE, "PDF")
        text = _page_text(document.base64)

        self.assertEqual(len(_pdf_pages(document.base64)), 1)
        self.assertEqual(
            stamping._detect_paper_variant(document.base64, "PDF"), "A4"
        )
        for marker in PDF_CN22_TEXT + PDF_LABEL_TEXT:
            self.assertIn(marker, text)
        self.assertLess(text.index("CUSTOMS DECLARATION"), text.index("Brev utrikes"))

    def test_lone_pdf_fixture_is_one_a4_page_without_label_text(self):
        document = _document(LONE_PDF_FIXTURE, "PDF")
        text = _page_text(document.base64)

        self.assertEqual(len(_pdf_pages(document.base64)), 1)
        self.assertEqual(
            stamping._detect_paper_variant(document.base64, "PDF"), "A4"
        )
        for marker in PDF_CN22_TEXT:
            self.assertIn(marker, text)
        for marker in PDF_LABEL_TEXT:
            self.assertNotIn(marker, text)


COMBINED = lib.CustomsComposition.label_with_declaration
DECLARATION = lib.CustomsComposition.declaration


class TestPostnordDocumentSections(unittest.TestCase):
    def test_plugin_metadata_declares_the_document_sections(self):
        sections = references.collect_providers_data()["postnord"].document_sections

        self.assertIs(sections, postnord_stamping.DOCUMENT_SECTIONS)
        self.assertEqual(
            sections,
            {
                "ZPL": {"cn22": ZPL_CN22_MARKER, "label": ZPL_LABEL_MARKER},
                "PDF": {"cn22": PDF_CN22_TEXT, "label": PDF_LABEL_TEXT},
            },
        )

    def test_combined_zpl_fixtures_classify_as_label_cn22(self):
        for name in COMBINED_ZPL_FIXTURES:
            with self.subTest(fixture=name):
                result = lib.classify_customs_composition(
                    _document(name, "ZPL"), carrier="postnord"
                )

                self.assertEqual(
                    result,
                    lib.CustomsClassification(
                        composition=COMBINED,
                        kinds=("cn22", "label"),
                        doc_type="label_cn22",
                        page=None,
                    ),
                )

    def test_combined_pdf_fixture_classifies_as_label_cn22_on_page_one(self):
        result = lib.classify_customs_composition(
            _document(COMBINED_PDF_FIXTURE, "PDF"), carrier="postnord"
        )

        self.assertEqual(
            result,
            lib.CustomsClassification(
                composition=COMBINED,
                kinds=("cn22", "label"),
                doc_type="label_cn22",
                page=1,
            ),
        )

    def test_lone_zpl_fixture_classifies_as_cn22(self):
        result = lib.classify_customs_composition(
            _document(LONE_ZPL_FIXTURE, "ZPL"), carrier="postnord"
        )

        self.assertEqual(
            result,
            lib.CustomsClassification(
                composition=DECLARATION, kinds=("cn22",), doc_type="cn22", page=None
            ),
        )

    def test_lone_pdf_fixture_classifies_as_cn22_on_page_one(self):
        result = lib.classify_customs_composition(
            _document(LONE_PDF_FIXTURE, "PDF"), carrier="postnord"
        )

        self.assertEqual(
            result,
            lib.CustomsClassification(
                composition=DECLARATION, kinds=("cn22",), doc_type="cn22", page=1
            ),
        )

    def test_zpl_label_without_the_cn22_section_is_not_customs_bearing(self):
        stream = _zpl_stream(COMBINED_ZPL_FIXTURES[0])
        label_only = (
            stream[: stream.index(ZPL_CN22_MARKER)]
            + stream[stream.index(ZPL_LABEL_MARKER) :]
        )
        document = models.ShippingDocument(
            category="label",
            format="ZPL",
            base64=base64.b64encode(label_only.encode("utf-8")).decode("utf-8"),
        )

        result = lib.classify_customs_composition(document, carrier="postnord")

        self.assertEqual(result.composition, lib.CustomsComposition.none)
        self.assertEqual(result.kinds, ("label",))
        self.assertIsNone(result.doc_type)


def _stamped_zpl(name: str, doc_type: str) -> str:
    stamped = lib.stamp_document(
        _document(name, "ZPL"),
        image=_signature_png_b64(),
        date="2026-09-28",
        carrier="postnord",
        doc_type=doc_type,
    )
    return _decode_zpl(stamped.base64)


def _stamp_field(zpl: str) -> str:
    (field,) = re.findall(r"\^FO\d+,\d+\^GFA,[0-9,A-F]*\^FS", zpl)
    return field


class TestLabelCn22ZplStamp(unittest.TestCase):
    def test_zpl_seed_reuses_the_cn22_keyword_anchor(self):
        seeds = references.collect_providers_data()["postnord"].stamp_seeds
        combined, lone = seeds["label_cn22/ZPL/*"], seeds["cn22/ZPL/*"]

        self.assertEqual(combined.keyword, KEYWORD)
        self.assertEqual(combined.keyword_placement, lone.keyword_placement)

    def test_combined_zpl_stamps_at_the_lone_cn22_placement(self):
        lone_field = _stamp_field(_stamped_zpl(LONE_ZPL_FIXTURE, "cn22"))
        ((lone_x, lone_y, *_),) = _grf_fields(lone_field)
        self.assertEqual((lone_x, lone_y), (7, 303))

        for name in COMBINED_ZPL_FIXTURES:
            with self.subTest(fixture=name):
                zpl = _stamped_zpl(name, "label_cn22")

                self.assertEqual(_stamp_field(zpl), lone_field)

    def test_combined_zpl_label_section_is_byte_identical(self):
        # The backend splices its one ^GFA field immediately before ^XZ, so
        # everything the carrier emitted, the label section from its marker
        # up to ^XZ included, keeps its bytes and offsets.
        for name in COMBINED_ZPL_FIXTURES:
            with self.subTest(fixture=name):
                original = _zpl_stream(name)
                zpl = _stamped_zpl(name, "label_cn22")
                close = original.rindex("^XZ")
                label_start = original.index(ZPL_LABEL_MARKER)

                self.assertEqual(
                    zpl[label_start:close], original[label_start:close]
                )
                self.assertEqual(zpl[:close], original[:close])
                self.assertEqual(
                    zpl[close:], _stamp_field(zpl) + original[close:]
                )
                self.assertIn("^BCR,95,N,N,N,N", zpl[label_start:close])


if __name__ == "__main__":
    unittest.main()
