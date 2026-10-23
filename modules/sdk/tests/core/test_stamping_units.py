"""Document stamping: placement units (mm, pt and px)."""

import unittest

import attr

import karrio.lib as lib
import karrio.core.utils.stamping as stamping

from .stamping_helpers import (
    INLINE_KEYWORD_STREAM,
    KEYWORD,
    blank_pdf_b64,
    decode_zpl,
    grf_fields,
    keyword_zpl_document,
    overlay_cms,
    solid_black_png_b64,
    zpl_doc_b64,
)


def _zpl(placement, image=None):
    return decode_zpl(
        stamping.stamp_zpl(
            zpl_doc_b64(),
            stamping.StampRequest(
                image=image or solid_black_png_b64(400, 140), placement=placement
            ),
        )
    )


def _pdf(placement):
    # A 400 x 100 px image is 96 x 24 pt in the overlay PDF, the 4:1 aspect of
    # every box below, so the leading cm is the box itself.
    return stamping.stamp_pdf(
        blank_pdf_b64(),
        stamping.StampRequest(image=solid_black_png_b64(400, 100), placement=placement),
    )


class TestPixelUnits(unittest.TestCase):
    def test_px_zpl_placement_is_in_printer_dots(self):
        zpl = _zpl(
            stamping.StampPlacement(
                unit="px", x=40, y=60, width=400, height=140, dpi=203
            )
        )

        ((fo_x, fo_y, total, total2, bpr, _),) = grf_fields(zpl)
        self.assertEqual((fo_x, fo_y), (40, 60))
        self.assertEqual((bpr, total, total2), (50, 7000, 7000))

    def test_px_pdf_placement_uses_the_render_density(self):
        stamped = _pdf(
            stamping.StampPlacement(
                unit="px", x=150, y=300, width=300, height=75, dpi=150
            )
        )

        ((a, b, c, d, e, f),) = overlay_cms(stamped)
        # 150/300/300/75 px at 150 dpi: 72 pt left, 144 pt down, 144 x 36 pt,
        # so the bottom-left sits at 842 - 144 - 36 = 662 pt.
        self.assertAlmostEqual(a, 1.5, places=6)
        self.assertAlmostEqual(d, 1.5, places=6)
        self.assertAlmostEqual(b, 0.0, places=9)
        self.assertAlmostEqual(c, 0.0, places=9)
        self.assertAlmostEqual(e, 72.0, places=6)
        self.assertAlmostEqual(f, 662.0, places=6)


class TestPointUnits(unittest.TestCase):
    def test_pt_placement_anchors_one_inch_from_the_top_left(self):
        stamped = _pdf(
            stamping.StampPlacement(unit="pt", x=72, y=72, width=144, height=36)
        )

        ((a, _, _, d, e, f),) = overlay_cms(stamped)
        self.assertAlmostEqual(a, 1.5, places=6)
        self.assertAlmostEqual(d, 1.5, places=6)
        self.assertAlmostEqual(e, 72.0, places=6)
        # Top edge 72 pt below the 842 pt page top, so the bottom is at 734 pt.
        self.assertAlmostEqual(f, 734.0, places=6)


class TestDefaultAndUnknownUnits(unittest.TestCase):
    PLACEMENT = stamping.StampPlacement(x=20.0, y=30.0, width=60.0, height=15.0)

    def test_omitted_unit_is_byte_identical_to_mm(self):
        omitted = self.PLACEMENT
        explicit = attr.evolve(self.PLACEMENT, unit="mm")

        self.assertEqual(_pdf(omitted), _pdf(explicit))
        self.assertEqual(_zpl(omitted), _zpl(explicit))

    def test_unknown_unit_is_rejected_naming_the_field(self):
        placement = attr.evolve(self.PLACEMENT, unit="in")
        for stamp in (_pdf, _zpl):
            with self.subTest(backend=stamp.__name__):
                with self.assertRaises(ValueError) as ctx:
                    stamp(placement)

                self.assertIn("StampPlacement.unit", str(ctx.exception))
                for unit in ("mm", "pt", "px"):
                    self.assertIn(unit, str(ctx.exception))

    def test_unknown_unit_is_rejected_by_stamp_document(self):
        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(
                keyword_zpl_document(INLINE_KEYWORD_STREAM),
                image=solid_black_png_b64(),
                placement=attr.evolve(self.PLACEMENT, unit="in"),
            )

        self.assertIn("StampPlacement.unit", str(ctx.exception))

    def test_accepted_units_are_exported(self):
        self.assertEqual(lib.STAMP_UNITS, ("mm", "pt", "px"))


class TestKeywordGeometryUnits(unittest.TestCase):
    def test_px_geometry_only_keyword_placement_is_converted(self):
        # The keyword field sits at ^FO10,20; a geometry-only placement leaves
        # its offsets unset, so the stamp lands on the field origin with the
        # px extent taken as 80 x 16 dots.
        stamped = lib.stamp_document(
            keyword_zpl_document(INLINE_KEYWORD_STREAM),
            image=solid_black_png_b64(400, 80),
            keyword=KEYWORD,
            placement=stamping.StampPlacement(unit="px", width=80, height=16, dpi=203),
        )

        ((fo_x, fo_y, total, _, bpr, _),) = grf_fields(decode_zpl(stamped.base64))
        self.assertEqual((fo_x, fo_y), (10, 20))
        self.assertEqual((bpr, total), (10, 160))


if __name__ == "__main__":
    unittest.main()
