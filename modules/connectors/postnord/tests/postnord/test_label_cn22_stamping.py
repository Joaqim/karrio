"""PostNord combined label + CN22 printouts: live fixtures, classification, seeds.

The combined fixtures are live export-letter (UX) captures: the ZPL from a
booking and from a by-printId fetch without ``definePrintout``, the PDF from the
same by-printId fetch. The two-page PDF is a sandbox export-letter booking
printout: a "PostNord Tracked Letter" label on page 1 and an upright CN22 on
page 2. The lone CN22 PDF is the ``definePrintout=onlyCustomsDeclarations``
capture already vendored as ``postnord_cn22.pdf``.
"""

import io
import re
import base64
import unittest

import pypdf
from pypdf.generic import ArrayObject, ContentStream

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
TWO_PAGE_PDF_FIXTURE = "postnord_label_cn22_booking_two_pages.pdf"
LONE_ZPL_FIXTURE = "postnord_cn22.zpl"
LONE_PDF_FIXTURE = "postnord_cn22.pdf"

ZPL_CN22_MARKER = "^FX CUSTOMS_CN22_ROTATED^FS"
ZPL_LABEL_MARKER = "^FX SE_INTERNATIONAL_LETTER_LABEL^FS"
PDF_CN22_TEXT = ("CUSTOMS DECLARATION", "CN22")
PDF_LABEL_TEXT = ("Brev utrikes", "Parcel ID")
PDF_TRACKED_LETTER_TEXT = ("PostNord Tracked Letter", "Item-ID")
PDF_FIXTURES = (COMBINED_PDF_FIXTURE, TWO_PAGE_PDF_FIXTURE, LONE_PDF_FIXTURE)


def _document(name: str, document_format: str) -> models.ShippingDocument:
    return models.ShippingDocument(
        category="label", format=document_format, base64=_read_b64(name)
    )


def _zpl_stream(name: str) -> str:
    return base64.b64decode(_read_b64(name)).decode("utf-8")


def _pdf_pages(document_b64: str):
    return pypdf.PdfReader(io.BytesIO(base64.b64decode(document_b64))).pages


def _page_text(document_b64: str, page: int = 1) -> str:
    # PostNord's text runs break mid-phrase ("CUSTOMS \nDECLARATIONCN22").
    return " ".join(_pdf_pages(document_b64)[page - 1].extract_text().split())


def _page_mm(page) -> tuple:
    return tuple(
        round(float(value) * 25.4 / 72.0, 1)
        for value in (page.mediabox.width, page.mediabox.height)
    )


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
        self.assertEqual(stamping._detect_paper_variant(document.base64, "PDF"), "A4")
        for marker in PDF_CN22_TEXT + PDF_LABEL_TEXT:
            self.assertIn(marker, text)
        self.assertLess(text.index("CUSTOMS DECLARATION"), text.index("Brev utrikes"))

    def test_two_page_pdf_fixture_is_a_tracked_letter_label_then_a_cn22(self):
        document = _document(TWO_PAGE_PDF_FIXTURE, "PDF")
        pages = _pdf_pages(document.base64)
        label, cn22 = _page_text(document.base64, 1), _page_text(document.base64, 2)

        self.assertEqual(len(pages), 2)
        self.assertEqual([_page_mm(page) for page in pages], [(210.0, 297.0)] * 2)
        self.assertEqual(stamping._detect_paper_variant(document.base64, "PDF"), "A4")
        for marker in PDF_TRACKED_LETTER_TEXT + ("Cust. No", "DELIVERY CONFIRMATION"):
            self.assertIn(marker, label)
        for marker in PDF_CN22_TEXT + PDF_LABEL_TEXT + (KEYWORD,):
            self.assertNotIn(marker, label)
        for marker in PDF_CN22_TEXT + (KEYWORD,):
            self.assertIn(marker, cn22)
        for marker in PDF_LABEL_TEXT + PDF_TRACKED_LETTER_TEXT:
            self.assertNotIn(marker, cn22)

    def test_tracked_letter_markers_occur_on_no_cn22_page(self):
        for name in PDF_FIXTURES:
            document = _document(name, "PDF")
            for page in range(1, len(_pdf_pages(document.base64)) + 1):
                text = _page_text(document.base64, page)
                if "CUSTOMS DECLARATION" not in text:
                    continue
                with self.subTest(fixture=name, page=page):
                    for marker in PDF_TRACKED_LETTER_TEXT:
                        self.assertNotIn(marker, text)

    def test_lone_pdf_fixture_is_one_a4_page_without_label_text(self):
        document = _document(LONE_PDF_FIXTURE, "PDF")
        text = _page_text(document.base64)

        self.assertEqual(len(_pdf_pages(document.base64)), 1)
        self.assertEqual(stamping._detect_paper_variant(document.base64, "PDF"), "A4")
        for marker in PDF_CN22_TEXT:
            self.assertIn(marker, text)
        for marker in PDF_LABEL_TEXT + PDF_TRACKED_LETTER_TEXT:
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
                "PDF": {
                    "cn22": PDF_CN22_TEXT,
                    "label": lib.AnyOf(PDF_LABEL_TEXT, PDF_TRACKED_LETTER_TEXT),
                },
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

    def test_two_page_pdf_fixture_classifies_as_label_cn22_on_page_two(self):
        result = lib.classify_customs_composition(
            _document(TWO_PAGE_PDF_FIXTURE, "PDF"), carrier="postnord"
        )

        self.assertEqual(
            result,
            lib.CustomsClassification(
                composition=COMBINED,
                kinds=("cn22", "label"),
                doc_type="label_cn22",
                page=2,
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

                self.assertEqual(zpl[label_start:close], original[label_start:close])
                self.assertEqual(zpl[:close], original[:close])
                self.assertEqual(zpl[close:], _stamp_field(zpl) + original[close:])
                self.assertIn("^BCR,95,N,N,N,N", zpl[label_start:close])


# Measured on the combined page (postnord_label_cn22_printid.pdf) with pypdf.
# The page draws the whole printout as one /Form1 XObject, the 839 x 1518-dot
# label frame at 203 dpi, placed by a pure translation; label dots map to form
# points at 72/203 pt per dot with the label y axis running down from the
# form's top edge.
DOT_PT = 72.0 / 203.0
PAGE_HEIGHT_PT = 841.8898
FORM_ORIGIN_PT = (148.84964, 151.74292)
FORM_HEIGHT_PT = 538.40393
# Landmarks in form points: the keyword text matrix origin and the CN22 box's
# outer bottom rule. They sit at label (25, 35) and y 695 dots, the landmarks
# of the lone CN22 form the signature strip was measured against.
KEYWORD_TM_PT = (8.867, 525.9902)
CN22_BOX_BOTTOM_RULE_PT = 291.9015
# The signature strip in label dots: x 6.63-67.53, y 302.97-695.44, its bottom
# edge on the box's bottom rule. On this page it spans x 53.34-60.96 mm and
# y 91.44-140.55 mm, the same page region as the lone CN22 page.
STRIP_LABEL_DOTS = ((6.63, 67.53), (302.97, 695.44))


def _label_dots(form_x: float, form_y: float):
    return form_x / DOT_PT, (FORM_HEIGHT_PT - form_y) / DOT_PT


def _page_mm_x(label_x: float) -> float:
    return (FORM_ORIGIN_PT[0] + label_x * DOT_PT) * 25.4 / 72.0


def _page_mm_y(label_y: float) -> float:
    form_top_pt = PAGE_HEIGHT_PT - FORM_ORIGIN_PT[1] - FORM_HEIGHT_PT
    return (form_top_pt + label_y * DOT_PT) * 25.4 / 72.0


def _strip_mm():
    (x_lo, x_hi), (y_lo, y_hi) = STRIP_LABEL_DOTS
    return (_page_mm_x(x_lo), _page_mm_x(x_hi)), (_page_mm_y(y_lo), _page_mm_y(y_hi))


def _pt(mm: float) -> float:
    return mm * 72.0 / 25.4


def _form_page(document_b64: str):
    page = _pdf_pages(document_b64)[0]
    form = page["/Resources"]["/XObject"]["/Form1"].get_object()
    return page, form


def _text_runs(page):
    runs = []
    page.extract_text(
        visitor_text=lambda text, cm, tm, font, size: (
            runs.append((" ".join(text.split()), tm[4], tm[5]))
            if text.strip()
            else None
        )
    )
    return runs


def _overlay_bounds(document_b64: str):
    """Page-point bounds of every quarter-turned stamp overlay.

    Each merged overlay is a rotated ``cm`` followed by its clip ``re``; the
    carrier's own page-level ``cm`` is a pure translation and is skipped.
    """
    page = _pdf_pages(document_b64)[0]
    contents = page["/Contents"].get_object()
    streams = contents if isinstance(contents, ArrayObject) else [contents]
    operations = [
        (tuple(float(value) for value in operands), operator)
        for element in streams
        for operands, operator in ContentStream(
            element.get_object(), page.pdf
        ).operations
        if operator in (b"cm", b"re")
    ]
    placed = [
        (matrix, clip[2:])
        for (matrix, op), (clip, next_op) in zip(operations, operations[1:])
        if op == b"cm" and next_op == b"re"
    ]
    return [
        (
            min(xs := [e + a * u + c * v for u in (0, w) for v in (0, h)]),
            max(xs),
            min(ys := [f + b * u + d * v for u in (0, w) for v in (0, h)]),
            max(ys),
        )
        for (a, b, c, d, e, f), (w, h) in placed
        if abs(a) < 1e-6 and b < 0
    ]


class TestLabelCn22PdfMeasurement(unittest.TestCase):
    def test_combined_page_places_the_label_frame_by_translation(self):
        page, form = _form_page(_read_b64(COMBINED_PDF_FIXTURE))
        ((operands, _),) = [
            (operands, operator)
            for operands, operator in ContentStream(
                page["/Contents"].get_object(), page.pdf
            ).operations
            if operator == b"cm"
        ]

        self.assertEqual(
            [round(float(value), 5) for value in operands],
            [1.0, 0.0, 0.0, 1.0, *FORM_ORIGIN_PT],
        )
        self.assertAlmostEqual(float(form["/BBox"][3]), FORM_HEIGHT_PT, places=5)
        self.assertAlmostEqual(float(form["/BBox"][2]) / DOT_PT, 839.0, places=2)
        self.assertAlmostEqual(FORM_HEIGHT_PT / DOT_PT, 1518.0, places=2)

    def test_combined_page_landmarks_match_the_lone_cn22_form(self):
        page, form = _form_page(_read_b64(COMBINED_PDF_FIXTURE))
        (keyword_run,) = [run for run in _text_runs(page) if run[0] == KEYWORD]
        rule_points = [
            tuple(float(value) for value in operands)
            for operands, operator in ContentStream(form, page.pdf).operations
            if operator == b"l"
        ]

        self.assertAlmostEqual(keyword_run[1], KEYWORD_TM_PT[0], places=3)
        self.assertAlmostEqual(keyword_run[2], KEYWORD_TM_PT[1], places=3)
        for measured, expected in zip(_label_dots(*KEYWORD_TM_PT), (25.0, 35.0)):
            self.assertAlmostEqual(measured, expected, places=2)
        self.assertIn(CN22_BOX_BOTTOM_RULE_PT, [round(y, 4) for _, y in rule_points])
        self.assertAlmostEqual(
            _label_dots(0.0, CN22_BOX_BOTTOM_RULE_PT)[1], 695.0, places=2
        )
        self.assertAlmostEqual(STRIP_LABEL_DOTS[1][1], 695.0, delta=0.5)

    def test_box_bottom_rule_separates_the_cn22_and_label_sections(self):
        runs = _text_runs(_form_page(_read_b64(COMBINED_PDF_FIXTURE))[0])
        above = {text for text, _, y in runs if y > CN22_BOX_BOTTOM_RULE_PT}
        below = {text for text, _, y in runs if y < CN22_BOX_BOTTOM_RULE_PT}

        self.assertTrue({KEYWORD, "CUSTOMS", "Sweden Post"} <= above)
        self.assertTrue({"Brev utrikes", "Parcel ID"} <= below)
        self.assertFalse({"Brev utrikes", "Parcel ID"} & above)
        self.assertFalse({KEYWORD, "CUSTOMS"} & below)


class TestLabelCn22PdfStamp(unittest.TestCase):
    def test_pdf_seed_resolves_to_the_measured_strip(self):
        (x_lo, x_hi), (y_lo, y_hi) = _strip_mm()
        placement = stamping._default_registry("postnord/label_cn22/PDF/A4")

        self.assertEqual(placement.rotation, 90)
        self.assertEqual(placement.page, 1)
        self.assertAlmostEqual(placement.x, x_lo, places=2)
        self.assertAlmostEqual(placement.y, y_lo, places=2)
        # Under rotation 90 the rendered rectangle is `height` wide and
        # `width` tall hanging down-right from the anchor.
        self.assertAlmostEqual(placement.x + placement.height, x_hi, places=2)
        self.assertAlmostEqual(placement.y + placement.width, y_hi, places=2)

    def test_pdf_seed_is_the_first_combined_measurement(self):
        self.assertEqual(postnord_stamping.LABEL_CN22_SEED.revision, 1)

    def test_pdf_seed_does_not_leak_to_letter(self):
        self.assertIsNone(stamping._default_registry("postnord/label_cn22/PDF/LETTER"))

    def test_classified_combined_pdf_stamps_within_the_strip_on_page_one(self):
        document = _document(COMBINED_PDF_FIXTURE, "PDF")
        result = lib.classify_customs_composition(document, carrier="postnord")

        stamped = lib.stamp_document(
            document,
            image=_signature_png_b64(),
            date="2026-09-28",
            carrier="postnord",
            doc_type=result.doc_type,
            page=result.page,
        )

        (x_lo, x_hi), (y_lo, y_hi) = _strip_mm()
        strip_left, strip_right = _pt(x_lo), _pt(x_hi)
        strip_bottom, strip_top = PAGE_HEIGHT_PT - _pt(y_hi), PAGE_HEIGHT_PT - _pt(y_lo)
        tolerance = 0.05
        bounds = _overlay_bounds(stamped.base64)

        self.assertEqual((result.doc_type, result.page), ("label_cn22", 1))
        self.assertEqual(len(_pdf_pages(stamped.base64)), 1)
        self.assertEqual(len(bounds), 2)
        for left, right, bottom, top in bounds:
            self.assertGreaterEqual(left, strip_left - tolerance)
            self.assertLessEqual(right, strip_right + tolerance)
            self.assertGreaterEqual(bottom, strip_bottom - tolerance)
            self.assertLessEqual(top, strip_top + tolerance)

    def test_stamp_leaves_the_label_section_untouched(self):
        document = _document(COMBINED_PDF_FIXTURE, "PDF")
        page, _ = _form_page(document.base64)
        label_top_pt = FORM_ORIGIN_PT[1] + max(
            y for _, _, y in _text_runs(page) if y < CN22_BOX_BOTTOM_RULE_PT
        )

        stamped = lib.stamp_document(
            document,
            image=_signature_png_b64(),
            date="2026-09-28",
            carrier="postnord",
            doc_type="label_cn22",
        )

        self.assertGreater(
            min(bottom for _, _, bottom, _ in _overlay_bounds(stamped.base64)),
            label_top_pt,
        )
        self.assertEqual(_text_runs(_form_page(stamped.base64)[0]), _text_runs(page))


if __name__ == "__main__":
    unittest.main()
