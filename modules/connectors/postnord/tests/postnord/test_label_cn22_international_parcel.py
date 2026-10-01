"""PostNord International Parcel (service 91) label + CN22 printouts.

Both fixtures are live 2026-09-28 bookings of ``postnord_postpaket_utrikes``.
The ZPL is two formats: the parcel label (``NORDIC_SHIPPING_LABEL``), then an
upright CN22 (``CUSTOMS_CN22_V2``, ``^FWN``, ``^LL840``). The PDF is two A4
pages: the parcel label, then the CN22.
"""

import re
import base64
import unittest

from pypdf.generic import ContentStream

import karrio.lib as lib
import karrio.core.models as models

from postnord.test_cn22_stamping import (
    KEYWORD,
    _decode_zpl,
    _grf_fields,
    _read_b64,
    _signature_png_b64,
)
from postnord.test_label_cn22_stamping import (
    COMBINED_ZPL_FIXTURES,
    DOT_PT,
    LONE_ZPL_FIXTURE,
    PAGE_HEIGHT_PT,
    PDF_CN22_TEXT,
    PDF_FIXTURES,
    PDF_LABEL_TEXT,
    PDF_TRACKED_LETTER_TEXT,
    STRIP_LABEL_DOTS,
    _document,
    _overlays,
    _page_mm,
    _page_text,
    _pdf_pages,
    _pt,
    _reads_left_to_right,
    _text_runs,
    _within,
    _zpl_stream,
)

ZPL_FIXTURE = "postnord_label_cn22_international_parcel.zpl"
PDF_FIXTURE = "postnord_label_cn22_international_parcel.pdf"

ZPL_CN22_MARKERS = ("^FX CUSTOMS_CN22_ROTATED^FS", "^FX CUSTOMS_CN22_V2^FS")
ZPL_LABEL_MARKERS = (
    "^FX SE_INTERNATIONAL_LETTER_LABEL^FS",
    "^FX NORDIC_SHIPPING_LABEL^FS",
)
ZPL_V2_MARKER = ZPL_CN22_MARKERS[1]
ZPL_NORDIC_MARKER = ZPL_LABEL_MARKERS[1]
PDF_INTERNATIONAL_PARCEL_TEXT = ("International Parcel", "Item-ID")
ALL_ZPL_FIXTURES = COMBINED_ZPL_FIXTURES + (LONE_ZPL_FIXTURE, ZPL_FIXTURE)
ALL_PDF_FIXTURES = PDF_FIXTURES + (PDF_FIXTURE,)

COMBINED = lib.CustomsClassification(
    composition=lib.CustomsComposition.label_with_declaration,
    kinds=("cn22", "label"),
    doc_type="label_cn22",
    page=None,
)

# The upright V2 CN22 format measured in label dots from a Labelary render
# (api.labelary.com, 8 dpmm = 203 dpi) of its static fields: the box
# (^FO10,15 ^GB820,820), the certification lines at ^FO25,690/710/730 and the
# keyword at ^FO25,785, all in font 0 at 18 dots. Ink rows and columns are
# inclusive. The signature area runs along the keyword line from past its
# text to the box's right rule, and across from below the certification text
# to above the box's bottom rule, within the format's ^LL840.
V2_LABEL_LENGTH = 840
V2_BOX_RULE_COLUMNS = (10, 829)
V2_BOX_BOTTOM_RULE_ROW = 834
V2_CERTIFICATION_INK_BOTTOM = 745
V2_KEYWORD_INK = ((26, 229), (784, 800))
V2_SIGNATURE_AREA = (
    (V2_KEYWORD_INK[0][1] + 1, V2_BOX_RULE_COLUMNS[1] - 1),
    (V2_CERTIFICATION_INK_BOTTOM + 1, V2_BOX_BOTTOM_RULE_ROW - 1),
)

# The rotated letter CN22 (^FWR, keyword ^FO20,35 in font 0 at 20 dots): the
# keyword's ink ends at label y 263 in the same kind of Labelary render, so
# the measured strip (STRIP_LABEL_DOTS, from y 302.97) clears the text.
ROTATED_KEYWORD_INK_END_Y = 263

# Page 2 of the International Parcel PDF, measured with pypdf: the CN22 is
# /Form2 (BBox 297.57635 x 538.40393 pt, the 839 x 1518-dot label frame)
# placed by a pure translation. In form points: the keyword text matrix
# origin, the CN22 box's inner left, right and bottom rules, and the baseline
# of the certification text's last line. Ink extents, page millimetres from
# the top-left, come from a 300 dpi pdftoppm render of page 2.
PARCEL_FORM_ORIGIN_PT = (148.84964, 151.74292)
PARCEL_FORM_SIZE_PT = (297.57635, 538.40393)
PARCEL_KEYWORD_TM_PT = (8.867, 255.3695)
PARCEL_BOX_INNER_RULES_PT = {"left": 3.9015, "right": 294.0296, "bottom": 242.601}
PARCEL_CERTIFICATION_BASELINE_PT = 274.8769
PARCEL_CERTIFICATION_INK_MM = 146.981
PARCEL_KEYWORD_INK_RIGHT_MM = 85.513


def _formats(stream: str):
    """The stream's ``^XA``...``^XZ`` formats, each ending with its ``^XZ``."""
    return [part + "^XZ" for part in stream.split("^XZ")[:-1]]


def _grf_ink_bounds(field):
    """Inclusive label-dot bounds of the black pixels of a ``^GFA`` field."""
    x, y, total, _, bytes_per_row, hexdata = field
    rows = [
        bin(int(hexdata[offset : offset + bytes_per_row * 2], 16))[2:].zfill(
            bytes_per_row * 8
        )
        for offset in range(0, total * 2, bytes_per_row * 2)
    ]
    columns = [
        column for row in rows for column, bit in enumerate(row) if bit == "1"
    ]
    ink_rows = [index for index, row in enumerate(rows) if "1" in row]
    return (
        (x + min(columns), x + max(columns)),
        (y + min(ink_rows), y + max(ink_rows)),
    )


def _grf_extent(field):
    """The field's raster rows and padded row width in dots."""
    _, _, total, _, bytes_per_row, _ = field
    return bytes_per_row * 8, total // bytes_per_row


def _stamp(name: str, document_format: str):
    document = _document(name, document_format)
    result = lib.classify_customs_composition(document, carrier="postnord")
    stamped = lib.stamp_document(
        document,
        image=_signature_png_b64(),
        date="2026-09-28",
        carrier="postnord",
        doc_type=result.doc_type,
        page=result.page,
    )
    return document, result, stamped


def _assert_dots_within(test, bounds, region, tolerance=0.5):
    (x_lo, x_hi), (y_lo, y_hi) = bounds
    (region_x_lo, region_x_hi), (region_y_lo, region_y_hi) = region
    test.assertGreaterEqual(x_lo, region_x_lo - tolerance)
    test.assertLessEqual(x_hi, region_x_hi + tolerance)
    test.assertGreaterEqual(y_lo, region_y_lo - tolerance)
    test.assertLessEqual(y_hi, region_y_hi + tolerance)


class TestInternationalParcelFixtures(unittest.TestCase):
    def test_zpl_fixture_is_a_label_format_then_an_upright_cn22_format(self):
        stream = _zpl_stream(ZPL_FIXTURE)
        label, cn22 = _formats(stream)

        self.assertTrue(stream.startswith("^XA"))
        self.assertEqual(stream.count("^XZ"), 2)
        self.assertEqual(stream.count(ZPL_NORDIC_MARKER), 1)
        self.assertEqual(stream.count(ZPL_V2_MARKER), 1)
        self.assertEqual(stream.count(KEYWORD), 1)
        self.assertIn(ZPL_NORDIC_MARKER, label)
        self.assertIn("^FDInternational Parcel^FS", label)
        self.assertIn(ZPL_V2_MARKER, cn22)
        self.assertIn(KEYWORD, cn22)
        for marker in ZPL_CN22_MARKERS:
            self.assertNotIn(marker, label)
        for marker in ZPL_LABEL_MARKERS:
            self.assertNotIn(marker, cn22)

    def test_zpl_cn22_format_carries_the_measured_upright_layout(self):
        _, cn22 = _formats(_zpl_stream(ZPL_FIXTURE))

        self.assertIn(f"^LL{V2_LABEL_LENGTH}", cn22)
        self.assertIn("^FWN", cn22)
        self.assertNotIn("^FWR", cn22)
        self.assertIn("^FO10,15\n^GB820,820,1,^FS", cn22)
        self.assertIn("^FO25,730\n^FDarticle or articles prohibited", cn22)
        keyword_field = cn22.index(f"^FO25,785\n^FD{KEYWORD}^FS")
        font = re.findall(r"\^CF0,\d+,\d+", cn22[:keyword_field])[-1]
        self.assertEqual(font, "^CF0,18,18")


    def test_pdf_fixture_is_a_parcel_label_page_then_a_cn22_page(self):
        document = _document(PDF_FIXTURE, "PDF")
        pages = _pdf_pages(document.base64)
        label, cn22 = _page_text(document.base64, 1), _page_text(document.base64, 2)

        self.assertEqual(len(pages), 2)
        self.assertEqual([_page_mm(page) for page in pages], [(210.0, 297.0)] * 2)
        for marker in PDF_INTERNATIONAL_PARCEL_TEXT + ("Shipment Item-ID",):
            self.assertIn(marker, label)
        for marker in PDF_CN22_TEXT + (KEYWORD,):
            self.assertNotIn(marker, label)
            self.assertIn(marker, cn22)
        for marker in (
            PDF_INTERNATIONAL_PARCEL_TEXT + PDF_LABEL_TEXT + PDF_TRACKED_LETTER_TEXT
        ):
            self.assertNotIn(marker, cn22)


class TestInternationalParcelMarkers(unittest.TestCase):
    def test_zpl_label_markers_occur_in_no_cn22_section_of_any_fixture(self):
        for name in ALL_ZPL_FIXTURES:
            for index, section in enumerate(_formats(_zpl_stream(name))):
                cn22 = [marker for marker in ZPL_CN22_MARKERS if marker in section]
                if not cn22:
                    continue
                with self.subTest(fixture=name, format=index):
                    # A single-format combined printout carries the CN22
                    # section ahead of its label section.
                    (marker,) = cn22
                    labels = [m for m in ZPL_LABEL_MARKERS if m in section]
                    cn22_section = section[
                        : min([section.index(m) for m in labels] or [len(section)])
                    ]
                    self.assertIn(marker, cn22_section)
                    self.assertIn(KEYWORD, cn22_section)
                    for label_marker in ZPL_LABEL_MARKERS:
                        self.assertNotIn(label_marker, cn22_section)

    def test_zpl_cn22_markers_occur_in_no_label_only_format(self):
        for name in ALL_ZPL_FIXTURES:
            for index, section in enumerate(_formats(_zpl_stream(name))):
                if not any(marker in section for marker in ZPL_LABEL_MARKERS):
                    continue
                with self.subTest(fixture=name, format=index):
                    label_start = min(
                        section.index(m) for m in ZPL_LABEL_MARKERS if m in section
                    )
                    for marker in ZPL_CN22_MARKERS:
                        self.assertNotIn(marker, section[label_start:])

    def test_international_parcel_markers_occur_on_no_cn22_page(self):
        cn22_pages = 0
        for name in ALL_PDF_FIXTURES:
            document = _document(name, "PDF")
            for page in range(1, len(_pdf_pages(document.base64)) + 1):
                text = _page_text(document.base64, page)
                if "CUSTOMS DECLARATION" not in text:
                    continue
                cn22_pages += 1
                with self.subTest(fixture=name, page=page):
                    for marker in PDF_INTERNATIONAL_PARCEL_TEXT:
                        self.assertNotIn(marker, text)

        self.assertEqual(cn22_pages, 4)


class TestInternationalParcelClassification(unittest.TestCase):
    def test_zpl_fixture_classifies_as_label_cn22(self):
        result = lib.classify_customs_composition(
            _document(ZPL_FIXTURE, "ZPL"), carrier="postnord"
        )

        self.assertEqual(result, COMBINED)

    def test_pdf_fixture_classifies_as_label_cn22_on_page_two(self):
        result = lib.classify_customs_composition(
            _document(PDF_FIXTURE, "PDF"), carrier="postnord"
        )

        self.assertEqual(result, lib.CustomsClassification(
            composition=COMBINED.composition,
            kinds=COMBINED.kinds,
            doc_type=COMBINED.doc_type,
            page=2,
        ))

    def test_zpl_label_format_alone_is_not_customs_bearing(self):
        label, _ = _formats(_zpl_stream(ZPL_FIXTURE))
        document = models.ShippingDocument(
            category="label",
            format="ZPL",
            base64=base64.b64encode(label.encode("utf-8")).decode("utf-8"),
        )

        result = lib.classify_customs_composition(document, carrier="postnord")

        self.assertEqual(result.composition, lib.CustomsComposition.none)
        self.assertEqual(result.kinds, ("label",))


class TestInternationalParcelZplStamp(unittest.TestCase):
    def test_measured_keyword_ink_clears_the_signature_areas(self):
        self.assertLess(V2_KEYWORD_INK[0][1], V2_SIGNATURE_AREA[0][0])
        self.assertLess(ROTATED_KEYWORD_INK_END_Y, STRIP_LABEL_DOTS[1][0])
        self.assertLessEqual(V2_BOX_BOTTOM_RULE_ROW, V2_LABEL_LENGTH)

    def test_stamp_is_inserted_into_the_cn22_format_in_its_signature_area(self):
        document, result, stamped = _stamp(ZPL_FIXTURE, "ZPL")
        original = _zpl_stream(ZPL_FIXTURE)
        zpl = _decode_zpl(stamped.base64)
        label, cn22 = _formats(original)
        (field,) = _grf_fields(zpl)
        (field_text,) = re.findall(r"\^FO\d+,\d+\^GFA,[0-9,A-F]*\^FS", zpl)
        width, height = _grf_extent(field)

        self.assertEqual((result.doc_type, result.page), ("label_cn22", None))
        self.assertEqual(stamped.format, document.format)
        self.assertEqual(zpl.count("^XZ"), 2)
        self.assertEqual(zpl[: len(label)], label)
        self.assertEqual(
            zpl[len(label) :], cn22[: -len("^XZ")] + field_text + "^XZ\n"
        )
        # Upright: the raster runs along the keyword line, wider than tall.
        self.assertGreater(width, height)
        _assert_dots_within(self, _grf_ink_bounds(field), V2_SIGNATURE_AREA)
        self.assertLessEqual(field[1] + height, V2_LABEL_LENGTH)
        self.assertLessEqual(field[1] + height - 1, V2_BOX_BOTTOM_RULE_ROW - 1)

    def test_rotated_letter_cn22_still_stamps_in_its_measured_strip(self):
        for name in COMBINED_ZPL_FIXTURES:
            with self.subTest(fixture=name):
                _, result, stamped = _stamp(name, "ZPL")
                original = _zpl_stream(name)
                zpl = _decode_zpl(stamped.base64)
                (field,) = _grf_fields(zpl)
                width, height = _grf_extent(field)

                self.assertEqual(result.doc_type, "label_cn22")
                self.assertEqual(field[:2], (7, 303))
                # Rotated: the raster runs down the page, taller than wide.
                self.assertGreater(height, width)
                _assert_dots_within(self, _grf_ink_bounds(field), STRIP_LABEL_DOTS)
                self.assertEqual(zpl.count("^XZ"), 1)
                self.assertEqual(
                    zpl[: original.rindex("^XZ")],
                    original[: original.rindex("^XZ")],
                )


def _parcel_signature_area():
    """The page-2 signature area in bottom-up page points.

    Along the keyword's line it spans from the keyword's ink to the box's
    inner right rule; across, from the box's inner bottom rule up to the
    certification text's lowest ink.
    """
    form_x, form_y = PARCEL_FORM_ORIGIN_PT
    return (
        _pt(PARCEL_KEYWORD_INK_RIGHT_MM),
        form_x + PARCEL_BOX_INNER_RULES_PT["right"],
        form_y + PARCEL_BOX_INNER_RULES_PT["bottom"],
        PAGE_HEIGHT_PT - _pt(PARCEL_CERTIFICATION_INK_MM),
    )


class TestInternationalParcelPdfStamp(unittest.TestCase):
    def _page(self):
        page = _pdf_pages(_read_b64(PDF_FIXTURE))[1]
        form = page["/Resources"]["/XObject"]["/Form2"].get_object()
        return page, form

    def test_page_two_landmarks(self):
        page, form = self._page()
        runs = _text_runs(page)
        rules = PARCEL_BOX_INNER_RULES_PT
        rule_points = {
            tuple(round(float(value), 4) for value in operands)
            for operands, operator in ContentStream(form, page.pdf).operations
            if operator == b"l"
        }
        ((operands, _),) = [
            (operands, operator)
            for operands, operator in ContentStream(
                page["/Contents"].get_object(), page.pdf
            ).operations
            if operator == b"cm"
        ]
        ((_, keyword_x, keyword_y),) = [run for run in runs if run[0] == KEYWORD]

        self.assertEqual(
            [round(float(value), 5) for value in operands],
            [1.0, 0.0, 0.0, 1.0, *PARCEL_FORM_ORIGIN_PT],
        )
        self.assertEqual(
            [round(float(value), 5) for value in form["/BBox"]],
            [0.0, 0.0, *PARCEL_FORM_SIZE_PT],
        )
        self.assertAlmostEqual(PARCEL_FORM_SIZE_PT[1] / DOT_PT, 1518.0, places=2)
        self.assertAlmostEqual(keyword_x, PARCEL_KEYWORD_TM_PT[0], places=3)
        self.assertAlmostEqual(keyword_y, PARCEL_KEYWORD_TM_PT[1], places=3)
        self.assertIn((rules["right"], rules["bottom"]), rule_points)
        self.assertIn((rules["left"], rules["bottom"]), rule_points)
        self.assertIn(
            PARCEL_CERTIFICATION_BASELINE_PT,
            [round(y, 4) for text, _, y in runs if text.startswith("article or")],
        )
        self.assertEqual(min(y for _, _, y in runs if y > rules["bottom"]), keyword_y)
        baseline_mm = (
            (PAGE_HEIGHT_PT - PARCEL_FORM_ORIGIN_PT[1] - PARCEL_CERTIFICATION_BASELINE_PT)
            * 25.4
            / 72.0
        )
        self.assertGreater(PARCEL_CERTIFICATION_INK_MM, baseline_mm)
        self.assertLess(PARCEL_CERTIFICATION_INK_MM - baseline_mm, 1.0)
        self.assertGreater(
            _pt(PARCEL_KEYWORD_INK_RIGHT_MM),
            PARCEL_FORM_ORIGIN_PT[0] + PARCEL_KEYWORD_TM_PT[0],
        )

    def test_classified_pdf_stamps_page_two_in_the_signature_area(self):
        document, result, stamped = _stamp(PDF_FIXTURE, "PDF")
        overlays = _overlays(stamped.base64, 2)
        original_label = _pdf_pages(document.base64)[0]
        stamped_label = _pdf_pages(stamped.base64)[0]

        self.assertEqual((result.doc_type, result.page), ("label_cn22", 2))
        self.assertEqual(stamped.format, document.format)
        self.assertEqual(len(_pdf_pages(stamped.base64)), 2)
        self.assertEqual(len(overlays), 2)
        for matrix, bounds in overlays:
            self.assertTrue(_reads_left_to_right(matrix))
            _within(self, bounds, _parcel_signature_area())
        self.assertEqual(_overlays(stamped.base64, 1), [])
        self.assertEqual(
            stamped_label["/Contents"].get_object().get_data(),
            original_label["/Contents"].get_object().get_data(),
        )
        self.assertEqual(_page_text(stamped.base64, 2), _page_text(document.base64, 2))


if __name__ == "__main__":
    unittest.main()
