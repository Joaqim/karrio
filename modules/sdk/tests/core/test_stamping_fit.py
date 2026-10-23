"""Document stamping: the image fits its box with its aspect ratio preserved."""

import unittest

import karrio.core.utils.stamping as stamping

from .stamping_helpers import (
    blank_pdf_b64,
    decode_zpl,
    grf_fields,
    grf_ink_bounds,
    overlay_cms,
    solid_black_png_b64,
    zpl_doc_b64,
)


def _pdf_cms(image, placement, **fields):
    return overlay_cms(
        stamping.stamp_pdf(
            blank_pdf_b64(),
            stamping.StampRequest(image=image, placement=placement, **fields),
        )
    )


def _zpl_graphic(image, placement, **fields):
    ((fo_x, fo_y, total, _, bpr, hexdata),) = grf_fields(
        decode_zpl(
            stamping.stamp_zpl(
                zpl_doc_b64(),
                stamping.StampRequest(image=image, placement=placement, **fields),
            )
        )
    )
    return (fo_x, fo_y, bpr, total // bpr), grf_ink_bounds(hexdata, bpr)


# A 40 x 20 mm box at (20, 30) mm: on the 842 pt A4 page its bottom-left is
# (56.693, 700.268) pt; at 203 dpi it is 320 x 160 dots at ^FO160,240.
WIDE_BOX = stamping.StampPlacement(x=20.0, y=30.0, width=40.0, height=20.0)
# A 40 x 10 mm box at (20, 30) mm: bottom-left (56.693, 728.614) pt, and
# 320 x 80 dots at 203 dpi.
FLAT_BOX = stamping.StampPlacement(x=20.0, y=30.0, width=40.0, height=10.0)


class TestPdfFit(unittest.TestCase):
    def test_wide_image_is_centred_vertically_in_a_taller_box(self):
        # 400 x 100 px is a 96 x 24 pt overlay; scaled 1.1811 it is drawn
        # 40 x 10 mm, lifted 5 mm (14.173 pt) off the box's bottom edge.
        ((a, b, c, d, e, f),) = _pdf_cms(solid_black_png_b64(400, 100), WIDE_BOX)

        self.assertAlmostEqual(a, 1.181102, places=5)
        self.assertAlmostEqual(d, 1.181102, places=5)
        self.assertAlmostEqual(b, 0.0, places=9)
        self.assertAlmostEqual(c, 0.0, places=9)
        self.assertAlmostEqual(e, 56.692913, places=4)
        self.assertAlmostEqual(f, 714.440945, places=4)

    def test_square_image_sits_against_the_left_edge(self):
        # 100 x 100 px is a 24 x 24 pt overlay drawn 10 x 10 mm at the box's
        # own bottom-left corner.
        ((a, _, _, d, e, f),) = _pdf_cms(solid_black_png_b64(100, 100), FLAT_BOX)

        self.assertAlmostEqual(a, 1.181102, places=5)
        self.assertAlmostEqual(d, 1.181102, places=5)
        self.assertAlmostEqual(e, 56.692913, places=4)
        self.assertAlmostEqual(f, 728.614173, places=4)

    def test_fit_applies_inside_the_signature_share(self):
        # The date takes the leading 20 mm; the 400 x 100 px signature fits
        # the 20 x 20 mm share at 20 x 5 mm, 7.5 mm above its bottom edge.
        date_cm, signature_cm = _pdf_cms(
            solid_black_png_b64(400, 100), WIDE_BOX, date="2026-09-22"
        )
        a, _, _, d, e, f = signature_cm

        self.assertAlmostEqual(a, 0.590551, places=5)
        self.assertAlmostEqual(d, 0.590551, places=5)
        self.assertAlmostEqual(e, 113.385827, places=4)
        self.assertAlmostEqual(f, 721.527559, places=4)
        self.assertAlmostEqual(date_cm[4], 56.692913, places=4)

    def test_rotation_carries_the_fit_offset(self):
        # Rotated 90 clockwise at (40, 200) mm the box is drawn 20 mm wide;
        # the 10 mm image is centred across it, 5 mm right of the anchor
        # (113.386 + 14.173 pt), with its top on the anchor's 275.071 pt.
        ((a, b, c, d, e, f),) = _pdf_cms(
            solid_black_png_b64(400, 100),
            stamping.StampPlacement(
                x=40.0, y=200.0, width=40.0, height=20.0, rotation=90
            ),
        )

        self.assertAlmostEqual(a, 0.0, places=6)
        self.assertAlmostEqual(b, -1.181102, places=5)
        self.assertAlmostEqual(c, 1.181102, places=5)
        self.assertAlmostEqual(d, 0.0, places=6)
        self.assertAlmostEqual(e, 127.559055, places=4)
        self.assertAlmostEqual(f, 275.070866, places=4)


class TestZplFit(unittest.TestCase):
    def test_raster_keeps_the_box_size_with_ink_in_the_fitted_rows(self):
        # 400 x 100 px into 320 x 160 dots: 320 x 80 dots, rows 40-119.
        (fo_x, fo_y, bpr, rows), (ink_rows, ink_columns) = _zpl_graphic(
            solid_black_png_b64(400, 100), WIDE_BOX
        )

        self.assertEqual((fo_x, fo_y, bpr, rows), (160, 240, 40, 160))
        self.assertEqual(ink_rows, list(range(40, 120)))
        self.assertEqual(ink_columns, list(range(0, 320)))

    def test_square_image_is_left_aligned_in_the_raster(self):
        # 100 x 100 px into 320 x 80 dots: 80 x 80 dots in columns 0-79.
        (_, _, bpr, rows), (ink_rows, ink_columns) = _zpl_graphic(
            solid_black_png_b64(100, 100), FLAT_BOX
        )

        self.assertEqual((bpr, rows), (40, 80))
        self.assertEqual(ink_rows, list(range(0, 80)))
        self.assertEqual(ink_columns, list(range(0, 80)))

    def test_fit_applies_inside_the_signature_share(self):
        # The date takes columns 0-159; the 400 x 100 px signature fits the
        # 160 x 160-dot share at 160 x 40 dots, rows 60-99.
        request = stamping.StampRequest(
            image=solid_black_png_b64(400, 100), placement=WIDE_BOX, date="9/22"
        )
        raster = stamping._build_zpl_raster(request)
        pixels = raster.load()
        share_rows = sorted(
            {y for y in range(160) for x in range(160, 320) if pixels[x, y] == 0}
        )
        share_columns = sorted(
            {x for y in range(160) for x in range(160, 320) if pixels[x, y] == 0}
        )

        self.assertEqual(raster.size, (320, 160))
        self.assertEqual(share_rows, list(range(60, 100)))
        self.assertEqual(share_columns, list(range(160, 320)))

    def test_rotation_carries_the_fit_offset(self):
        # Rotated 90 clockwise the 320 x 160 raster becomes 160 x 320 and the
        # fitted rows 40-119 become columns 40-119.
        (_, _, bpr, rows), (ink_rows, ink_columns) = _zpl_graphic(
            solid_black_png_b64(400, 100),
            stamping.StampPlacement(
                x=20.0, y=30.0, width=40.0, height=20.0, rotation=90
            ),
        )

        self.assertEqual((bpr, rows), (20, 320))
        self.assertEqual(ink_rows, list(range(0, 320)))
        self.assertEqual(ink_columns, list(range(40, 120)))


if __name__ == "__main__":
    unittest.main()
