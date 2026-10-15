"""Document stamping: format sniffing, placement conversion and the PDF backend."""

import base64
import unittest

import PIL.Image

import karrio.lib as lib
import karrio.core.models as models
import karrio.core.utils.helpers as helpers
import karrio.core.utils.stamping as stamping

from .stamping_helpers import (
    FORM_TEXT,
    SIGNATURE_FIXTURE,
    acroform_document,
    acroform_pdf_b64,
    b64,
    blank_pdf_b64,
    form_fields,
    form_pdf_b64,
    ordered_content_streams,
    overlay_cms,
    page_count,
    page_text,
    pdf_document,
    placement,
    png_document,
    real_signature_b64,
    sentinel_pdf_b64,
    signature_png_b64,
)


class TestSniffDocumentFormat(unittest.TestCase):
    def test_detects_pdf(self):
        self.assertEqual(helpers.sniff_document_format(b64(b"%PDF-1.4\n%rest")), "PDF")

    def test_detects_zpl(self):
        self.assertEqual(helpers.sniff_document_format(b64(b"^XA^FO50,50^XZ")), "ZPL")

    def test_detects_png(self):
        self.assertEqual(
            helpers.sniff_document_format(b64(b"\x89PNG\r\n\x1a\n\x00\x00")), "PNG"
        )

    def test_accepts_raw_bytes(self):
        self.assertEqual(helpers.sniff_document_format(b"%PDF-1.7"), "PDF")

    def test_tolerates_leading_whitespace(self):
        self.assertEqual(helpers.sniff_document_format(b64(b"  \n^XA^XZ")), "ZPL")

    def test_magic_bytes_win_over_content_type(self):
        self.assertEqual(
            helpers.sniff_document_format(
                b64(b"%PDF-1.4"), content_type="application/zpl"
            ),
            "PDF",
        )

    def test_falls_back_to_content_type(self):
        self.assertEqual(
            helpers.sniff_document_format(
                b64(b"not-a-known-magic"), content_type="image/png"
            ),
            "PNG",
        )

    def test_falls_back_to_default(self):
        self.assertEqual(
            helpers.sniff_document_format(b64(b"unknown"), default="PDF"),
            "PDF",
        )

    def test_empty_content_returns_default(self):
        self.assertIsNone(helpers.sniff_document_format(""))
        self.assertEqual(helpers.sniff_document_format("", default="PDF"), "PDF")

    def test_short_bytes_do_not_misclassify(self):
        # A truncated PDF prefix must not match the full "%PDF-" signature.
        self.assertIsNone(helpers.sniff_document_format(b64(b"%PD")))

    def test_invalid_base64_returns_default(self):
        self.assertIsNone(helpers.sniff_document_format("!!!not base64!!!"))


class TestStampPlacementConversion(unittest.TestCase):
    def test_mm_to_points_known_inch(self):
        # 25.4 mm is exactly one inch, which is exactly 72 points.
        self.assertAlmostEqual(stamping.mm_to_points(25.4), 72.0, places=9)

    def test_mm_to_points_zero(self):
        self.assertEqual(stamping.mm_to_points(0.0), 0.0)

    def test_placement_to_pdf_rect_flips_origin(self):
        # A4 page height in points; a rectangle 250 mm down from the top-left.
        page_height_pt = 841.8898
        rect = stamping.StampPlacement(x=150.0, y=250.0, width=45.0, height=18.0)

        x, y, width, height = stamping.placement_to_pdf_rect(rect, page_height_pt)

        self.assertAlmostEqual(x, 150.0 * 72.0 / 25.4, places=6)
        self.assertAlmostEqual(width, 45.0 * 72.0 / 25.4, places=6)
        self.assertAlmostEqual(height, 18.0 * 72.0 / 25.4, places=6)
        # Bottom edge = page height - top offset - rect height (bottom-left origin).
        self.assertAlmostEqual(
            y,
            page_height_pt - (250.0 * 72.0 / 25.4) - (18.0 * 72.0 / 25.4),
            places=6,
        )

    def test_placement_at_top_left_sits_below_top_edge(self):
        # A rectangle anchored at the very top-left (y=0) has its bottom edge one
        # rect-height below the page's top edge in bottom-left PDF coordinates.
        page_height_pt = 1000.0
        rect = stamping.StampPlacement(x=0.0, y=0.0, width=10.0, height=20.0)

        _, y, _, height = stamping.placement_to_pdf_rect(rect, page_height_pt)

        self.assertAlmostEqual(y, page_height_pt - height, places=6)


class TestStampPdfBackend(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_preserves_format_and_page_count(self):
        document = form_pdf_b64()
        request = stamping.StampRequest(
            image=signature_png_b64(), placement=placement()
        )

        stamped = stamping.stamp_pdf(document, request)

        self.assertTrue(base64.b64decode(stamped).startswith(b"%PDF-"))
        self.assertEqual(page_count(stamped), page_count(document))

    def test_form_text_layer_is_not_rasterized(self):
        document = form_pdf_b64()
        request = stamping.StampRequest(
            image=signature_png_b64(), placement=placement()
        )

        stamped = stamping.stamp_pdf(document, request)

        # The selectable form text survives the merge intact (the merge only
        # appends the overlay content stream, adding trailing whitespace).
        self.assertIn(FORM_TEXT, page_text(document))
        self.assertEqual(page_text(stamped).strip(), page_text(document).strip())

    def test_acroform_fields_remain_fillable(self):
        document = acroform_pdf_b64()
        request = stamping.StampRequest(
            image=signature_png_b64(), placement=placement()
        )

        stamped = stamping.stamp_pdf(document, request)

        self.assertIn("signature_field", form_fields(stamped))
        self.assertEqual(page_count(stamped), page_count(document))

    def test_underlay_preserves_page_count(self):
        document = form_pdf_b64()
        request = stamping.StampRequest(
            image=signature_png_b64(), placement=placement(), layer="underlay"
        )

        stamped = stamping.stamp_pdf(document, request)

        self.assertTrue(base64.b64decode(stamped).startswith(b"%PDF-"))
        self.assertEqual(page_count(stamped), page_count(document))

    def test_layer_determines_image_z_order(self):
        # The stamp image must be composited ABOVE carrier content for overlay
        # and BENEATH it for underlay. The oracle reads the output page's
        # /Contents array order (= paint order), never the production
        # `over=(layer != "underlay")` expression.
        document = sentinel_pdf_b64()

        def carrier_and_image_indices(layer):
            request = stamping.StampRequest(
                image=signature_png_b64(), placement=placement(), layer=layer
            )
            streams = ordered_content_streams(stamping.stamp_pdf(document, request))
            carrier = [i for i, s in enumerate(streams) if b"654.321" in s]
            image = [i for i, s in enumerate(streams) if b"Do" in s]
            # Exactly one carrier stream and one distinct stamp-image stream.
            self.assertEqual(len(carrier), 1)
            self.assertEqual(len(image), 1)
            self.assertNotEqual(carrier[0], image[0])
            return carrier[0], image[0]

        carrier_over, image_over = carrier_and_image_indices("overlay")
        carrier_under, image_under = carrier_and_image_indices("underlay")

        self.assertGreater(image_over, carrier_over)
        self.assertLess(image_under, carrier_under)

    def test_underlay_acroform_fields_remain_fillable(self):
        document = acroform_pdf_b64()
        request = stamping.StampRequest(
            image=signature_png_b64(), placement=placement(), layer="underlay"
        )

        stamped = stamping.stamp_pdf(document, request)

        self.assertIn("signature_field", form_fields(stamped))
        self.assertEqual(page_count(stamped), page_count(document))

    def test_placement_page_selects_the_stamped_page(self):
        # One-based page 2 of a 2-page document: the overlay lands on the
        # second page and the first page draws no image.
        request = stamping.StampRequest(
            image=signature_png_b64(),
            placement=stamping.StampPlacement(
                page=2, x=40.0, y=200.0, width=60.0, height=20.0
            ),
        )

        stamped = stamping.stamp_pdf(blank_pdf_b64(pages=2), request)

        self.assertEqual(overlay_cms(stamped, page_index=0), [])
        self.assertEqual(len(overlay_cms(stamped, page_index=1)), 1)


class TestPdfInputErrors(unittest.TestCase):
    """Client-input faults raise ``ValueError`` naming the fault."""

    def _stamp(self, document=None, image=None, **fields):
        rect = dict(x=40.0, y=200.0, width=60.0, height=20.0, **fields)
        return stamping.stamp_pdf(
            document or blank_pdf_b64(pages=2),
            stamping.StampRequest(
                image=image, placement=stamping.StampPlacement(**rect)
            ),
        )

    def test_missing_image_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self._stamp(image=None)

        self.assertIn("image", str(ctx.exception))

    def test_undecodable_image_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self._stamp(image=b64(b"notapng"))

        self.assertIn("image", str(ctx.exception))

    def test_unparseable_pdf_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self._stamp(
                document=b64(b"%PDF-1.4 truncated garbage"), image=signature_png_b64()
            )

        self.assertIn("PDF", str(ctx.exception))

    def test_page_beyond_the_document_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self._stamp(image=signature_png_b64(), page=3)

        self.assertIn("StampPlacement.page", str(ctx.exception))
        self.assertIn("2 page", str(ctx.exception))

    def test_negative_page_is_rejected(self):
        # A negative page would otherwise index from the document's end.
        with self.assertRaises(ValueError) as ctx:
            self._stamp(image=signature_png_b64(), page=-1)

        self.assertIn("StampPlacement.page", str(ctx.exception))

    def test_page_zero_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self._stamp(image=signature_png_b64(), page=0)

        self.assertIn("StampPlacement.page", str(ctx.exception))

    def test_negative_anchor_is_rejected_naming_the_field(self):
        with self.assertRaises(ValueError) as ctx:
            stamping.stamp_pdf(
                form_pdf_b64(),
                stamping.StampRequest(
                    image=signature_png_b64(),
                    placement=stamping.StampPlacement(
                        x=40.0, y=-2.0, width=60.0, height=20.0
                    ),
                ),
            )

        self.assertIn("StampPlacement.y", str(ctx.exception))

    def test_non_positive_extent_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            stamping.stamp_pdf(
                form_pdf_b64(),
                stamping.StampRequest(
                    image=signature_png_b64(),
                    placement=stamping.StampPlacement(
                        x=40.0, y=20.0, width=0.0, height=20.0
                    ),
                ),
            )

        self.assertIn("StampPlacement.width", str(ctx.exception))


class TestStampDocumentPdf(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_pdf_preserves_format_page_and_acroform(self):
        document = acroform_document()

        stamped = lib.stamp_document(
            document, image=signature_png_b64(), placement=placement()
        )

        self.assertEqual(stamped.format, "PDF")
        self.assertEqual(page_count(stamped.base64), page_count(document.base64))
        self.assertIn("signature_field", form_fields(stamped.base64))

    def test_returns_new_document_leaving_input_untouched(self):
        document = pdf_document()
        original_b64 = document.base64

        stamped = lib.stamp_document(
            document, image=signature_png_b64(), placement=placement()
        )

        self.assertNotEqual(stamped.base64, original_b64)
        self.assertEqual(document.base64, original_b64)
        self.assertEqual(stamped.category, document.category)

    def test_rejects_png_document(self):
        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(
                png_document(), image=signature_png_b64(), placement=placement()
            )

        self.assertIn("PNG", str(ctx.exception))

    def test_rejects_a_document_with_no_backend(self):
        document = models.ShippingDocument(
            category="other",
            format=None,
            base64=b64(b"plain text, neither PDF nor ZPL"),
        )

        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(
                document, image=signature_png_b64(), placement=placement()
            )

        self.assertIn("backend", str(ctx.exception))

    def test_omitted_placement_raises(self):
        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(pdf_document(), image=signature_png_b64())

        self.assertIn("placement", str(ctx.exception))


class TestRealSignaturePdf(unittest.TestCase):
    def test_signature_fixture_is_a_transparent_rgba_png(self):
        image = PIL.Image.open(SIGNATURE_FIXTURE)

        self.assertEqual(image.size, (450, 180))
        self.assertEqual(image.mode, "RGBA")
        alpha = image.getchannel("A").histogram()
        # A transparent ground plus substantive opaque ink: the flatten path
        # must composite anti-aliased alpha, not an opaque rectangle.
        self.assertGreater(alpha[0], 0)
        self.assertGreater(sum(alpha[128:]), 0)

    def test_real_signature_preserves_the_text_layer(self):
        document = form_pdf_b64(with_image=True)
        request = stamping.StampRequest(
            image=real_signature_b64(),
            placement=stamping.StampPlacement(
                x=100.0, y=100.0, width=40.0, height=20.0
            ),
        )

        stamped = stamping.stamp_pdf(document, request)

        self.assertEqual(page_count(stamped), 1)
        self.assertEqual(page_text(stamped).strip(), page_text(document).strip())


if __name__ == "__main__":
    unittest.main()
