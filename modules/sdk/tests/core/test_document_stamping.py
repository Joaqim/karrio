import io
import os
import base64
import unittest

import pypdf
import PIL.Image
import PIL.ImageDraw
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

import karrio.lib as lib
import karrio.core.models as models
import karrio.core.utils.helpers as helpers
import karrio.core.utils.stamping as stamping

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("utf-8")


def _cn22_pdf_b64() -> str:
    """A real 1-page PostNord customs-declaration PDF with a text layer."""
    with open(os.path.join(FIXTURES_DIR, "postnord_cn22.pdf"), "rb") as handle:
        return _b64(handle.read())


def _signature_png_b64() -> str:
    """A synthetic RGBA signature PNG on a transparent background."""
    image = PIL.Image.new("RGBA", (400, 140), (255, 255, 255, 0))
    draw = PIL.ImageDraw.Draw(image)
    draw.line((20, 70, 380, 70), fill=(0, 0, 0, 180), width=6)
    draw.ellipse((120, 30, 280, 110), outline=(0, 0, 0, 220), width=4)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return _b64(buffer.getvalue())


def _acroform_pdf_b64() -> str:
    """A synthetic 2-page PDF whose first page carries one fillable text field.

    The real carrier fixtures are flat (no AcroForm), so this minimal document
    exists solely to exercise the AcroForm-survival assertion.
    """
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    writer.add_blank_page(width=595, height=842)

    field = DictionaryObject()
    field.update(
        {
            NameObject("/FT"): NameObject("/Tx"),
            NameObject("/T"): TextStringObject("signature_field"),
            NameObject("/V"): TextStringObject(""),
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/Rect"): ArrayObject(
                [NumberObject(50), NumberObject(50), NumberObject(250), NumberObject(90)]
            ),
        }
    )
    reference = writer._add_object(field)
    page[NameObject("/Annots")] = ArrayObject([reference])
    field[NameObject("/P")] = page.indirect_reference

    acroform = DictionaryObject()
    acroform.update(
        {
            NameObject("/Fields"): ArrayObject([reference]),
            NameObject("/NeedAppearances"): BooleanObject(True),
        }
    )
    writer._root_object[NameObject("/AcroForm")] = writer._add_object(acroform)

    buffer = io.BytesIO()
    writer.write(buffer)
    return _b64(buffer.getvalue())


def _page_count(b64: str) -> int:
    return len(pypdf.PdfReader(io.BytesIO(base64.b64decode(b64))).pages)


def _fields(b64: str):
    return pypdf.PdfReader(io.BytesIO(base64.b64decode(b64))).get_fields() or {}


def _placement() -> stamping.StampPlacement:
    return stamping.StampPlacement(x=40.0, y=200.0, width=60.0, height=20.0)


class TestSniffDocumentFormat(unittest.TestCase):
    def test_detects_pdf(self):
        self.assertEqual(
            helpers.sniff_document_format(_b64(b"%PDF-1.4\n%rest")), "PDF"
        )

    def test_detects_zpl(self):
        self.assertEqual(
            helpers.sniff_document_format(_b64(b"^XA^FO50,50^XZ")), "ZPL"
        )

    def test_detects_png(self):
        self.assertEqual(
            helpers.sniff_document_format(_b64(b"\x89PNG\r\n\x1a\n\x00\x00")), "PNG"
        )

    def test_accepts_raw_bytes(self):
        self.assertEqual(helpers.sniff_document_format(b"%PDF-1.7"), "PDF")

    def test_tolerates_leading_whitespace(self):
        self.assertEqual(
            helpers.sniff_document_format(_b64(b"  \n^XA^XZ")), "ZPL"
        )

    def test_magic_bytes_win_over_content_type(self):
        self.assertEqual(
            helpers.sniff_document_format(
                _b64(b"%PDF-1.4"), content_type="application/zpl"
            ),
            "PDF",
        )

    def test_falls_back_to_content_type(self):
        self.assertEqual(
            helpers.sniff_document_format(
                _b64(b"not-a-known-magic"), content_type="image/png"
            ),
            "PNG",
        )

    def test_falls_back_to_default(self):
        self.assertEqual(
            helpers.sniff_document_format(_b64(b"unknown"), default="PDF"),
            "PDF",
        )

    def test_empty_content_returns_default(self):
        self.assertIsNone(helpers.sniff_document_format(""))
        self.assertEqual(helpers.sniff_document_format("", default="PDF"), "PDF")

    def test_short_bytes_do_not_misclassify(self):
        # A truncated PDF prefix must not match the full "%PDF-" signature.
        self.assertIsNone(helpers.sniff_document_format(_b64(b"%PD")))

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
        placement = stamping.StampPlacement(x=150.0, y=250.0, width=45.0, height=18.0)

        x, y, width, height = stamping.placement_to_pdf_rect(
            placement, page_height_pt
        )

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
        placement = stamping.StampPlacement(x=0.0, y=0.0, width=10.0, height=20.0)

        _, y, _, height = stamping.placement_to_pdf_rect(placement, page_height_pt)

        self.assertAlmostEqual(y, page_height_pt - height, places=6)


class TestStampPdfBackend(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_preserves_format_and_page_count(self):
        document = _cn22_pdf_b64()
        request = stamping.StampRequest(
            image=_signature_png_b64(), placement=_placement()
        )

        stamped = stamping.stamp_pdf(document, request)

        self.assertTrue(base64.b64decode(stamped).startswith(b"%PDF-"))
        self.assertEqual(_page_count(stamped), _page_count(document))

    def test_carrier_text_layer_is_not_rasterized(self):
        document = _cn22_pdf_b64()
        original = pypdf.PdfReader(
            io.BytesIO(base64.b64decode(document))
        ).pages[0].extract_text()
        request = stamping.StampRequest(
            image=_signature_png_b64(), placement=_placement()
        )

        stamped = stamping.stamp_pdf(document, request)
        after = pypdf.PdfReader(
            io.BytesIO(base64.b64decode(stamped))
        ).pages[0].extract_text()

        # The selectable carrier text survives the merge intact (the merge only
        # appends the overlay content stream, adding trailing whitespace).
        self.assertTrue(original.strip())
        self.assertEqual(after.strip(), original.strip())

    def test_acroform_fields_remain_fillable(self):
        document = _acroform_pdf_b64()
        request = stamping.StampRequest(
            image=_signature_png_b64(), placement=_placement()
        )

        stamped = stamping.stamp_pdf(document, request)

        self.assertIn("signature_field", _fields(stamped))
        self.assertEqual(_page_count(stamped), _page_count(document))

    def test_underlay_preserves_page_count(self):
        document = _cn22_pdf_b64()
        request = stamping.StampRequest(
            image=_signature_png_b64(),
            placement=_placement(),
            layer="underlay",
        )

        stamped = stamping.stamp_pdf(document, request)

        self.assertTrue(base64.b64decode(stamped).startswith(b"%PDF-"))
        self.assertEqual(_page_count(stamped), _page_count(document))


def _pdf_document() -> models.ShippingDocument:
    return models.ShippingDocument(
        category="customs_declaration", format="PDF", base64=_cn22_pdf_b64()
    )


def _acroform_document() -> models.ShippingDocument:
    return models.ShippingDocument(
        category="customs_declaration", format="PDF", base64=_acroform_pdf_b64()
    )


def _png_document() -> models.ShippingDocument:
    return models.ShippingDocument(
        category="customs_declaration", format="PNG", base64=_signature_png_b64()
    )


class TestStampDocument(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_pdf_preserves_format_page_and_acroform(self):
        document = _acroform_document()

        stamped = lib.stamp_document(
            document, image=_signature_png_b64(), placement=_placement()
        )

        self.assertEqual(stamped.format, "PDF")
        self.assertEqual(_page_count(stamped.base64), _page_count(document.base64))
        self.assertIn("signature_field", _fields(stamped.base64))

    def test_returns_new_document_leaving_input_untouched(self):
        document = _pdf_document()
        original_b64 = document.base64

        stamped = lib.stamp_document(
            document, image=_signature_png_b64(), placement=_placement()
        )

        self.assertNotEqual(stamped.base64, original_b64)
        self.assertEqual(document.base64, original_b64)
        self.assertEqual(stamped.category, document.category)

    def test_rejects_png_document(self):
        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(
                _png_document(), image=_signature_png_b64(), placement=_placement()
            )

        self.assertIn("PNG", str(ctx.exception))

    def test_rejects_format_without_backend(self):
        # ZPL is recognized by the sniffer but has no launch backend.
        document = models.ShippingDocument(
            category="customs_declaration", format="ZPL", base64=_b64(b"^XA^FO^XZ")
        )

        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(
                document, image=_signature_png_b64(), placement=_placement()
            )

        self.assertIn("ZPL", str(ctx.exception))

    def test_supplied_placement_skips_registry(self):
        def exploding_registry(key):
            raise AssertionError(
                f"registry consulted for {key!r} despite supplied placement"
            )

        stamped = lib.stamp_document(
            _pdf_document(),
            image=_signature_png_b64(),
            placement=_placement(),
            registry=exploding_registry,
        )

        self.assertEqual(stamped.format, "PDF")

    def test_registry_consulted_only_on_omission(self):
        seen = []

        def seed_registry(key):
            seen.append(key)
            return _placement()

        stamped = lib.stamp_document(
            _pdf_document(),
            image=_signature_png_b64(),
            carrier="postnord",
            doc_type="cn22",
            registry=seed_registry,
        )

        self.assertEqual(stamped.format, "PDF")
        self.assertEqual(seen, ["postnord/cn22/PDF"])

    def test_registry_miss_raises_naming_the_key(self):
        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(
                _pdf_document(),
                image=_signature_png_b64(),
                carrier="postnord",
                doc_type="cn22",
            )

        message = str(ctx.exception)
        self.assertIn("postnord/cn22/PDF", message)

    def test_default_registry_always_misses(self):
        with self.assertRaises(ValueError):
            lib.stamp_document(_pdf_document(), image=_signature_png_b64())


if __name__ == "__main__":
    unittest.main()
