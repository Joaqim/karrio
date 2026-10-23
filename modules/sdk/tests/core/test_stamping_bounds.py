"""Document stamping: placements must stay on the PDF page or ZPL label."""

import unittest
from unittest import mock

import karrio.lib as lib
import karrio.core.models as models
import karrio.core.utils.stamping as stamping

from .stamping_helpers import (
    TextRun,
    blank_pdf_b64,
    decode_zpl,
    grf_fields,
    overlay_cms,
    signature_png_b64,
    solid_black_png_b64,
    text_runs_pdf_b64,
    zpl_doc_b64,
)


def _pdf(**placement):
    # The blank page is A4, 595 x 842 pt (209.9 x 297.0 mm).
    return stamping.stamp_pdf(
        blank_pdf_b64(),
        stamping.StampRequest(
            image=signature_png_b64(),
            placement=stamping.StampPlacement(**placement),
        ),
    )


def _zpl(stream, **placement):
    return decode_zpl(
        stamping.stamp_zpl(
            zpl_doc_b64(stream),
            stamping.StampRequest(
                image=signature_png_b64(),
                placement=stamping.StampPlacement(**{"unit": "px", **placement}),
            ),
        )
    )


class TestPdfPageBounds(unittest.TestCase):
    def test_unrotated_rectangle_past_the_right_edge_is_rejected(self):
        # Drawn over x 200-220 mm, past the 209.9 mm page width.
        with self.assertRaises(ValueError) as ctx:
            _pdf(x=200.0, y=50.0, width=20.0, height=10.0)

        self.assertIn("right edge", str(ctx.exception))
        self.assertIn("595.0 x 842.0 pt", str(ctx.exception))

    def test_unrotated_rectangle_past_the_bottom_edge_is_rejected(self):
        # Drawn over y 290-300 mm, past the 297.0 mm page height.
        with self.assertRaises(ValueError) as ctx:
            _pdf(x=20.0, y=290.0, width=20.0, height=10.0)

        self.assertIn("bottom edge", str(ctx.exception))
        self.assertIn("595.0 x 842.0 pt", str(ctx.exception))

    def test_rotated_rectangles_past_each_edge_are_rejected(self):
        # A quarter turn draws the 60 x 20 mm box 20 mm wide and 60 mm tall;
        # 30 degrees draws it about 61.96 x 47.32 mm.
        for rotation, x, y, edge in (
            (90, 195.0, 50.0, "right edge"),
            (90, 20.0, 250.0, "bottom edge"),
            (30, 150.0, 50.0, "right edge"),
            (30, 20.0, 260.0, "bottom edge"),
        ):
            with self.subTest(rotation=rotation, edge=edge):
                with self.assertRaises(ValueError) as ctx:
                    _pdf(x=x, y=y, width=60.0, height=20.0, rotation=rotation)

                self.assertIn(edge, str(ctx.exception))
                self.assertIn("mediabox", str(ctx.exception))

    def test_rectangle_ending_exactly_on_the_edges_is_accepted(self):
        stamped = _pdf(unit="pt", x=495, y=742, width=100, height=100)

        ((_, _, _, _, e, f),) = overlay_cms(stamped)
        self.assertAlmostEqual(e, 495.0, places=4)

    def test_rotated_rectangle_ending_exactly_on_the_edges_is_accepted(self):
        # A quarter turn draws the 100 x 50 pt box 50 pt wide and 100 pt tall.
        stamped = _pdf(unit="pt", x=545, y=742, width=100, height=50, rotation=90)

        self.assertEqual(len(overlay_cms(stamped)), 1)


class TestZplLabelBounds(unittest.TestCase):
    LABEL = "^XA^PW800^LL1200^FO10,10^GB100,100,2^FS^XZ"

    def test_rectangle_past_the_label_length_is_rejected_before_the_raster(self):
        with mock.patch.object(
            stamping,
            "_build_zpl_raster",
            side_effect=AssertionError("raster built before the label check"),
        ) as build:
            with self.assertRaises(ValueError) as ctx:
                _zpl(self.LABEL, x=10, y=1100, width=400, height=140)

        build.assert_not_called()
        self.assertIn("label length", str(ctx.exception))
        self.assertIn("1200", str(ctx.exception))
        self.assertIn("1240", str(ctx.exception))

    def test_rectangle_past_the_print_width_is_rejected_before_the_raster(self):
        with mock.patch.object(
            stamping,
            "_build_zpl_raster",
            side_effect=AssertionError("raster built before the label check"),
        ) as build:
            with self.assertRaises(ValueError) as ctx:
                _zpl(self.LABEL, x=440, y=400, width=400, height=140)

        build.assert_not_called()
        self.assertIn("print width", str(ctx.exception))
        self.assertIn("800", str(ctx.exception))
        self.assertIn("840", str(ctx.exception))

    def test_rotated_rectangle_past_the_label_length_is_rejected(self):
        # A quarter turn hangs the 400 x 140-dot box 400 dots down from y 900.
        with self.assertRaises(ValueError) as ctx:
            _zpl(self.LABEL, x=10, y=900, width=400, height=140, rotation=90)

        self.assertIn("label length", str(ctx.exception))

    def test_rectangle_ending_exactly_on_the_label_edges_is_accepted(self):
        zpl = _zpl(self.LABEL, x=400, y=1060, width=400, height=140)

        ((fo_x, fo_y, *_),) = grf_fields(zpl)
        self.assertEqual((fo_x, fo_y), (400, 1060))

    def test_earlier_format_settings_apply_to_a_later_format(self):
        stream = self.LABEL + "^XA^FO20,20^GB50,50,1^FS^XZ"
        for field, placement in (
            ("label length", dict(x=10, y=1100, width=400, height=140)),
            ("print width", dict(x=440, y=400, width=400, height=140)),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError) as ctx:
                    _zpl(stream, page=2, **placement)

                self.assertIn(field, str(ctx.exception))

    def test_later_format_settings_do_not_apply_to_an_earlier_format(self):
        stream = "^XA^FO20,20^GB50,50,1^FS^XZ" + self.LABEL
        zpl = _zpl(stream, x=10, y=1100, width=400, height=140)

        self.assertEqual(len(grf_fields(zpl)), 1)

    def test_stream_without_a_print_width_checks_the_length_only(self):
        zpl = _zpl(
            "^XA^LL1200^FO10,10^GB100,100,2^FS^XZ",
            x=1600,
            y=100,
            width=400,
            height=140,
        )
        ((fo_x, _, *_),) = grf_fields(zpl)
        self.assertEqual(fo_x, 1600)

        with self.assertRaises(ValueError) as ctx:
            _zpl(
                "^XA^LL1200^FO10,10^GB100,100,2^FS^XZ",
                x=1600,
                y=1100,
                width=400,
                height=140,
            )
        self.assertIn("label length", str(ctx.exception))

    def test_stream_without_a_label_length_checks_the_operand_range_only(self):
        zpl = _zpl("^XA^FO10,10^GB100,100,2^FS^XZ", x=10, y=5000, width=400, height=140)

        ((_, fo_y, *_),) = grf_fields(zpl)
        self.assertEqual(fo_y, 5000)


class TestKeywordOffsetsAreNotBounded(unittest.TestCase):
    def test_negative_zpl_keyword_offsets_resolving_inside_the_label_pass(self):
        # The keyword field sits at ^FO200,300; a seed offset of (-100, -50)
        # dots lands the stamp at ^FO100,250 on the 800 x 1200-dot label.
        seed_geometry = stamping.StampPlacement(
            unit="px", x=-100, y=-50, width=400, height=140, dpi=203
        )
        stamped = lib.stamp_document(
            models.ShippingDocument(
                category="customs_declaration",
                format="ZPL",
                base64=zpl_doc_b64(
                    "^XA^PW800^LL1200^FO200,300^FDSender signature^FS^XZ"
                ),
            ),
            image=solid_black_png_b64(),
            keyword="Sender signature",
            registry=lambda key: seed_geometry,
        )

        ((fo_x, fo_y, *_),) = grf_fields(decode_zpl(stamped.base64))
        self.assertEqual((fo_x, fo_y), (100, 250))

    def test_negative_pdf_keyword_offsets_resolving_inside_the_page_pass(self):
        # Keyword baseline at (300, 500) pt; the strip starts 10 mm before the
        # text and 4 mm above its baseline, still on the page.
        stamped = lib.stamp_document(
            models.ShippingDocument(
                category="label",
                format="PDF",
                base64=text_runs_pdf_b64(
                    [TextRun("Sender signature", (1, 0, 0, 1, 300, 500))]
                ),
            ),
            image=solid_black_png_b64(400, 100),
            keyword="Sender signature",
            registry=lambda key: stamping.StampPlacement(
                x=-10.0, y=-4.0, width=40.0, height=10.0
            ),
        )

        ((_, _, _, _, e, f),) = overlay_cms(stamped.base64)
        # 300 - 28.346 pt along the text; the bottom edge 6 mm (17.008 pt)
        # below the baseline.
        self.assertAlmostEqual(e, 271.6535, places=3)
        self.assertAlmostEqual(f, 482.9921, places=3)


if __name__ == "__main__":
    unittest.main()
