"""Document stamping: corner-anchored rotation and the consumer date strip."""

import io
import math
import base64
import unittest
from unittest import mock

import pypdf
from pypdf.generic import ContentStream

import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont

import karrio.lib as lib
import karrio.core.utils.stamping as stamping

from .stamping_helpers import (
    decode_zpl,
    example_zpl_form_b64,
    form_pdf_b64,
    grf_fields,
    overlay_cms,
    pdf_document,
    placement,
    real_signature_b64,
    rotated_placement,
    sentinel_pdf_b64,
    signature_png_b64,
    solid_black_png_b64,
    zpl_doc_b64,
    zpl_placement,
)


def _pdf_cms(request_placement, document=None, **fields):
    return overlay_cms(
        stamping.stamp_pdf(
            document or sentinel_pdf_b64(),
            stamping.StampRequest(
                image=signature_png_b64(), placement=request_placement, **fields
            ),
        )
    )


def _concat(m, n):
    """PDF matrix product ``m x n`` of two ``(a, b, c, d, e, f)`` matrices."""
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def _drawn_image_boxes_mm(document_b64: str, page_index: int = 0):
    """Return each drawn image's bounding box as ``(left, top, right, bottom)``.

    The page content is interpreted directly: ``q``/``Q``/``cm`` maintain the
    current transformation matrix and every ``Do`` paints the unit square
    through it, per the PDF imaging model. Boxes are millimetres from the page
    top-left, so they compare directly with a placement.
    """
    page = pypdf.PdfReader(io.BytesIO(base64.b64decode(document_b64))).pages[page_index]
    height_pt = float(page.mediabox.height)
    ctm, stack, boxes = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0), [], []
    for operands, operator in ContentStream(page.get_contents(), page.pdf).operations:
        if operator == b"q":
            stack.append(ctm)
        elif operator == b"Q":
            ctm = stack.pop()
        elif operator == b"cm":
            ctm = _concat(tuple(float(value) for value in operands), ctm)
        elif operator == b"Do":
            a, b, c, d, e, f = ctm
            xs, ys = zip(
                *(
                    (a * u + c * v + e, b * u + d * v + f)
                    for u, v in ((0, 0), (1, 0), (0, 1), (1, 1))
                )
            )
            boxes.append(
                tuple(
                    value * 25.4 / 72.0
                    for value in (
                        min(xs),
                        height_pt - max(ys),
                        max(xs),
                        height_pt - min(ys),
                    )
                )
            )
    return boxes


def _union(boxes):
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _expected_box_mm(x, y, width, height, rotation):
    """The corner-anchored rotated extent: its top-left sits on ``(x, y)``."""
    radians = math.radians(rotation)
    cosine, sine = abs(math.cos(radians)), abs(math.sin(radians))
    return (
        x,
        y,
        x + width * cosine + height * sine,
        y + width * sine + height * cosine,
    )


class TestPdfRotationGeometry(unittest.TestCase):
    """The drawn PDF extent against an analytic oracle and the ZPL backend."""

    ANGLES = (30, 90, 135, 180, 200, 270, 315)

    def _stamp(self, rotation, **fields):
        return stamping.stamp_pdf(
            sentinel_pdf_b64(),
            stamping.StampRequest(
                image=solid_black_png_b64(),
                placement=stamping.StampPlacement(
                    x=60.0, y=120.0, width=50.0, height=16.0, rotation=rotation
                ),
                **fields,
            ),
        )

    def _assert_box(self, observed, expected):
        for got, want in zip(observed, expected):
            self.assertAlmostEqual(got, want, delta=0.05)

    def test_rotated_extent_top_left_lands_on_the_anchor_at_any_angle(self):
        for rotation in self.ANGLES:
            with self.subTest(rotation=rotation):
                (box,) = _drawn_image_boxes_mm(self._stamp(rotation))

                self._assert_box(
                    box, _expected_box_mm(60.0, 120.0, 50.0, 16.0, rotation)
                )

    def test_pdf_extent_matches_the_zpl_graphic(self):
        # The ZPL backend anchors the rotated raster's top-left at ^FO; its
        # origin and row count, read from the ^GFA header, locate the same
        # extent in dots (0.125 mm at 203 dpi). The row width is only known to
        # the byte, so the right edge is bounded by the padded width.
        dots_to_mm = 25.4 / 203
        for rotation in self.ANGLES:
            with self.subTest(rotation=rotation):
                left, top, right, bottom = _drawn_image_boxes_mm(self._stamp(rotation))[
                    0
                ]
                zpl = decode_zpl(
                    stamping.stamp_zpl(
                        zpl_doc_b64(),
                        stamping.StampRequest(
                            image=solid_black_png_b64(),
                            placement=stamping.StampPlacement(
                                x=60.0,
                                y=120.0,
                                width=50.0,
                                height=16.0,
                                rotation=rotation,
                                dpi=203,
                            ),
                        ),
                    )
                )
                ((fo_x, fo_y, total, _, bpr, _),) = grf_fields(zpl)

                self.assertAlmostEqual(left, fo_x * dots_to_mm, delta=0.5)
                self.assertAlmostEqual(top, fo_y * dots_to_mm, delta=0.5)
                self.assertAlmostEqual(
                    bottom, (fo_y + total // bpr) * dots_to_mm, delta=0.5
                )
                self.assertLessEqual(right, (fo_x + bpr * 8) * dots_to_mm + 0.5)
                self.assertGreaterEqual(right, (fo_x + bpr * 8 - 8) * dots_to_mm - 0.5)

    def test_date_and_signature_tile_the_rotated_rectangle(self):
        # With a date the two images are halves of one rotated rectangle:
        # together they cover exactly the corner-anchored extent, and neither
        # half strays outside it.
        for rotation in (0,) + self.ANGLES:
            with self.subTest(rotation=rotation):
                boxes = _drawn_image_boxes_mm(self._stamp(rotation, date="2026-09-22"))
                expected = _expected_box_mm(60.0, 120.0, 50.0, 16.0, rotation)

                self.assertEqual(len(boxes), 2)
                self._assert_box(_union(boxes), expected)
                self.assertNotEqual(boxes[0], boxes[1])

    def test_half_turn_near_the_left_edge_is_accepted(self):
        # Rotated 180 degrees a 60 x 20 mm placement at x=5 mm is drawn over
        # x 5-65 mm, well inside the page.
        document = stamping.stamp_pdf(
            form_pdf_b64(),
            stamping.StampRequest(
                image=solid_black_png_b64(),
                placement=stamping.StampPlacement(
                    x=5.0, y=50.0, width=60.0, height=20.0, rotation=180
                ),
            ),
        )

        self._assert_box(
            _union(_drawn_image_boxes_mm(document)), (5.0, 50.0, 65.0, 70.0)
        )

    def test_three_quarter_turn_near_the_left_edge_is_accepted(self):
        stamping.stamp_pdf(
            form_pdf_b64(),
            stamping.StampRequest(
                image=solid_black_png_b64(),
                placement=stamping.StampPlacement(
                    x=5.0, y=50.0, width=60.0, height=20.0, rotation=270
                ),
            ),
        )

    def test_half_turn_past_the_right_edge_is_rejected(self):
        # Drawn over x 180-240 mm, past the 210 mm A4 width.
        with self.assertRaises(ValueError) as ctx:
            stamping.stamp_pdf(
                form_pdf_b64(),
                stamping.StampRequest(
                    image=solid_black_png_b64(),
                    placement=stamping.StampPlacement(
                        x=180.0, y=50.0, width=60.0, height=20.0, rotation=180
                    ),
                ),
            )

        self.assertIn("right edge", str(ctx.exception))

    def test_three_quarter_turn_past_the_bottom_edge_is_rejected(self):
        # Rotated 270 degrees the 60 mm width runs down the page from y=280 mm
        # to 340 mm, past the 297 mm A4 height.
        with self.assertRaises(ValueError) as ctx:
            stamping.stamp_pdf(
                form_pdf_b64(),
                stamping.StampRequest(
                    image=solid_black_png_b64(),
                    placement=stamping.StampPlacement(
                        x=100.0, y=280.0, width=60.0, height=20.0, rotation=270
                    ),
                ),
            )

        self.assertIn("bottom edge", str(ctx.exception))


class TestPdfRotation(unittest.TestCase):
    def test_rotation_composes_a_clockwise_matrix_at_the_anchor(self):
        # Oracle: the overlay's leading `cm`. A 90-degree clockwise rotation maps
        # the observed upright scale (sx, 0, 0, sy) to (0, -sx, sy, 0). The scale
        # is read from the un-rotated stamp, never re-derived from the
        # production rotation expression, so a wrong angle or direction fails.
        (upright,) = _pdf_cms(placement())
        (rotated,) = _pdf_cms(rotated_placement(90))

        self.assertAlmostEqual(upright[1], 0.0, places=9)
        self.assertAlmostEqual(upright[2], 0.0, places=9)
        sx, sy = upright[0], upright[3]

        a, b, c, d = rotated[:4]
        self.assertAlmostEqual(a, 0.0, places=6)
        self.assertAlmostEqual(b, -sx, places=6)
        self.assertAlmostEqual(c, sy, places=6)
        self.assertAlmostEqual(d, 0.0, places=6)

    def test_rotation_translates_the_rotated_corner_to_the_anchor(self):
        # The rotated extent's top-left lands at (pt(x), H - pt(y)) on the
        # 595 x 842 pt page: (113.386, 275.071) pt for (40, 200) mm.
        (rotated,) = _pdf_cms(rotated_placement(90))

        self.assertAlmostEqual(rotated[4], 40.0 * 72.0 / 25.4, places=3)
        self.assertAlmostEqual(rotated[5], 842.0 - 200.0 * 72.0 / 25.4, places=2)

    def test_zero_rotation_is_byte_identical_to_no_rotation(self):
        document = form_pdf_b64()
        image = signature_png_b64()

        no_rotation = stamping.stamp_pdf(
            document, stamping.StampRequest(image=image, placement=placement())
        )
        zero_rotation = stamping.stamp_pdf(
            document,
            stamping.StampRequest(image=image, placement=rotated_placement(0)),
        )

        self.assertEqual(no_rotation, zero_rotation)

    def test_rotated_extent_beyond_the_mediabox_is_rejected(self):
        # A 20 x 200 mm placement rotated 90 degrees at x=200 mm sweeps right to
        # 400 mm, far past the A4 page's 210 mm width.
        with self.assertRaises(ValueError) as ctx:
            stamping.stamp_pdf(
                form_pdf_b64(),
                stamping.StampRequest(
                    image=signature_png_b64(),
                    placement=stamping.StampPlacement(
                        x=200.0, y=50.0, width=20.0, height=200.0, rotation=90
                    ),
                ),
            )

        self.assertIn("mediabox", str(ctx.exception))

    def test_the_same_extent_unrotated_is_tolerated(self):
        stamped = stamping.stamp_pdf(
            form_pdf_b64(),
            stamping.StampRequest(
                image=signature_png_b64(),
                placement=stamping.StampPlacement(
                    x=200.0, y=50.0, width=20.0, height=200.0
                ),
            ),
        )

        self.assertEqual(len(overlay_cms(stamped)), 1)


class TestZplRotation(unittest.TestCase):
    def test_rotation_swaps_dimensions_and_anchors_at_the_placement(self):
        # At 203 dpi the placement is 480x160 dots anchored at (160, 240). A
        # 90-degree clockwise rotation swaps the raster to 160x480, and the
        # rotated graphic's top-left anchors at the placement's own origin.
        def stamp(rotation):
            return decode_zpl(
                stamping.stamp_zpl(
                    zpl_doc_b64(),
                    stamping.StampRequest(
                        image=signature_png_b64(),
                        placement=zpl_placement(rotation=rotation),
                    ),
                )
            )

        ((up_x, up_y, up_total, _, up_bpr, _),) = grf_fields(stamp(0))
        ((ro_x, ro_y, ro_total, _, ro_bpr, _),) = grf_fields(stamp(90))

        self.assertEqual((up_x, up_y), (160, 240))
        self.assertEqual(up_total // up_bpr, 160)
        self.assertEqual(ro_total // ro_bpr, 480)
        self.assertEqual((ro_x, ro_y), (160, 240))

    def test_range_check_extent_matches_the_rotated_raster(self):
        # The pre-build range check predicts the rotated raster's extent: exact
        # for right angles, never above the built raster for any other angle.
        for rotation in (0, 30, 45, 90, 135, 180, 200, 270, 315):
            with self.subTest(rotation=rotation):
                geometry = stamping.StampPlacement(
                    x=5.0, y=5.0, width=33.0, height=12.0, rotation=rotation
                )
                raster = stamping._build_zpl_raster(
                    stamping.StampRequest(image=signature_png_b64(), placement=geometry)
                )
                if rotation:
                    raster = raster.rotate(-rotation, expand=True, fillcolor=1)

                predicted = stamping._zpl_raster_extent(geometry)

                if rotation % 90 == 0:
                    self.assertEqual(predicted, raster.size)
                else:
                    self.assertLessEqual(predicted[0], raster.size[0])
                    self.assertLessEqual(predicted[1], raster.size[1])
                    self.assertGreaterEqual(predicted[0], raster.size[0] - 2)
                    self.assertGreaterEqual(predicted[1], raster.size[1] - 2)

    def test_rotated_extent_beyond_the_range_is_rejected_before_the_build(self):
        # Rotated 90 degrees, a 4000 x 10 mm strip at y=100 mm hangs 31969
        # dots down from ^FO..,799: a y extent of 32768.
        with mock.patch.object(
            stamping,
            "_build_zpl_raster",
            side_effect=AssertionError("raster built before the range check"),
        ):
            with self.assertRaises(ValueError) as ctx:
                stamping.stamp_zpl(
                    zpl_doc_b64(),
                    stamping.StampRequest(
                        image=signature_png_b64(),
                        placement=stamping.StampPlacement(
                            x=5.0, y=100.0, width=4000.0, height=10.0, rotation=90
                        ),
                    ),
                )

        self.assertIn("y extent", str(ctx.exception))
        self.assertIn("32768", str(ctx.exception))


class TestRotatedExampleForm(unittest.TestCase):
    # A 33 x 12 mm strip at (5, 100) mm rotated 90 clockwise at 203 dpi:
    # 40/799/264/96 dots, the rotated 96 x 264 raster hanging down-right from
    # the placement's own ^FO40,799.
    PLACEMENT = stamping.StampPlacement(
        x=5.0, y=100.0, width=33.0, height=12.0, rotation=90, dpi=203
    )

    def _stamp(self, placement):
        return decode_zpl(
            stamping.stamp_zpl(
                example_zpl_form_b64(),
                stamping.StampRequest(image=real_signature_b64(), placement=placement),
            )
        )

    def test_rotation_anchors_the_rotated_corner_on_the_form(self):
        ((fo_x, fo_y, total, total2, bpr, hexdata),) = grf_fields(
            self._stamp(self.PLACEMENT)
        )

        self.assertEqual((fo_x, fo_y), (40, 799))
        self.assertEqual(bpr, 12)
        self.assertEqual(total, 3168)
        self.assertEqual(total2, total)
        self.assertEqual(len(hexdata), total * 2)

    def test_corner_placement_anchors_the_rotated_strip_at_the_corner(self):
        # (0, 0, 70, 20, rotation=90) anchors the rotated strip's top-left at
        # the label corner: ^FO0,0 with a 160 x 559-dot raster, not a
        # centre-pivot origin half off the label.
        ((fo_x, fo_y, total, _, bpr, _),) = grf_fields(
            self._stamp(
                stamping.StampPlacement(
                    x=0.0, y=0.0, width=70.0, height=20.0, rotation=90, dpi=203
                )
            )
        )

        self.assertEqual((fo_x, fo_y), (0, 0))
        self.assertEqual(bpr, 20)
        self.assertEqual(total, 11180)


class TestConsumerDateStamp(unittest.TestCase):
    def test_date_precedes_signature_and_shares_its_rotation(self):
        # Un-rotated: reading order is left-to-right, so the leading (date)
        # overlay's translation-x sits left of the signature overlay's. The two
        # overlays are composited date-first, so paint order labels them.
        upright = _pdf_cms(placement(), date="2026-09-22")
        self.assertEqual(len(upright), 2)
        date_cm, signature_cm = upright
        self.assertLess(date_cm[4], signature_cm[4])

        # Rotated: the rotation angle is atan2(b, a), scale-independent, so
        # equal angles mean the date shares the signature's rotation even
        # though the two images scale differently.
        rotated = _pdf_cms(rotated_placement(90), date="2026-09-22")
        self.assertEqual(len(rotated), 2)
        date_cm, signature_cm = rotated
        date_angle = math.atan2(date_cm[1], date_cm[0])
        signature_angle = math.atan2(signature_cm[1], signature_cm[0])
        self.assertAlmostEqual(date_angle, signature_angle, places=9)
        # A genuine clockwise 90-degree rotation: -pi/2, zero diagonal, b < 0 < c.
        self.assertAlmostEqual(signature_angle, -math.pi / 2, places=6)
        self.assertAlmostEqual(signature_cm[0], 0.0, places=6)
        self.assertAlmostEqual(signature_cm[3], 0.0, places=6)
        self.assertLess(signature_cm[1], 0.0)
        self.assertGreater(signature_cm[2], 0.0)

    def test_absent_date_composites_the_signature_alone(self):
        # With no date the signature is the only overlay and spans the whole
        # placement, so its x-scale exceeds the partitioned signature's.
        absent = _pdf_cms(placement())
        present = _pdf_cms(placement(), date="2026-09-22")

        self.assertEqual(len(absent), 1)
        self.assertEqual(len(present), 2)
        self.assertGreater(absent[0][0], present[1][0])

    def test_empty_date_is_treated_as_absent(self):
        self.assertEqual(len(_pdf_cms(placement(), date="")), 1)

    def test_date_threads_through_lib_stamp_document(self):
        stamped = lib.stamp_document(
            pdf_document(),
            image=signature_png_b64(),
            placement=placement(),
            date="2026-09-22",
        )

        self.assertEqual(stamped.format, "PDF")
        self.assertEqual(len(overlay_cms(stamped.base64)), 2)

    def test_pdf_date_overlay_scales_uniformly(self):
        # The date overlay's horizontal and vertical scale factors into the
        # placement rectangle are equal, so the text carries no aspect
        # distortion.
        date_cm, signature_cm = _pdf_cms(placement(), date="2026-09-22")

        self.assertLess(date_cm[4], signature_cm[4])
        ratio = date_cm[0] / date_cm[3]
        self.assertGreater(ratio, 0.9)
        self.assertLess(ratio, 1.1)

    def test_oversized_date_strip_is_rejected_before_rendering(self):
        # A 4 x 2 m date strip would render a 23622 x 23622 px raster at the
        # 300 dpi overlay density, past the per-side limit.
        with mock.patch.object(
            stamping,
            "_render_date_image",
            side_effect=AssertionError("date rendered before the size check"),
        ) as render:
            with self.assertRaises(ValueError) as ctx:
                stamping.stamp_pdf(
                    sentinel_pdf_b64(),
                    stamping.StampRequest(
                        image=signature_png_b64(),
                        placement=stamping.StampPlacement(
                            x=0.0, y=0.0, width=4000.0, height=2000.0
                        ),
                        date="2026-09-22",
                    ),
                )

        render.assert_not_called()
        self.assertIn("date strip", str(ctx.exception))

    def test_zpl_date_composites_into_a_single_raster(self):
        # A supplied date is drawn into the same 1-bpp raster as the signature,
        # so only one GRF graphic is emitted and it differs from the date-less one.
        def stamp(**fields):
            return decode_zpl(
                stamping.stamp_zpl(
                    zpl_doc_b64(),
                    stamping.StampRequest(
                        image=signature_png_b64(), placement=zpl_placement(), **fields
                    ),
                )
            )

        with_date = grf_fields(stamp(date="2026-09-22"))

        self.assertEqual(len(with_date), 1)
        self.assertNotEqual(with_date[0][5], grf_fields(stamp())[0][5])


class TestZplDateRenderFidelity(unittest.TestCase):
    """Render-contract oracles for the date strip in the ZPL raster.

    Expected bounds derive from the glyph-height fraction of the placement's
    short axis, font metrics Pillow measures independently in the test, and the
    480 x 160-dot geometry of ``zpl_placement`` at 203 dpi.
    """

    # Pinned as a literal so a constant change fails here rather than being
    # tracked silently. DATE's natural width at this size exceeds the 240-dot
    # date half, so the shrink step normalizes it; the short-date oracle is the
    # one that observes the constant directly.
    DATE_FONT_HEIGHT_FRACTION = 0.30

    DATE = "2026-09-22"

    SHORT_DATE = "9/22"

    def _raster(self, date: str = DATE) -> "PIL.Image.Image":
        return stamping._build_zpl_raster(
            stamping.StampRequest(
                image=signature_png_b64(), placement=zpl_placement(), date=date
            )
        )

    @staticmethod
    def _ink_band(raster, x_start: int, x_stop: int):
        pixels = raster.load()
        width, height = raster.size
        rows = [
            y
            for y in range(height)
            if any(pixels[x, y] == 0 for x in range(x_start, x_stop))
        ]
        cols = [
            x
            for x in range(x_start, x_stop)
            if any(pixels[x, y] == 0 for y in range(height))
        ]
        return rows, cols

    def _font(self, height: int):
        return PIL.ImageFont.load_default(
            size=int(round(height * self.DATE_FONT_HEIGHT_FRACTION))
        )

    def test_date_glyphs_render_within_the_fraction_height(self):
        # The ink band sits strictly inside the short axis and within the
        # glyph-height bound (em size plus antialiasing), not edge-to-edge.
        raster = self._raster()
        width, height = raster.size

        rows, _ = self._ink_band(raster, 0, width // 2)

        self.assertTrue(rows)
        bound = int(round(height * self.DATE_FONT_HEIGHT_FRACTION)) + 2
        self.assertLessEqual(rows[-1] - rows[0] + 1, bound)
        self.assertGreater(rows[0], 0)
        self.assertLess(rows[-1], height - 1)

    def test_date_preserves_its_natural_aspect(self):
        # The ink band's width/height ratio stays within tolerance of the ratio
        # Pillow measures for the same string at the contract font size.
        raster = self._raster()
        width, height = raster.size

        ruler = PIL.ImageDraw.Draw(PIL.Image.new("RGBA", (1, 1)))
        left, top, right, bottom = ruler.textbbox(
            (0, 0), self.DATE, font=self._font(height)
        )
        natural = (right - left) / max(bottom - top, 1)

        rows, cols = self._ink_band(raster, 0, width // 2)
        observed = (cols[-1] - cols[0] + 1) / (rows[-1] - rows[0] + 1)

        self.assertGreater(observed, natural * 0.7)
        self.assertLess(observed, natural * 1.4)

    def test_short_date_tracks_the_contract_font_height(self):
        # A string narrow enough for the date half takes no shrink step, so its
        # ink band must match the ink height Pillow measures for it at the
        # contract size (0.40 renders 49 rows and 0.25 renders 31 against a
        # natural 36 on this geometry).
        raster = self._raster(date=self.SHORT_DATE)
        width, height = raster.size

        ruler = PIL.ImageDraw.Draw(PIL.Image.new("RGBA", (1, 1)))
        left, top, right, bottom = ruler.textbbox(
            (0, 0), self.SHORT_DATE, font=self._font(height)
        )
        self.assertLessEqual(right - left, width // 2)

        rows, _ = self._ink_band(raster, 0, width // 2)
        band = rows[-1] - rows[0] + 1
        natural = bottom - top
        self.assertGreaterEqual(band, natural - 3)
        self.assertLessEqual(band, natural + 2)

    def test_date_region_carries_no_isolated_speckle_pixels(self):
        # Threshold binarization leaves no single-pixel ink dots isolated from
        # the glyph strokes; error diffusion scatters them across the date half.
        raster = self._raster()
        width, height = raster.size
        pixels = raster.load()

        isolated = [
            (x, y)
            for y in range(height)
            for x in range(0, width // 2)
            if pixels[x, y] == 0
            and all(
                pixels[nx, ny] != 0
                for nx in range(max(0, x - 1), min(width, x + 2))
                for ny in range(max(0, y - 1), min(height, y + 2))
                if (nx, ny) != (x, y)
            )
        ]

        self.assertEqual(isolated, [])

    def test_a_long_date_shrinks_to_fit_the_date_sub_rectangle(self):
        # A caller-owned string wider than the date half at the contract height
        # shrinks its glyphs to fit rather than distorting or running into the
        # signature half.
        raster = self._raster(date="22 september 2026, 14:35:07")
        width, height = raster.size

        rows, cols = self._ink_band(raster, 0, width // 2)

        self.assertTrue(rows)
        bound = int(round(height * self.DATE_FONT_HEIGHT_FRACTION)) + 2
        band = rows[-1] - rows[0] + 1
        self.assertLessEqual(band, bound)
        self.assertGreaterEqual(band, 6)
        self.assertLessEqual(cols[-1], width // 2 - 1)


if __name__ == "__main__":
    unittest.main()
