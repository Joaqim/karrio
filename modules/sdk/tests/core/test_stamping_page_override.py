"""Document stamping: applying a registry-resolved placement on a named page."""

import unittest

import karrio.lib as lib
import karrio.core.models as models
import karrio.core.utils.stamping as stamping

from .stamping_helpers import (
    EXAMPLE_SEED,
    INLINE_KEYWORD_STREAM,
    KEYWORD,
    keyword_zpl_document,
    overlay_cms,
    page_count,
    page_text,
    placement,
    providers,
    seeded_provider,
    signature_png_b64,
    text_pdf_b64,
    zpl_placement,
)

# The seed places an upright 60 x 20 mm rectangle at (40, 200) mm on page 1,
# which on the 842 pt tall A4 page is a bottom-left corner at
# (113.386, 218.378) pt.
_SEED_PLACEMENT = stamping.StampPlacement(
    page=1, x=40.0, y=200.0, width=60.0, height=20.0
)
_SEED_ORIGIN_PT = (113.386, 218.378)


def _two_page_document() -> models.ShippingDocument:
    return models.ShippingDocument(
        category="label",
        format="PDF",
        base64=text_pdf_b64(["Letter label"], ["CUSTOMS DECLARATION CN22"]),
    )


def _seeded():
    return providers(
        seeded_provider(
            {"label_cn22/PDF/A4": stamping.StampSeed(placement=_SEED_PLACEMENT)}
        )
    )


class TestSeededPageOverride(unittest.TestCase):
    def _stamp(self, **kwargs):
        with _seeded():
            return lib.stamp_document(
                _two_page_document(),
                image=signature_png_b64(),
                carrier="acme",
                doc_type="label_cn22",
                **kwargs,
            )

    def test_override_applies_the_seed_on_the_named_page(self):
        stamped = self._stamp(page=2)

        self.assertEqual(overlay_cms(stamped.base64, page_index=0), [])
        (cm,) = overlay_cms(stamped.base64, page_index=1)
        self.assertAlmostEqual(cm[4], _SEED_ORIGIN_PT[0], places=2)
        self.assertAlmostEqual(cm[5], _SEED_ORIGIN_PT[1], places=2)
        self.assertEqual(page_count(stamped.base64), 2)
        self.assertIn("CUSTOMS DECLARATION CN22", page_text(stamped.base64, 1))

    def test_omitted_override_keeps_the_seed_page(self):
        stamped = self._stamp()

        (cm,) = overlay_cms(stamped.base64, page_index=0)
        self.assertAlmostEqual(cm[4], _SEED_ORIGIN_PT[0], places=2)
        self.assertAlmostEqual(cm[5], _SEED_ORIGIN_PT[1], places=2)
        self.assertEqual(overlay_cms(stamped.base64, page_index=1), [])

    def test_none_override_keeps_the_seed_page(self):
        stamped = self._stamp(page=None)

        self.assertEqual(len(overlay_cms(stamped.base64, page_index=0)), 1)
        self.assertEqual(overlay_cms(stamped.base64, page_index=1), [])

    def test_out_of_range_override_raises(self):
        for page in (3, 0, -1):
            with self.subTest(page=page):
                with self.assertRaises(ValueError) as ctx:
                    self._stamp(page=page)

                self.assertIn(
                    "between 1 and the document's 2 page(s)", str(ctx.exception)
                )
                self.assertIn(f"(got {page})", str(ctx.exception))

    def test_override_applies_to_an_injected_registry_placement(self):
        stamped = lib.stamp_document(
            _two_page_document(),
            image=signature_png_b64(),
            carrier="acme",
            doc_type="label_cn22",
            registry=lambda key: _SEED_PLACEMENT,
            page=2,
        )

        self.assertEqual(overlay_cms(stamped.base64, page_index=0), [])
        self.assertEqual(len(overlay_cms(stamped.base64, page_index=1)), 1)


class TestPageOverrideRejections(unittest.TestCase):
    def test_override_with_a_fully_anchored_placement_raises(self):
        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(
                _two_page_document(),
                image=signature_png_b64(),
                placement=placement(),
                page=2,
            )

        self.assertIn("fully anchored placement", str(ctx.exception))

    def test_override_against_zpl_raises(self):
        geometry = stamping.StampPlacement(width=60.0, height=20.0)
        with providers(seeded_provider({"customs_declaration/ZPL/*": EXAMPLE_SEED})):
            for kwargs in (
                dict(carrier="acme", doc_type="customs_declaration"),
                dict(keyword=KEYWORD, placement=geometry),
                dict(placement=zpl_placement()),
            ):
                with self.subTest(kwargs=sorted(kwargs)):
                    with self.assertRaises(ValueError) as ctx:
                        lib.stamp_document(
                            keyword_zpl_document(INLINE_KEYWORD_STREAM),
                            image=signature_png_b64(),
                            page=1,
                            **kwargs,
                        )

                    self.assertIn("'ZPL'", str(ctx.exception))
                    self.assertIn("page", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
