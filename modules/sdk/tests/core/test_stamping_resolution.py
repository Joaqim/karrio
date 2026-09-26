"""Document stamping: anchor resolution from plugin seeds and ZPL keywords."""

import unittest

import karrio.lib as lib
import karrio.core.models as models
import karrio.core.metadata as metadata
import karrio.core.utils.stamping as stamping

from .stamping_helpers import (
    EXAMPLE_SEED,
    FLOAT_FO_STREAM,
    FORM_IMAGE_Y_PT,
    INLINE_KEYWORD_STREAM,
    KEYWORD,
    LINE_KEYWORD_STREAM,
    MULTILINE_FD_STREAM,
    TWICE_KEYWORD_STREAM,
    b64,
    blank_pdf_b64,
    cms_in_y_band,
    decode_zpl,
    example_providers,
    example_zpl_form_b64,
    form_pdf_b64,
    grf_fields,
    keyword_zpl_document,
    pdf_document,
    placement,
    providers,
    real_signature_b64,
    seeded_provider,
    signature_png_b64,
    zpl_placement,
)

# The example seed's PDF strip, spelled out as independent literals: a
# vertical strip spanning page x 53.34-60.96 mm and y 91.44-140.55 mm on the
# generated 842 pt tall A4 page, encoded as a pre-rotation 49.11 x 7.62 mm
# extent at rotation 90 anchored top-left at (53.34, 91.44).
_STRIP_ANCHOR_MM = (53.34, 91.44)
_STRIP_EXTENT_MM = (49.11, 7.62)
_PAGE_HEIGHT_PT = 842.0


def _example_form_document() -> models.ShippingDocument:
    return models.ShippingDocument(
        category="customs_declaration", format="ZPL", base64=example_zpl_form_b64()
    )


def _form_pdf_document(with_image: bool = True) -> models.ShippingDocument:
    return models.ShippingDocument(
        category="customs_declaration",
        format="PDF",
        base64=form_pdf_b64(with_image=with_image),
    )


class TestPaperVariantDetection(unittest.TestCase):
    def test_detects_a4_from_mediabox_points(self):
        self.assertEqual(stamping._nearest_paper_variant(595.276, 841.890), "A4")

    def test_detects_letter_from_mediabox_points(self):
        # US Letter mediabox in points (216 x 279 mm = 612 x 792 pt).
        self.assertEqual(stamping._nearest_paper_variant(612.0, 792.0), "LETTER")

    def test_detection_is_orientation_independent(self):
        self.assertEqual(stamping._nearest_paper_variant(841.890, 595.276), "A4")

    def test_unknown_size_is_inconclusive(self):
        self.assertEqual(stamping._nearest_paper_variant(500.0, 500.0), "*")

    def test_generated_form_detects_a4(self):
        self.assertEqual(stamping._detect_paper_variant(form_pdf_b64(), "PDF"), "A4")

    def test_non_pdf_format_is_inconclusive(self):
        self.assertEqual(stamping._detect_paper_variant(b64(b"^XA^XZ"), "ZPL"), "*")

    def test_unparseable_pdf_is_inconclusive(self):
        self.assertEqual(
            stamping._detect_paper_variant(b64(b"%PDF-1.4 garbage"), "PDF"), "*"
        )


class TestRegistryKey(unittest.TestCase):
    def test_category_normalization_converges(self):
        # The value form, the name form, and one composed literal all agree, so
        # a seed registered under either spelling resolves for the other.
        self.assertEqual(
            stamping._registry_key("acme", "CustomsDeclaration", "PDF", "A4"),
            stamping._registry_key("acme", "customs_declaration", "PDF", "A4"),
        )
        self.assertEqual(
            stamping._registry_key("acme", "CustomsDeclaration", "PDF", "A4"),
            "acme/customs_declaration/PDF/A4",
        )

    def test_unrecognized_doc_type_falls_back_to_raw(self):
        # A carrier's own form name is not a category member, so it survives
        # verbatim rather than crashing the lookup.
        self.assertEqual(
            stamping._registry_key("acme", "cn23", "PDF", "A4"),
            "acme/cn23/PDF/A4",
        )

    def test_missing_segments_become_star(self):
        self.assertEqual(stamping._registry_key(None, None, "PDF", "*"), "*/*/PDF/*")


class TestPluginSeeds(unittest.TestCase):
    def test_plugin_metadata_declares_no_seeds_by_default(self):
        self.assertIsNone(metadata.PluginMetadata(id="acme", label="Acme").stamp_seeds)

    def test_seed_resolves_from_the_carrier_plugin(self):
        with example_providers():
            resolved = stamping._default_registry("acme/customs_declaration/PDF/A4")

        self.assertEqual(resolved, EXAMPLE_SEED.placement)

    def test_unseeded_key_misses(self):
        with example_providers():
            self.assertIsNone(stamping._default_registry("acme/unknown/PDF/A4"))
            self.assertIsNone(
                stamping._default_registry("other/customs_declaration/PDF/A4")
            )

    def test_paper_agnostic_seed_resolves_via_fallback(self):
        seed = stamping.StampSeed(placement=placement())

        with providers(seeded_provider({"receipt/PDF/*": seed})):
            resolved = stamping._default_registry("acme/receipt/PDF/LETTER")

        self.assertEqual(resolved, placement())

    def test_paper_specific_seed_does_not_leak_across_variants(self):
        # The A4 seed must not resolve for a LETTER page: the fallback only
        # relaxes to "*", never across concrete paper variants.
        with example_providers():
            self.assertIsNone(
                stamping._default_registry("acme/customs_declaration/PDF/LETTER")
            )

    def test_a_key_without_a_carrier_never_loads_plugins(self):
        with providers() as collect:
            self.assertIsNone(stamping._default_registry("*/*/PDF/A4"))

        collect.assert_not_called()


class TestRegistryResolution(unittest.TestCase):
    def test_supplied_placement_skips_registry(self):
        def exploding_registry(key):
            raise AssertionError(f"registry consulted for {key!r}")

        stamped = lib.stamp_document(
            pdf_document(),
            image=signature_png_b64(),
            placement=placement(),
            registry=exploding_registry,
        )

        self.assertEqual(stamped.format, "PDF")

    def test_registry_consulted_only_on_omission(self):
        seen = []

        def seed_registry(key):
            seen.append(key)
            return placement()

        stamped = lib.stamp_document(
            pdf_document(),
            image=signature_png_b64(),
            carrier="acme",
            doc_type="cn23",
            registry=seed_registry,
        )

        self.assertEqual(stamped.format, "PDF")
        self.assertEqual(seen, ["acme/cn23/PDF/A4"])

    def test_registry_miss_raises_naming_the_key(self):
        with example_providers():
            with self.assertRaises(ValueError) as ctx:
                lib.stamp_document(
                    pdf_document(),
                    image=signature_png_b64(),
                    carrier="acme",
                    doc_type="commercial_invoice",
                )

        self.assertIn("acme/commercial_invoice/PDF/A4", str(ctx.exception))

    def test_unkeyed_lookup_misses(self):
        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(pdf_document(), image=signature_png_b64())

        self.assertIn("*/*/PDF/A4", str(ctx.exception))


class TestSeededPdfStamp(unittest.TestCase):
    """The example seed on a PDF form that draws its own image.

    The form's own image transform sits at ``FORM_IMAGE_Y_PT`` (151.7 pt), so
    the stamp overlays are isolated by the strip's band: translations at
    582.8 pt (date or lone signature) and 513.2 pt (signature after the date).
    """

    def _anchor_pt(self):
        # For rotation 90 the merged overlay's translation equals its anchor,
        # computed here from the strip literals and the A4 page height.
        return (
            _STRIP_ANCHOR_MM[0] * 72.0 / 25.4,
            _PAGE_HEIGHT_PT - _STRIP_ANCHOR_MM[1] * 72.0 / 25.4,
        )

    def _assert_clockwise_quarter_turn(self, cm):
        self.assertAlmostEqual(cm[0], 0.0, places=6)
        self.assertAlmostEqual(cm[3], 0.0, places=6)
        self.assertLess(cm[1], 0.0)
        self.assertGreater(cm[2], 0.0)

    def test_seed_composites_date_and_signature_at_the_strip(self):
        with example_providers():
            stamped = lib.stamp_document(
                _form_pdf_document(),
                image=signature_png_b64(),
                date="2026-09-22",
                carrier="acme",
                doc_type="customs_declaration",
            )

        anchor_x, anchor_y = self._anchor_pt()
        date_width_pt = _STRIP_EXTENT_MM[0] * 72.0 / 25.4 * 0.5
        band = cms_in_y_band(stamped.base64, 505.0, 590.0)

        self.assertEqual(len(band), 2)
        self.assertLess(FORM_IMAGE_Y_PT, 505.0)
        date_cm, signature_cm = band
        # Under clockwise rotation the strip reads downward from its top-left
        # anchor, so the date leads with the greater translation-y.
        self.assertGreater(date_cm[5], signature_cm[5])
        self.assertAlmostEqual(date_cm[4], anchor_x, places=1)
        self.assertAlmostEqual(date_cm[5], anchor_y, places=1)
        self.assertAlmostEqual(signature_cm[4], anchor_x, places=1)
        self.assertAlmostEqual(signature_cm[5], anchor_y - date_width_pt, places=1)
        for cm in band:
            self._assert_clockwise_quarter_turn(cm)

    def test_seed_composites_the_real_signature_clockwise(self):
        with example_providers():
            stamped = lib.stamp_document(
                _form_pdf_document(),
                image=real_signature_b64(),
                carrier="acme",
                doc_type="customs_declaration",
            )

        anchor_x, anchor_y = self._anchor_pt()
        (cm,) = cms_in_y_band(stamped.base64, 575.0, 590.0)

        self.assertAlmostEqual(cm[4], anchor_x, places=1)
        self.assertAlmostEqual(cm[5], anchor_y, places=1)
        self._assert_clockwise_quarter_turn(cm)


class TestZplKeywordLocator(unittest.TestCase):
    def test_inline_stream_locates_the_nearest_preceding_fo(self):
        self.assertEqual(
            stamping._locate_zpl_field(INLINE_KEYWORD_STREAM, KEYWORD), (10.0, 20.0)
        )

    def test_newline_separated_stream_skips_fb_blocks(self):
        # The scan keys on ^FD..^FS blocks, so ^FB tokens are never confused
        # with field text and the preceding ^FO20,35 (not the earlier
        # ^FO160,240 of the Total Weight field) is the matched field's origin.
        self.assertEqual(
            stamping._locate_zpl_field(LINE_KEYWORD_STREAM, KEYWORD), (20.0, 35.0)
        )

    def test_float_fo_operands_parse_as_floats(self):
        self.assertEqual(
            stamping._locate_zpl_field(FLOAT_FO_STREAM, "Total Weight"),
            (385.0, 488.3333333333333),
        )

    def test_multi_line_fd_text_matches_within_one_block(self):
        self.assertEqual(
            stamping._locate_zpl_field(MULTILINE_FD_STREAM, "in this declaration"),
            (25.0, 35.0),
        )

    def test_first_match_in_stream_order_wins(self):
        self.assertEqual(
            stamping._locate_zpl_field(TWICE_KEYWORD_STREAM, KEYWORD), (20.0, 35.0)
        )

    def test_miss_raises_naming_the_keyword(self):
        with self.assertRaises(ValueError) as ctx:
            stamping._locate_zpl_field(LINE_KEYWORD_STREAM, "no such field text")

        self.assertIn("no such field text", str(ctx.exception))

    def test_field_without_a_preceding_origin_raises(self):
        with self.assertRaises(ValueError) as ctx:
            stamping._locate_zpl_field("^XA^FDSender signature^FS^XZ", KEYWORD)

        self.assertIn("^FO", str(ctx.exception))


class TestKeywordResolution(unittest.TestCase):
    def test_keyword_with_a_fully_anchored_placement_raises(self):
        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(
                keyword_zpl_document(INLINE_KEYWORD_STREAM),
                image=signature_png_b64(),
                placement=zpl_placement(),
                keyword=KEYWORD,
            )

        self.assertIn("placement", str(ctx.exception).lower())
        self.assertIn("keyword", str(ctx.exception).lower())

    def test_keyword_with_geometry_only_placement_resolves_from_the_form(self):
        # The geometry-only placement carries extent/rotation/dpi while the
        # position comes from the located ^FO160,240 origin; integer dots
        # round-trip through millimetres unchanged.
        stamped = lib.stamp_document(
            keyword_zpl_document("^XA^FO160,240^FDTotal Weight (in kg)^FS^XZ"),
            image=signature_png_b64(),
            placement=stamping.StampPlacement(width=60.0, height=20.0, dpi=203),
            keyword="Total Weight (in kg)",
        )

        zpl = decode_zpl(stamped.base64)
        ((fo_x, fo_y, total, _, bpr, _),) = grf_fields(zpl)
        self.assertEqual((fo_x, fo_y), (160, 240))
        # 60 x 20 mm at 203 dpi is a 480 x 160-dot raster: 60 bytes/row.
        self.assertEqual((total, bpr), (9600, 60))
        self.assertIn("Total Weight (in kg)", zpl)

    def test_geometry_only_placement_offsets_add_to_the_located_origin(self):
        stamped = lib.stamp_document(
            keyword_zpl_document("^XA^FO160,240^FDTotal Weight (in kg)^FS^XZ"),
            image=signature_png_b64(),
            placement=stamping.StampPlacement(x=10.0, width=60.0, height=20.0),
            keyword="Total Weight (in kg)",
        )

        ((fo_x, fo_y, *_),) = grf_fields(decode_zpl(stamped.base64))
        self.assertEqual(fo_x, int(round(((160 * 25.4 / 203) + 10.0) / 25.4 * 203)))
        self.assertEqual(fo_y, int(round(((240 * 25.4 / 203) + 0.0) / 25.4 * 203)))

    def test_keyword_derived_negative_anchor_raises(self):
        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(
                keyword_zpl_document("^XA^FO-5,35^FDSender signature^FS^XZ"),
                image=signature_png_b64(),
                placement=stamping.StampPlacement(width=60.0, height=20.0),
                keyword=KEYWORD,
            )

        self.assertIn("non-negative", str(ctx.exception))

    def test_keyword_derived_operand_overflow_raises(self):
        # ^FO31600,35 with a 480-dot wide raster resolves the x extent to 32080.
        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(
                keyword_zpl_document("^XA^FO31600,35^FDSender signature^FS^XZ"),
                image=signature_png_b64(),
                placement=stamping.StampPlacement(width=60.0, height=20.0),
                keyword=KEYWORD,
            )

        self.assertIn("32080", str(ctx.exception))
        self.assertIn("operand range", str(ctx.exception))

    def test_keyword_with_no_placement_and_no_seed_raises_naming_the_source(self):
        with providers():
            with self.assertRaises(ValueError) as ctx:
                lib.stamp_document(
                    keyword_zpl_document(INLINE_KEYWORD_STREAM),
                    image=signature_png_b64(),
                    carrier="acme",
                    doc_type="unknown",
                    keyword=KEYWORD,
                )

        self.assertIn("acme/unknown/ZPL/*", str(ctx.exception))
        self.assertIn("keyword", str(ctx.exception).lower())

    def test_keyword_against_a_pdf_document_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(
                pdf_document(),
                image=signature_png_b64(),
                carrier="acme",
                doc_type="customs_declaration",
                keyword=KEYWORD,
            )

        self.assertIn("PDF", str(ctx.exception))
        self.assertIn("keyword", str(ctx.exception).lower())

    def test_keyword_miss_propagates_through_stamp_document(self):
        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(
                keyword_zpl_document(INLINE_KEYWORD_STREAM),
                image=signature_png_b64(),
                placement=stamping.StampPlacement(width=60.0, height=20.0),
                keyword="no such field text",
            )

        self.assertIn("no such field text", str(ctx.exception))


class TestKeywordSeeds(unittest.TestCase):
    def test_seeded_zpl_document_resolves_implicitly_by_keyword(self):
        # Neither placement nor keyword: the ZPL key resolves through the seed's
        # own keyword. The form's keyword field sits at ^FO20,35 and the seed
        # offset (-1.673, 33.529) mm resolves to ^FO7,303, with the rotated
        # 49.1 x 7.6 mm strip a 61 x 392-dot raster (8 bytes/row).
        with example_providers():
            stamped = lib.stamp_document(
                _example_form_document(),
                image=signature_png_b64(),
                carrier="acme",
                doc_type="customs_declaration",
            )

        zpl = decode_zpl(stamped.base64)
        ((fo_x, fo_y, total, _, bpr, _),) = grf_fields(zpl)
        self.assertEqual((fo_x, fo_y), (7, 303))
        self.assertEqual((bpr, total), (8, 3136))
        self.assertIn(KEYWORD, zpl)

    def test_consumer_keyword_outranks_the_seed_keyword(self):
        # The Total Weight field's ^FO385,488.33 origin differs from the seed
        # keyword's ^FO20,35, so the operands identify which keyword won.
        with example_providers():
            stamped = lib.stamp_document(
                _example_form_document(),
                image=signature_png_b64(),
                carrier="acme",
                doc_type="customs_declaration",
                keyword="Total Weight (in kg)",
            )

        ((fo_x, fo_y, *_),) = grf_fields(decode_zpl(stamped.base64))
        self.assertEqual(
            (fo_x, fo_y),
            (
                int(round(((385 * 25.4 / 203) - 1.673) / 25.4 * 203)),
                int(round(((488.3333333333333 * 25.4 / 203) + 33.529) / 25.4 * 203)),
            ),
        )
        self.assertNotEqual((fo_x, fo_y), (7, 303))

    def test_seed_keyword_geometry_offsets_derive_the_anchor(self):
        seed = stamping.StampSeed(
            keyword="Total Weight (in kg)",
            keyword_placement=stamping.StampPlacement(
                x=3.0, y=7.0, width=33.0, height=12.0, rotation=90, dpi=203
            ),
        )

        with providers(seeded_provider({"unknown/ZPL/*": seed})):
            stamped = lib.stamp_document(
                keyword_zpl_document("^XA^FO160,240^FDTotal Weight (in kg)^FS^XZ"),
                image=signature_png_b64(),
                carrier="acme",
                doc_type="unknown",
                keyword="Total Weight (in kg)",
            )

        ((fo_x, fo_y, *_),) = grf_fields(decode_zpl(stamped.base64))
        self.assertEqual(fo_x, int(round(((160 * 25.4 / 203) + 3.0) / 25.4 * 203)))
        self.assertEqual(fo_y, int(round(((240 * 25.4 / 203) + 7.0) / 25.4 * 203)))

    def test_zpl_keyword_less_seed_keeps_the_registry_miss_error(self):
        # A keyword-less seed has no ZPL anchor, so a ZPL document against it
        # raises the registry-miss error naming the composed key.
        seed = stamping.StampSeed(placement=zpl_placement())

        with providers(seeded_provider({"cn23/ZPL/*": seed})):
            with self.assertRaises(ValueError) as ctx:
                lib.stamp_document(
                    keyword_zpl_document(INLINE_KEYWORD_STREAM),
                    image=signature_png_b64(),
                    carrier="acme",
                    doc_type="cn23",
                )

        self.assertIn("acme/cn23/ZPL/*", str(ctx.exception))

    def test_supplied_placement_wins_with_a_keyword_seed_present(self):
        document = keyword_zpl_document(INLINE_KEYWORD_STREAM)

        with example_providers() as collect:
            seeded = lib.stamp_document(
                document,
                image=signature_png_b64(),
                placement=zpl_placement(),
                carrier="acme",
                doc_type="customs_declaration",
            )
        direct = lib.stamp_document(
            document, image=signature_png_b64(), placement=zpl_placement()
        )

        self.assertEqual(seeded.base64, direct.base64)
        collect.assert_not_called()

    def test_injected_registry_owns_keyword_geometry_resolution(self):
        # A supplied registry replaces the plugin seeds wherever they would be
        # consulted, so the example seed (which resolves this very key and
        # would land on-label at ^FO20,35) must not leak through.
        seen = []

        def empty_registry(key):
            seen.append(key)
            return None

        with example_providers():
            with self.assertRaises(ValueError) as ctx:
                lib.stamp_document(
                    keyword_zpl_document("^XA^FO20,35^FDSender signature^FS^XZ"),
                    image=signature_png_b64(),
                    carrier="acme",
                    doc_type="customs_declaration",
                    keyword=KEYWORD,
                    registry=empty_registry,
                )

        self.assertEqual(seen, ["acme/customs_declaration/ZPL/*"])
        self.assertIn("acme/customs_declaration/ZPL/*", str(ctx.exception))
        self.assertIn("keyword", str(ctx.exception).lower())

    def test_keyword_stamp_with_date_composites_one_strip(self):
        # Image AND date in one call composite one combined strip at the seed
        # origin, never two graphics, and its ink is neither blank nor solid.
        with example_providers():
            stamped = lib.stamp_document(
                _example_form_document(),
                image=real_signature_b64(),
                carrier="acme",
                doc_type="customs_declaration",
                keyword=KEYWORD,
                date="2026-09-24",
            )

        zpl = decode_zpl(stamped.base64)
        ((fo_x, fo_y, total, _, _, hexdata),) = grf_fields(zpl)
        self.assertEqual((fo_x, fo_y), (7, 303))
        self.assertEqual(zpl.count("^XZ"), 1)
        fraction = bin(int(hexdata, 16)).count("1") / (total * 8)
        self.assertGreater(fraction, 0.005)
        self.assertLess(fraction, 0.30)

    def test_seeds_resolve_on_a_blank_a4_page(self):
        with example_providers():
            stamped = lib.stamp_document(
                models.ShippingDocument(
                    category="customs_declaration", format="PDF", base64=blank_pdf_b64()
                ),
                image=signature_png_b64(),
                carrier="acme",
                doc_type="customs_declaration",
            )

        self.assertEqual(stamped.format, "PDF")


if __name__ == "__main__":
    unittest.main()
