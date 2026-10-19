"""Document stamping: keyword-anchored placement on PDF page text."""

import unittest

import karrio.lib as lib
import karrio.core.models as models
import karrio.core.utils.stamping as stamping

from .stamping_helpers import (
    TextRun,
    overlay_cms,
    page_count,
    providers,
    seeded_provider,
    signature_png_b64,
    text_runs_pdf_b64,
)

KEYWORD = "Date and Sender's signature"

UPRIGHT = (1.0, 0.0, 0.0, 1.0)
CLOCKWISE = (0.0, -1.0, 1.0, 0.0)
COUNTERCLOCKWISE = (0.0, 1.0, -1.0, 0.0)

# A 40 x 10 mm strip whose top-left sits 5 mm along the text and 2 mm below
# its baseline, measured in the keyword's own reading frame.
GEOMETRY = stamping.StampPlacement(x=5.0, y=2.0, width=40.0, height=10.0)

# Consumer geometry names only the extent: a consumer-supplied x or y would
# make the placement fully anchored, so measured offsets reach the keyword
# through the registry (a seed or an injected lookup).
EXTENT = stamping.StampPlacement(width=40.0, height=10.0)

# The same offsets in points: 2 / 5 / 10 / 12 mm.
MM2, MM5, MM10, MM12 = 5.66929, 14.17323, 28.34646, 34.01575


def _measured(key):
    return GEOMETRY


def _document(*pages) -> models.ShippingDocument:
    return models.ShippingDocument(
        category="label", format="PDF", base64=text_runs_pdf_b64(*pages)
    )


def _run(direction, x, y, text=KEYWORD, **form) -> TextRun:
    return TextRun(text, (*direction, x, y), **form)


def _stamp(document, **kwargs):
    return lib.stamp_document(document, image=signature_png_b64(), **kwargs)


class TestPdfKeywordPlacement(unittest.TestCase):
    def assertOrigin(self, cm, x, y):
        self.assertAlmostEqual(cm[4], x, places=2)
        self.assertAlmostEqual(cm[5], y, places=2)

    def test_upright_keyword_anchors_below_its_baseline(self):
        # Keyword baseline at (100, 500) pt: the upright strip's bottom-left
        # is 5 mm right of it and 2 + 10 mm below it.
        stamped = _stamp(
            _document([_run(UPRIGHT, 100, 500)]),
            keyword=KEYWORD,
            registry=_measured,
        )

        (cm,) = overlay_cms(stamped.base64)
        self.assertOrigin(cm, 100 + MM5, 500 - MM2 - MM10)
        self.assertGreater(cm[0], 0)
        self.assertGreater(cm[3], 0)
        self.assertAlmostEqual(cm[1], 0, places=6)
        self.assertAlmostEqual(cm[2], 0, places=6)

    def test_clockwise_keyword_turns_the_strip_along_the_text(self):
        # Text reading downward from (300, 600) pt: "along" is page-down and
        # "below" is page-left, so the strip spans x 300-12..300-2 mm and
        # hangs from 5 mm below the origin; a clockwise image's overlay origin
        # is its extent's top-left corner.
        stamped = _stamp(
            _document([_run(CLOCKWISE, 300, 600)]),
            keyword=KEYWORD,
            registry=_measured,
        )

        (cm,) = overlay_cms(stamped.base64)
        self.assertOrigin(cm, 300 - MM12, 600 - MM5)
        self.assertAlmostEqual(cm[0], 0, places=6)
        self.assertAlmostEqual(cm[3], 0, places=6)
        self.assertLess(cm[1], 0)
        self.assertGreater(cm[2], 0)

    def test_counterclockwise_keyword_turns_the_strip_along_the_text(self):
        # Text reading upward from (300, 200) pt: "along" is page-up and
        # "below" is page-right; a counter-clockwise image's overlay origin is
        # its extent's bottom-right corner.
        stamped = _stamp(
            _document([_run(COUNTERCLOCKWISE, 300, 200)]),
            keyword=KEYWORD,
            registry=_measured,
        )

        (cm,) = overlay_cms(stamped.base64)
        self.assertOrigin(cm, 300 + MM12, 200 + MM5)
        self.assertGreater(cm[1], 0)
        self.assertLess(cm[2], 0)

    def test_keyword_inside_a_placed_form_resolves_in_page_space(self):
        # The run sits at (8.867, 525.99) in a form whose /Matrix shifts it by
        # (10, 20) and which is drawn under a (148.84964, 151.74292) cm, so its
        # page-space origin is (167.71664, 697.73292) pt.
        stamped = _stamp(
            _document(
                [
                    _run(
                        CLOCKWISE,
                        8.867,
                        525.99,
                        form_cm=(1, 0, 0, 1, 148.84964, 151.74292),
                        form_matrix=(1, 0, 0, 1, 10, 20),
                    )
                ]
            ),
            keyword=KEYWORD,
            registry=_measured,
        )

        # The page's own content stream draws the form, so its placement cm
        # leads; the stamp overlay follows it.
        (form_cm, cm) = overlay_cms(stamped.base64)
        self.assertOrigin(form_cm, 148.84964, 151.74292)
        self.assertOrigin(cm, 167.71664 - MM12, 697.73292 - MM5)

    def test_consumer_extent_anchors_at_the_keyword_origin(self):
        stamped = _stamp(
            _document([_run(UPRIGHT, 100, 500)]), keyword=KEYWORD, placement=EXTENT
        )

        (cm,) = overlay_cms(stamped.base64)
        self.assertOrigin(cm, 100, 500 - MM10)

    def test_consumer_extent_follows_a_clockwise_keyword(self):
        stamped = _stamp(
            _document([_run(CLOCKWISE, 300, 600)]), keyword=KEYWORD, placement=EXTENT
        )

        (cm,) = overlay_cms(stamped.base64)
        self.assertOrigin(cm, 300 - MM10, 600)
        self.assertLess(cm[1], 0)

    def test_keyword_within_a_longer_run_anchors_at_the_run_origin(self):
        stamped = _stamp(
            _document([_run(UPRIGHT, 100, 500, text=f"12 {KEYWORD} here")]),
            keyword=KEYWORD,
            registry=_measured,
        )

        (cm,) = overlay_cms(stamped.base64)
        self.assertOrigin(cm, 100 + MM5, 500 - MM2 - MM10)

    def test_resolved_placement_meets_bounds_validation(self):
        with self.assertRaises(ValueError) as ctx:
            _stamp(
                _document([_run(UPRIGHT, 10, 500)]),
                keyword=KEYWORD,
                registry=lambda key: stamping.StampPlacement(
                    x=-10.0, y=2.0, width=40.0, height=10.0
                ),
            )

        self.assertIn("non-negative", str(ctx.exception))

    def test_non_orthogonal_text_direction_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _stamp(
                _document([_run((0.70711, 0.70711, -0.70711, 0.70711), 200, 400)]),
                keyword=KEYWORD,
                registry=_measured,
            )

        self.assertIn(KEYWORD, str(ctx.exception))
        self.assertIn("90", str(ctx.exception))


class TestPdfKeywordPages(unittest.TestCase):
    def _two_page(self):
        return _document(
            [_run(UPRIGHT, 100, 500)],
            [_run(UPRIGHT, 200, 300)],
        )

    def test_first_page_containing_the_keyword_is_stamped(self):
        stamped = _stamp(
            _document(
                [_run(UPRIGHT, 100, 500, text="Tracked letter")],
                [_run(UPRIGHT, 200, 300)],
            ),
            keyword=KEYWORD,
            registry=_measured,
        )

        self.assertEqual(overlay_cms(stamped.base64, page_index=0), [])
        (cm,) = overlay_cms(stamped.base64, page_index=1)
        self.assertAlmostEqual(cm[4], 200 + MM5, places=2)
        self.assertEqual(page_count(stamped.base64), 2)

    def test_page_override_locates_the_keyword_on_the_named_page(self):
        stamped = _stamp(
            self._two_page(), keyword=KEYWORD, registry=_measured, page=2
        )

        self.assertEqual(overlay_cms(stamped.base64, page_index=0), [])
        (cm,) = overlay_cms(stamped.base64, page_index=1)
        self.assertAlmostEqual(cm[4], 200 + MM5, places=2)
        self.assertAlmostEqual(cm[5], 300 - MM2 - MM10, places=2)

    def test_omitted_page_takes_the_first_match(self):
        stamped = _stamp(self._two_page(), keyword=KEYWORD, registry=_measured)

        (cm,) = overlay_cms(stamped.base64, page_index=0)
        self.assertAlmostEqual(cm[4], 100 + MM5, places=2)
        self.assertEqual(overlay_cms(stamped.base64, page_index=1), [])

    def test_out_of_range_page_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _stamp(self._two_page(), keyword=KEYWORD, registry=_measured, page=3)

        self.assertIn("between 1 and the document's 2 page(s)", str(ctx.exception))

    def test_keyword_absent_from_the_page_text_raises_naming_it(self):
        with self.assertRaises(ValueError) as ctx:
            _stamp(
                _document([_run(UPRIGHT, 100, 500, text="Tracked letter")]),
                keyword=KEYWORD,
                registry=_measured,
            )

        self.assertIn(KEYWORD, str(ctx.exception))

    def test_keyword_absent_from_the_named_page_raises_naming_it(self):
        with self.assertRaises(ValueError) as ctx:
            _stamp(
                _document([_run(UPRIGHT, 100, 500)], [_run(UPRIGHT, 1, 1, "Other")]),
                keyword=KEYWORD,
                registry=_measured,
                page=2,
            )

        self.assertIn(KEYWORD, str(ctx.exception))

    def test_pages_without_text_raise_the_no_text_error(self):
        for pages, page in ((([],), None), (([], [_run(UPRIGHT, 100, 500)]), 1)):
            with self.subTest(page=page):
                with self.assertRaises(ValueError) as ctx:
                    _stamp(
                        _document(*pages),
                        keyword=KEYWORD,
                        registry=_measured,
                        page=page,
                    )

                self.assertIn("without page text", str(ctx.exception))


SEEDED_GEOMETRY = stamping.StampSeed(
    revision=1, keyword=KEYWORD, pdf_keyword_placement=GEOMETRY
)


class TestPdfKeywordSeeds(unittest.TestCase):
    def _seeded(self, seed=SEEDED_GEOMETRY):
        return providers(seeded_provider({"label_cn22/PDF/A4": seed}))

    def test_seed_pdf_keyword_geometry_resolves_implicitly(self):
        with self._seeded():
            stamped = _stamp(
                _document([_run(CLOCKWISE, 300, 600)]),
                carrier="acme",
                doc_type="label_cn22",
            )

        (cm,) = overlay_cms(stamped.base64)
        self.assertAlmostEqual(cm[4], 300 - MM12, places=2)
        self.assertAlmostEqual(cm[5], 600 - MM5, places=2)

    def test_seed_keyword_is_located_on_the_classified_page(self):
        with self._seeded():
            stamped = _stamp(
                _document([_run(UPRIGHT, 100, 500)], [_run(CLOCKWISE, 300, 600)]),
                carrier="acme",
                doc_type="label_cn22",
                page=2,
            )

        self.assertEqual(overlay_cms(stamped.base64, page_index=0), [])
        (cm,) = overlay_cms(stamped.base64, page_index=1)
        self.assertAlmostEqual(cm[4], 300 - MM12, places=2)

    def test_consumer_keyword_takes_the_seed_pdf_geometry(self):
        with self._seeded():
            stamped = _stamp(
                _document(
                    [_run(UPRIGHT, 100, 500), _run(UPRIGHT, 200, 300, "Signature")]
                ),
                carrier="acme",
                doc_type="label_cn22",
                keyword="Signature",
            )

        (cm,) = overlay_cms(stamped.base64)
        self.assertAlmostEqual(cm[4], 200 + MM5, places=2)
        self.assertAlmostEqual(cm[5], 300 - MM2 - MM10, places=2)

    def test_consumer_keyword_without_pdf_geometry_raises_naming_the_key(self):
        zpl_only = stamping.StampSeed(
            keyword=KEYWORD,
            keyword_placement=stamping.StampPlacement(width=40.0, height=10.0),
        )
        with self._seeded(zpl_only):
            with self.assertRaises(ValueError) as ctx:
                _stamp(
                    _document([_run(UPRIGHT, 100, 500)]),
                    carrier="acme",
                    doc_type="label_cn22",
                    keyword=KEYWORD,
                )

        self.assertIn("acme/label_cn22/PDF/A4", str(ctx.exception))

    def test_coordinate_seed_never_consults_its_keyword(self):
        # The seed carries a keyword and ZPL geometry but only a coordinate
        # PDF placement: (40, 200) mm, a bottom-left of (113.386, 218.378) pt,
        # regardless of where the keyword sits on the page.
        seed = stamping.StampSeed(
            placement=stamping.StampPlacement(x=40.0, y=200.0, width=60.0, height=20.0),
            keyword=KEYWORD,
            keyword_placement=stamping.StampPlacement(width=40.0, height=10.0),
        )
        with self._seeded(seed):
            stamped = _stamp(
                _document([_run(UPRIGHT, 400, 700)]),
                carrier="acme",
                doc_type="label_cn22",
            )

        (cm,) = overlay_cms(stamped.base64)
        self.assertAlmostEqual(cm[4], 113.386, places=2)
        self.assertAlmostEqual(cm[5], 218.378, places=2)

    def test_injected_registry_supplies_pdf_keyword_geometry(self):
        seen = []

        def registry(key):
            seen.append(key)
            return GEOMETRY

        stamped = _stamp(
            _document([_run(UPRIGHT, 100, 500)]),
            carrier="acme",
            doc_type="label_cn22",
            keyword=KEYWORD,
            registry=registry,
        )

        self.assertEqual(seen, ["acme/label_cn22/PDF/A4"])
        (cm,) = overlay_cms(stamped.base64)
        self.assertAlmostEqual(cm[4], 100 + MM5, places=2)


if __name__ == "__main__":
    unittest.main()
