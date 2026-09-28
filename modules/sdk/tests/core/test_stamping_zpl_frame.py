"""Document stamping: ZPL keyword anchoring in the field's reading frame and format."""

import unittest

import karrio.lib as lib
import karrio.core.models as models
import karrio.core.utils.stamping as stamping

from .stamping_helpers import (
    EXAMPLE_SEED,
    EXAMPLE_ZPL_FORM,
    KEYWORD,
    decode_zpl,
    grf_fields,
    keyword_zpl_document,
    providers,
    seeded_provider,
    signature_png_b64,
)

# The example seed's rotated strip expressed in the keyword field's reading
# frame. The form's keyword field is ^FWR-rotated at ^FO20,35 under
# ^CF0,20,20, so its text starts at the glyph-top side of the 20-dot cell,
# page dots (40, 35). The strip starts 33.529 mm along the text and 3.4245 mm
# above the cell top, 49.1 x 7.6 mm along the text: page ^FO7,303, the same
# 61 x 392-dot raster the page-axis offset (-1.673, 33.529) mm produces.
FRAME_GEOMETRY = stamping.StampPlacement(
    x=33.529, y=-3.4245, width=49.1, height=7.6, rotation=0, dpi=203
)

FRAME_SEED = stamping.StampSeed(
    keyword=KEYWORD, zpl_keyword_frame_placement=FRAME_GEOMETRY
)

# A parcel label format followed by an upright CN22 format opened by a
# redundant header ^XA, as carrier printouts compose them.
LABEL_FORMAT = "^XA^LL1520^FWR^FO30,40^FDPARCEL LABEL^FS^XZ"

UPRIGHT_CN22_FORMAT = "\n".join(
    [
        "^XA",
        "^LL840",
        "^XA",
        "^FWN",
        "^CF0,18,18",
        "^FO10,15^GB820,820,1^FS",
        "^FO25,785",
        "^FDSender signature^FS",
        "^XZ",
    ]
)

# FRAME_GEOMETRY on the upright field at ^FO25,785: the text frame's origin is
# the ^FO itself, so the strip lands at 25 + 33.529 mm = 292.97 -> 293 and
# 785 - 3.4245 mm = 757.63 -> 758 dots, unrotated: 49.1 mm = 392 dots wide
# (49 bytes per row) by 7.6 mm = 61 dots.
UPRIGHT_ORIGIN = (293, 758)
UPRIGHT_GRF = (49, 49 * 61)


def _stamp(stream: str, seed: stamping.StampSeed) -> str:
    with providers(seeded_provider({"customs_declaration/ZPL/*": seed})):
        stamped = lib.stamp_document(
            keyword_zpl_document(stream),
            image=signature_png_b64(),
            carrier="acme",
            doc_type="customs_declaration",
        )

    return decode_zpl(stamped.base64)


def _single_field(zpl: str) -> str:
    start = zpl.rindex("^FO", 0, zpl.index("^GFA"))
    return zpl[start : zpl.index("^FS", start) + 3]


class TestZplFieldMatch(unittest.TestCase):
    def test_orientation_follows_the_formats_latest_fw(self):
        match = stamping._match_zpl_field(EXAMPLE_ZPL_FORM, KEYWORD)

        self.assertEqual(
            (match.origin, match.orientation, match.height, match.format_index),
            ((20.0, 35.0), 90, 20.0, 0),
        )

    def test_fw_does_not_leak_into_the_next_format(self):
        stream = "^XA^FWR^CF0,40^FO1,1^FDx^FS^XZ^XA^FO25,785^FDSender signature^FS^XZ"
        match = stamping._match_zpl_field(stream, KEYWORD)

        self.assertEqual(
            (match.origin, match.orientation, match.height, match.format_index),
            ((25.0, 785.0), 0, 9.0, 1),
        )

    def test_field_font_orientation_overrides_fw(self):
        stream = "^XA^FWN^CF0,18,18^FO100,200^A0R,30,30^FDSender signature^FS^XZ"
        match = stamping._match_zpl_field(stream, KEYWORD)

        self.assertEqual((match.orientation, match.height), (90, 30.0))

    def test_field_font_orientation_ends_with_its_field(self):
        stream = "^XA^FWN^FO1,1^A0R,30^FDx^FS^FO100,200^FDSender signature^FS^XZ"
        match = stamping._match_zpl_field(stream, KEYWORD)

        self.assertEqual((match.orientation, match.height), (0, 9.0))

    def test_field_font_without_orientation_keeps_fw(self):
        stream = "^XA^FWR^FO100,200^A0,30,30^FDSender signature^FS^XZ"
        match = stamping._match_zpl_field(stream, KEYWORD)

        self.assertEqual((match.orientation, match.height), (90, 30.0))


class TestZplFormatScoping(unittest.TestCase):
    def test_rotated_single_format_output_is_unchanged(self):
        # The page-axis seed keeps its behavior: ^FO7,303 with a 61 x 392-dot
        # raster spliced before the form's only ^XZ.
        zpl = _stamp(EXAMPLE_ZPL_FORM, EXAMPLE_SEED)

        ((fo_x, fo_y, total, _, bpr, _),) = grf_fields(zpl)
        self.assertEqual((fo_x, fo_y, bpr, total), (7, 303, 8, 3136))
        self.assertEqual(
            zpl, EXAMPLE_ZPL_FORM[: -len("^XZ")] + _single_field(zpl) + "^XZ"
        )

    def test_reading_frame_geometry_reproduces_the_rotated_output(self):
        self.assertEqual(
            _stamp(EXAMPLE_ZPL_FORM, FRAME_SEED), _stamp(EXAMPLE_ZPL_FORM, EXAMPLE_SEED)
        )

    def test_upright_keyword_in_the_second_format(self):
        stream = f"{LABEL_FORMAT}\n{UPRIGHT_CN22_FORMAT}"
        zpl = _stamp(stream, FRAME_SEED)

        ((fo_x, fo_y, total, _, bpr, _),) = grf_fields(zpl)
        self.assertEqual((fo_x, fo_y), UPRIGHT_ORIGIN)
        self.assertEqual((bpr, total), UPRIGHT_GRF)
        self.assertTrue(zpl.startswith(f"{LABEL_FORMAT}\n"))
        self.assertEqual(
            zpl,
            f"{LABEL_FORMAT}\n"
            + UPRIGHT_CN22_FORMAT[: -len("^XZ")]
            + _single_field(zpl)
            + "^XZ",
        )

    def test_keyword_in_the_first_format_splices_before_the_first_xz(self):
        stream = f"{UPRIGHT_CN22_FORMAT}\n{LABEL_FORMAT}"
        zpl = _stamp(stream, FRAME_SEED)

        ((fo_x, fo_y, *_),) = grf_fields(zpl)
        self.assertEqual((fo_x, fo_y), UPRIGHT_ORIGIN)
        self.assertEqual(
            zpl,
            UPRIGHT_CN22_FORMAT[: -len("^XZ")]
            + _single_field(zpl)
            + f"^XZ\n{LABEL_FORMAT}",
        )

    def test_page_axis_seed_also_splices_into_the_keyword_format(self):
        stream = f"{UPRIGHT_CN22_FORMAT}\n{LABEL_FORMAT}"
        zpl = _stamp(stream, EXAMPLE_SEED)

        self.assertTrue(zpl.endswith(f"^FS^XZ\n{LABEL_FORMAT}"))

    def test_field_font_orientation_overrides_fw_in_placement(self):
        # ^A0R,30,30 turns the field under ^FWN: the text starts at the
        # glyph-top side of the 30-dot cell, page dots (130, 200). The strip,
        # 5 mm along and 2 mm above the cell top, 20 x 6 mm, runs down the
        # page: x 130 - (6 - 2) mm = 98.03 -> 98, y 200 + 5 mm = 239.96 -> 240,
        # a 48 x 160-dot raster (6 bytes per row).
        stream = "^XA^FWN^CF0,18,18^FO100,200^A0R,30,30^FDSender signature^FS^XZ"
        seed = stamping.StampSeed(
            keyword=KEYWORD,
            zpl_keyword_frame_placement=stamping.StampPlacement(
                x=5.0, y=-2.0, width=20.0, height=6.0, rotation=0, dpi=203
            ),
        )

        ((fo_x, fo_y, total, _, bpr, _),) = grf_fields(_stamp(stream, seed))
        self.assertEqual((fo_x, fo_y, bpr, total), (98, 240, 6, 960))

    def test_frame_geometry_outranks_the_page_axis_geometry(self):
        seed = stamping.StampSeed(
            keyword=KEYWORD,
            keyword_placement=EXAMPLE_SEED.keyword_placement,
            zpl_keyword_frame_placement=FRAME_GEOMETRY,
        )
        stream = f"{LABEL_FORMAT}\n{UPRIGHT_CN22_FORMAT}"

        ((fo_x, fo_y, *_),) = grf_fields(_stamp(stream, seed))
        self.assertEqual((fo_x, fo_y), UPRIGHT_ORIGIN)

    def test_inverted_field_frame_raises_naming_the_orientation(self):
        stream = "^XA^FWI^FO100,200^FDSender signature^FS^XZ"

        with self.assertRaises(ValueError) as ctx:
            _stamp(stream, FRAME_SEED)

        self.assertIn(KEYWORD, str(ctx.exception))
        self.assertIn("180", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
