"""Document stamping: the ZPL backend (GRF raster, splice, printer cache, bounds)."""

import re
import math
import unittest
from unittest import mock

import PIL.Image

import karrio.lib as lib
import karrio.core.models as models
import karrio.core.utils.stamping as stamping

from .stamping_helpers import (
    EXAMPLE_ZPL_FORM,
    decode_zpl,
    example_zpl_form_b64,
    faint_stroke_png_b64,
    grf_fields,
    real_signature_b64,
    signature_png_b64,
    solid_black_png_b64,
    zpl_doc_b64,
    zpl_document,
    zpl_placement,
)


def _stamp(placement=None, image=None, **fields):
    return decode_zpl(
        stamping.stamp_zpl(
            zpl_doc_b64(),
            stamping.StampRequest(
                image=image or signature_png_b64(),
                placement=placement or zpl_placement(),
                **fields,
            ),
        )
    )


class TestZplGrfEncoding(unittest.TestCase):
    def test_all_black_block_packs_to_ff_per_row(self):
        # An 8x2 all-black block: each 8-px row fills exactly one byte with every
        # bit set, so the hex is FF twice (a set bit is black), one byte per row.
        image = PIL.Image.new("1", (8, 2), 0)

        hexdata, total, bytes_per_row = stamping._encode_grf(image)

        self.assertEqual(bytes_per_row, 1)
        self.assertEqual(total, 2)
        self.assertEqual(hexdata, "FFFF")

    def test_bit_order_is_msb_first(self):
        # A 4-px-wide row with black only at x=0 and x=3 packs MSB-first into the
        # high nibble: 0b1001_0000 = 0x90, and the sub-byte width pads to one byte.
        image = PIL.Image.new("1", (4, 1), 1)
        image.putpixel((0, 0), 0)
        image.putpixel((3, 0), 0)

        hexdata, total, bytes_per_row = stamping._encode_grf(image)

        self.assertEqual(bytes_per_row, 1)
        self.assertEqual(total, 1)
        self.assertEqual(hexdata, "90")

    def test_row_is_byte_padded_for_non_multiple_of_eight_width(self):
        # A 12-px row pads to two bytes: black at x=0 sets the first byte's MSB
        # (0x80) and black at x=11 sets bit 3 of the second byte (0x10), with
        # the trailing pad bits left clear.
        image = PIL.Image.new("1", (12, 1), 1)
        image.putpixel((0, 0), 0)
        image.putpixel((11, 0), 0)

        hexdata, total, bytes_per_row = stamping._encode_grf(image)

        self.assertEqual(bytes_per_row, 2)
        self.assertEqual(total, 2)
        self.assertEqual(hexdata, "8010")

    def test_hex_is_uppercase(self):
        # x=0 and x=4 set 0x88, confirming the encoder emits uppercase nibbles.
        image = PIL.Image.new("1", (8, 1), 1)
        image.putpixel((0, 0), 0)
        image.putpixel((4, 0), 0)

        hexdata, _, _ = stamping._encode_grf(image)

        self.assertEqual(hexdata, "88")
        self.assertEqual(hexdata, hexdata.upper())


class TestZplBackend(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_splices_single_grf_before_trailing_xz(self):
        zpl = _stamp()

        self.assertTrue(zpl.startswith("^XA"))
        self.assertEqual(zpl.count("^XZ"), 1)
        self.assertEqual(len(grf_fields(zpl)), 1)
        # The graphic is drawn last (overlay), so it lands before the final ^XZ.
        self.assertLess(zpl.index("^GFA,"), zpl.index("^XZ"))
        # The carrier field stream survives ahead of the spliced graphic.
        self.assertIn("^GB100,100,2^FS", zpl)

    def test_grf_header_matches_the_raster_dimensions(self):
        request = stamping.StampRequest(
            image=signature_png_b64(), placement=zpl_placement()
        )
        raster = stamping._build_zpl_raster(request)
        width, height = raster.size
        expected_bpr = math.ceil(width / 8)

        zpl = decode_zpl(stamping.stamp_zpl(zpl_doc_b64(), request))
        ((fo_x, fo_y, total, total2, bpr, hexdata),) = grf_fields(zpl)

        # 203 dpi: x=20 mm -> 160 dots, y=30 mm -> 240 dots (independent literals).
        self.assertEqual((fo_x, fo_y), (160, 240))
        self.assertEqual(bpr, expected_bpr)
        self.assertEqual(total, expected_bpr * height)
        self.assertEqual(total2, total)
        self.assertEqual(len(hexdata), total * 2)

    def test_underlay_layer_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            _stamp(layer="underlay")

        self.assertIn("underlay", str(ctx.exception).lower())

    def test_missing_image_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            stamping.stamp_zpl(
                zpl_doc_b64(), stamping.StampRequest(placement=zpl_placement())
            )

        self.assertIn("image", str(ctx.exception))


class TestZplRaster(unittest.TestCase):
    def _assert_connected_black_row(self, dpi):
        request = stamping.StampRequest(
            image=solid_black_png_b64(), placement=zpl_placement(dpi=dpi)
        )

        raster = stamping._build_zpl_raster(request)

        width, height = raster.size
        pixels = raster.load()
        # A solid-black stamp must survive flatten + resample + binarization as a
        # fully connected black run: at least one row is black (value 0) across
        # its entire width. The oracle is the raster's own pixels, not the GRF
        # encoder, so an inverted set-bit convention or a lost stroke fails here.
        self.assertTrue(
            any(all(pixels[x, y] == 0 for x in range(width)) for y in range(height))
        )

    def test_stroke_stays_connected_at_203_dpi(self):
        self._assert_connected_black_row(203)

    def test_stroke_stays_connected_at_300_dpi(self):
        self._assert_connected_black_row(300)

    def test_faint_signature_strokes_survive_as_connected_ink(self):
        # A semi-transparent stroke (flattens to gray ~115) survives the ink
        # threshold as one connected run spanning the stroke's length; error
        # diffusion would scatter it into fragments. The alpha-bbox trim crops
        # the stroke to its own extent, so after the resize it spans the full
        # raster width and 90% of the stroke is 90% of the width.
        request = stamping.StampRequest(
            image=faint_stroke_png_b64(), placement=zpl_placement()
        )

        raster = stamping._build_zpl_raster(request)
        width, height = raster.size
        pixels = raster.load()

        def longest_run(y):
            best = run = 0
            for x in range(width):
                run = run + 1 if pixels[x, y] == 0 else 0
                best = max(best, run)
            return best

        self.assertGreaterEqual(
            max(longest_run(y) for y in range(height)), int(width * 0.9)
        )


class TestZplPrinterCache(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_default_inline_path_is_unaffected_when_caching_off(self):
        request = stamping.StampRequest(
            image=signature_png_b64(), placement=zpl_placement()
        )

        first = stamping.stamp_zpl(zpl_doc_b64(), request)
        second = stamping.stamp_zpl(zpl_doc_b64(), request)
        zpl = decode_zpl(first)

        self.assertEqual(first, second)
        self.assertIn("^GFA,", zpl)
        self.assertNotIn("~DY", zpl)
        self.assertNotIn("^XG", zpl)

    def test_opt_in_emits_download_and_recall_with_matching_payload(self):
        inline = _stamp()
        cached = _stamp(graphic_name="R:STAMP.GRF")

        # The opt-in path downloads once (~DY) and recalls per label (^XG),
        # replacing the inline ^GFA entirely, with a matching object name.
        self.assertIn("~DYR:STAMP.GRF,", cached)
        self.assertIn("^XGR:STAMP.GRF,1,1", cached)
        self.assertNotIn("^GFA,", cached)

        # The stored GRF payload is byte-identical to what the inline path packs.
        ((_, _, inline_total, _, inline_bpr, inline_hex),) = grf_fields(inline)
        match = re.search(r"~DYR:STAMP\.GRF,A,G,(\d+),(\d+),([0-9A-F]*)", cached)
        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(1)), inline_total)
        self.assertEqual(int(match.group(2)), inline_bpr)
        self.assertEqual(match.group(3), inline_hex)

    def test_plain_object_names_are_accepted(self):
        for name in ("SIGN", "R:SIGN", "SIGN.GRF", "E:SIGN_01.GRF"):
            with self.subTest(name=name):
                self.assertIn(f"^XG{name},1,1", _stamp(graphic_name=name))

    def test_graphic_name_carrying_zpl_commands_is_rejected(self):
        # The name is interpolated into ~DY and ^XG, so a caret, tilde or comma
        # would splice extra commands into the printed label.
        for name in ("A^FDinjected", "A~JA", "SIGN,2,2", "TOOLONGNAME", "sign"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError) as ctx:
                    _stamp(graphic_name=name)

                self.assertIn("graphic name", str(ctx.exception))


class TestZplBounds(unittest.TestCase):
    def test_negative_anchor_is_rejected_naming_the_field(self):
        with self.assertRaises(ValueError) as ctx:
            _stamp(
                placement=stamping.StampPlacement(
                    x=-1.0, y=0.0, width=60.0, height=20.0, dpi=203
                )
            )

        self.assertIn("StampPlacement.x", str(ctx.exception))

    def test_rejects_operands_beyond_the_zpl_range(self):
        # 4006 mm at 203 dpi resolves past 32000 dots, the ^FO operand maximum.
        with self.assertRaises(ValueError) as ctx:
            _stamp(
                placement=stamping.StampPlacement(
                    x=4006.0, y=0.0, width=60.0, height=20.0, dpi=203
                )
            )

        self.assertIn("32000", str(ctx.exception))

    def test_rejects_an_in_range_origin_with_an_extent_beyond_the_range(self):
        # The origin (100 mm -> 799 dots) is well inside 0-32000; only the
        # raster's width (3910 mm -> 31249 dots) pushes the x extent to 32048,
        # so an origin-only guard would not raise here at all.
        with self.assertRaises(ValueError) as ctx:
            _stamp(
                placement=stamping.StampPlacement(
                    x=100.0, y=0.0, width=3910.0, height=1.0, dpi=203
                )
            )

        self.assertIn("x extent", str(ctx.exception))
        self.assertIn("32048", str(ctx.exception))

    def test_accepts_an_extent_resolving_exactly_to_the_boundary(self):
        # 8128 mm at 100 dpi is exactly 32000 dots (25.4 * 32000 = 812800), so
        # an origin of 0 puts the x extent exactly on the operand maximum,
        # which is in-range and must stamp rather than raise.
        zpl = _stamp(
            placement=stamping.StampPlacement(
                x=0.0, y=0.0, width=8128.0, height=1.0, dpi=100
            )
        )

        self.assertIn("^FO0,0", zpl)

    def test_range_check_runs_before_the_raster_is_built(self):
        # A 100 m square placement asks for an ~800k x 800k-dot canvas; the
        # operand check must reject it from the placement alone, before any
        # raster allocation.
        with mock.patch.object(
            stamping,
            "_build_zpl_raster",
            side_effect=AssertionError("raster built before the range check"),
        ) as build:
            with self.assertRaises(ValueError) as ctx:
                _stamp(
                    placement=stamping.StampPlacement(
                        x=1.0, y=1.0, width=100000.0, height=100000.0, dpi=203
                    )
                )

        build.assert_not_called()
        self.assertIn("operand range", str(ctx.exception))


class TestStampDocumentZpl(unittest.TestCase):
    def test_stamps_zpl_document(self):
        stamped = lib.stamp_document(
            zpl_document(), image=signature_png_b64(), placement=zpl_placement()
        )

        self.assertEqual(stamped.format, "ZPL")
        zpl = decode_zpl(stamped.base64)
        self.assertTrue(zpl.startswith("^XA"))
        self.assertIn("^GFA,", zpl)
        self.assertLess(zpl.index("^GFA,"), zpl.rindex("^XZ"))

    def test_graphic_name_threads_through_lib_stamp_document(self):
        stamped = lib.stamp_document(
            zpl_document(),
            image=signature_png_b64(),
            placement=zpl_placement(),
            graphic_name="MYSIG",
        )

        zpl = decode_zpl(stamped.base64)
        self.assertIn("~DYMYSIG,", zpl)
        self.assertIn("^XGMYSIG,1,1", zpl)
        self.assertNotIn("^GFA,", zpl)

    def test_default_path_omits_the_zpl_cache(self):
        stamped = lib.stamp_document(
            zpl_document(), image=signature_png_b64(), placement=zpl_placement()
        )

        zpl = decode_zpl(stamped.base64)
        self.assertIn("^GFA,", zpl)
        self.assertNotIn("~DY", zpl)
        self.assertNotIn("^XG", zpl)


class TestExampleZplForm(unittest.TestCase):
    """The real signature against a carrier-style ZPL form."""

    # A 33 x 12 mm strip at (5, 100) mm and 203 dpi: 40/799/264/96 dots, in
    # the blank stock below the form box.
    PLACEMENT = stamping.StampPlacement(x=5.0, y=100.0, width=33.0, height=12.0)

    def setUp(self):
        self.maxDiff = None
        self.request = stamping.StampRequest(
            image=real_signature_b64(), placement=self.PLACEMENT
        )

    def test_form_fixture_carries_the_traits_the_backend_must_tolerate(self):
        self.assertTrue(EXAMPLE_ZPL_FORM.startswith("^XA"))
        self.assertEqual(EXAMPLE_ZPL_FORM.count("^XA"), 2)
        self.assertIn("^LL1520", EXAMPLE_ZPL_FORM)
        self.assertIn("^FWR", EXAMPLE_ZPL_FORM)
        self.assertNotIn("^GFA", EXAMPLE_ZPL_FORM)

    def test_stamp_splices_one_grf_onto_the_form(self):
        zpl = decode_zpl(stamping.stamp_zpl(example_zpl_form_b64(), self.request))

        self.assertTrue(zpl.startswith("^XA"))
        self.assertEqual(zpl.count("^XZ"), 1)
        self.assertIn("CUSTOMS DECLARATION", zpl)
        self.assertIn("REF0012345", zpl)
        ((fo_x, fo_y, total, total2, bpr, hexdata),) = grf_fields(zpl)
        self.assertEqual((fo_x, fo_y), (40, 799))
        self.assertEqual((bpr, total, total2), (33, 3168, 3168))
        self.assertEqual(len(hexdata), total * 2)
        self.assertLess(zpl.index("^GFA,"), zpl.rindex("^XZ"))

    def test_real_signature_keeps_ink_through_flatten_and_threshold(self):
        raster = stamping._build_zpl_raster(self.request)

        self.assertEqual(raster.mode, "1")
        self.assertEqual(raster.size, (264, 96))
        fraction = raster.histogram()[0] / (264 * 96)
        # Sparse anti-aliased ink survives as neither blank nor solid.
        self.assertGreater(fraction, 0.005)
        self.assertLess(fraction, 0.30)

    def test_lib_stamp_document_returns_a_new_zpl_document(self):
        document = models.ShippingDocument(
            category="customs_declaration", format="ZPL", base64=example_zpl_form_b64()
        )

        stamped = lib.stamp_document(
            document, image=real_signature_b64(), placement=self.PLACEMENT
        )

        self.assertEqual(stamped.format, "ZPL")
        self.assertEqual(stamped.category, document.category)
        self.assertIn("^GFA,", decode_zpl(stamped.base64))
        self.assertEqual(document.base64, example_zpl_form_b64())


if __name__ == "__main__":
    unittest.main()
