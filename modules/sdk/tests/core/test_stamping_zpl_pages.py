"""Document stamping: the ZPL format a stamp lands in, selected by page."""

import unittest

import karrio.lib as lib
import karrio.core.models as models
import karrio.core.utils.stamping as stamping

from .stamping_helpers import (
    KEYWORD,
    ZPL_FORMAT_ONE,
    ZPL_TRAILING_TEXT,
    decode_zpl,
    grf_fields,
    providers,
    seeded_provider,
    signature_png_b64,
    stamp_field,
    two_format_zpl,
    zpl_doc_b64,
)

# A 20 x 10 mm stamp at (5, 5) mm: ^FO40,40 at 203 dpi.
PLACEMENT = dict(x=5.0, y=5.0, width=20.0, height=10.0)


def _stamp(stream, **placement):
    return decode_zpl(
        stamping.stamp_zpl(
            zpl_doc_b64(stream),
            stamping.StampRequest(
                image=signature_png_b64(),
                placement=stamping.StampPlacement(**{**PLACEMENT, **placement}),
            ),
        )
    )


def _document(stream):
    return models.ShippingDocument(
        category="customs_declaration", format="ZPL", base64=zpl_doc_b64(stream)
    )


class TestZplFormatSelection(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def assertSpliced(self, stream, zpl, position):
        field = stamp_field(zpl)
        self.assertEqual(zpl, stream[:position] + field + stream[position:])

    def test_default_page_stamps_the_first_format(self):
        stream = two_format_zpl()
        # The first ^XZ closes ZPL_FORMAT_ONE, 3 characters before its end.
        self.assertSpliced(stream, _stamp(stream), len(ZPL_FORMAT_ONE) - 3)

    def test_page_two_stamps_the_second_format(self):
        stream = two_format_zpl()
        # The second ^XZ opens the trailing ^FX text's final 3 characters back.
        position = len(stream) - len(ZPL_TRAILING_TEXT) - 3

        self.assertSpliced(stream, _stamp(stream, page=2), position)

    def test_swapped_formats_keep_their_order(self):
        stream = two_format_zpl(swapped=True)
        position = len(stream) - len(ZPL_TRAILING_TEXT) - 3

        self.assertSpliced(stream, _stamp(stream, page=2), position)

    def test_unterminated_second_format_is_closed_after_the_field(self):
        stream = two_format_zpl(terminated=False)
        zpl = _stamp(stream, page=2)

        self.assertEqual(zpl, stream + stamp_field(zpl) + "^XZ")

    def test_trailing_comment_text_is_not_a_format(self):
        with self.assertRaises(ValueError) as ctx:
            _stamp(ZPL_FORMAT_ONE + ZPL_TRAILING_TEXT, page=2)

        self.assertIn("StampPlacement.page", str(ctx.exception))
        self.assertIn("1 ZPL format(s)", str(ctx.exception))

    def test_page_beyond_the_formats_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            _stamp(two_format_zpl(), page=3)

        self.assertIn("StampPlacement.page", str(ctx.exception))
        self.assertIn("2 ZPL format(s)", str(ctx.exception))


class TestStampDocumentZplPage(unittest.TestCase):
    # A 20 x 10 mm geometry at the keyword: the first format's field is at
    # ^FO20,35 and the second's at ^FO25,45.
    GEOMETRY = stamping.StampPlacement(width=20.0, height=10.0)

    def test_page_restricts_a_keyword_search_to_that_format(self):
        stream = two_format_zpl()
        stamped = lib.stamp_document(
            _document(stream),
            image=signature_png_b64(),
            keyword=KEYWORD,
            placement=self.GEOMETRY,
            page=2,
        )

        zpl = decode_zpl(stamped.base64)
        ((fo_x, fo_y, *_),) = grf_fields(zpl)
        self.assertEqual((fo_x, fo_y), (25, 45))
        self.assertTrue(zpl.startswith(ZPL_FORMAT_ONE))

    def test_keyword_without_a_page_lands_in_the_first_matching_format(self):
        stamped = lib.stamp_document(
            _document(two_format_zpl(swapped=True)),
            image=signature_png_b64(),
            keyword=KEYWORD,
            placement=self.GEOMETRY,
        )

        zpl = decode_zpl(stamped.base64)
        ((fo_x, fo_y, *_),) = grf_fields(zpl)
        self.assertEqual((fo_x, fo_y), (25, 45))
        self.assertLess(zpl.index("^GFA"), zpl.index("^XZ"))

    def test_page_applies_a_seed_to_that_format(self):
        seed = stamping.StampSeed(keyword=KEYWORD, keyword_placement=self.GEOMETRY)
        stream = two_format_zpl()
        with providers(seeded_provider({"customs_declaration/ZPL/*": seed})):
            stamped = lib.stamp_document(
                _document(stream),
                image=signature_png_b64(),
                carrier="acme",
                doc_type="customs_declaration",
                page=2,
            )

        zpl = decode_zpl(stamped.base64)
        ((fo_x, fo_y, *_),) = grf_fields(zpl)
        self.assertEqual((fo_x, fo_y), (25, 45))
        self.assertTrue(zpl.startswith(ZPL_FORMAT_ONE))

    def test_page_applies_an_injected_registry_placement_to_that_format(self):
        stream = two_format_zpl()
        stamped = lib.stamp_document(
            _document(stream),
            image=signature_png_b64(),
            carrier="acme",
            doc_type="customs_declaration",
            registry=lambda key: stamping.StampPlacement(**PLACEMENT),
            page=2,
        )

        zpl = decode_zpl(stamped.base64)
        position = len(stream) - len(ZPL_TRAILING_TEXT) - 3
        field = stamp_field(zpl)
        self.assertEqual(zpl, stream[:position] + field + stream[position:])
        self.assertTrue(field.startswith("^FO40,40^GFA"))

    def test_page_with_a_fully_anchored_placement_still_raises(self):
        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(
                _document(two_format_zpl()),
                image=signature_png_b64(),
                placement=stamping.StampPlacement(**PLACEMENT),
                page=2,
            )

        self.assertIn("fully anchored placement", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
