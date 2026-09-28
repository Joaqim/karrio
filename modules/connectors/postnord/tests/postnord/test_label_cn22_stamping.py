"""PostNord combined label + CN22 printouts: live fixtures, classification, seeds.

The combined fixtures are live export-letter (UX) captures: the ZPL from a
booking and from a by-printId fetch without ``definePrintout``, the PDF from the
same by-printId fetch. The lone CN22 PDF is the ``definePrintout=
onlyCustomsDeclarations`` capture already vendored as ``postnord_cn22.pdf``.
"""

import io
import base64
import unittest

import pypdf

import karrio.core.models as models
import karrio.core.utils.stamping as stamping

from postnord.test_cn22_stamping import KEYWORD, _read_b64

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


if __name__ == "__main__":
    unittest.main()
