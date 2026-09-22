import io
import os
import math
import base64
import unittest

import pypdf
import PIL.Image
import PIL.ImageDraw
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    ContentStream,
    DecodedStreamObject,
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
                [
                    NumberObject(50),
                    NumberObject(50),
                    NumberObject(250),
                    NumberObject(90),
                ]
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


def _zpl_doc_b64(stream: str = "^XA^FO10,10^GB100,100,2^FS^XZ") -> str:
    return _b64(stream.encode("utf-8"))


def _decode_zpl(b64: str) -> str:
    return base64.b64decode(b64).decode("utf-8")


def _zpl_placement(rotation: float = 0, dpi: int = 203) -> stamping.StampPlacement:
    # 203 dpi: 20/30/60 mm resolve to 160/240/480/160 dots (see the rotation
    # oracle in TestZplRotation), so the anchor arithmetic lands on integers.
    return stamping.StampPlacement(
        x=20.0, y=30.0, width=60.0, height=20.0, rotation=rotation, dpi=dpi
    )


def _grf_fields(zpl: str):
    """Return each inline ``^FO..^GFA..^FS`` field as a parsed tuple.

    The tuple is ``(fo_x, fo_y, total, total2, bytes_per_row, hexdata)`` with the
    four numeric header fields as ints and the hex payload verbatim, so a test
    can assert the exact origin, byte counts, and bytes-per-row independently of
    the production encoder.
    """
    import re

    return [
        (int(x), int(y), int(t1), int(t2), int(bpr), hexdata)
        for x, y, t1, t2, bpr, hexdata in re.findall(
            r"\^FO(\d+),(\d+)\^GFA,(\d+),(\d+),(\d+),([0-9A-F]*)\^FS", zpl
        )
    ]


def _solid_black_png_b64(width: int = 400, height: int = 140) -> str:
    """An opaque solid-black PNG: flattens to pure black at any density."""
    image = PIL.Image.new("RGBA", (width, height), (0, 0, 0, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return _b64(buffer.getvalue())


def _sentinel_pdf_b64() -> str:
    """A 1-page PDF whose sole content stream paints a uniquely-located mark.

    The carrier content is a 1x1 rectangle at the distinctive coordinate
    654.321 -- a token no generated stamp-image stream contains -- and the page
    carries no XObject, so the stamp's image-draw (`Do`) content is
    unambiguously the other stream. This lets the z-order test identify
    carrier-vs-stamp content by intrinsic markers rather than by array position.
    """
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    content = DecodedStreamObject()
    content.set_data(b"q 123.456 654.321 1 1 re f Q")
    page[NameObject("/Contents")] = writer._add_object(content)

    buffer = io.BytesIO()
    writer.write(buffer)
    return _b64(buffer.getvalue())


def _ordered_content_streams(b64: str, page_index: int = 0):
    """Return page 1's content streams as bytes in ``/Contents`` array order.

    Per the PDF spec, when ``/Contents`` is an array of streams they are
    concatenated in array order to form the page content, so a lower array
    index is painted first and therefore drawn *beneath* higher indices.
    Observing this order in the written-out PDF is an oracle independent of the
    production ``over=(layer != "underlay")`` expression: it reports where the
    stamp image actually landed in the composited page, not how the caller asked
    for it, so flipping that expression flips the observed order.
    """
    page = pypdf.PdfReader(io.BytesIO(base64.b64decode(b64))).pages[page_index]
    contents = page["/Contents"].get_object()
    if isinstance(contents, ArrayObject):
        return [element.get_object().get_data() for element in contents]
    return [contents.get_data()]


def _overlay_cms(b64: str, page_index: int = 0):
    """Return each overlay stream's leading ``cm`` matrix, in paint order.

    An overlay stream is a page content stream carrying an image draw (``Do``).
    ``merge_transformed_page`` prepends the placement transformation as the
    stream's first ``cm`` operator, so the leading ``cm`` of each overlay stream
    is where that image actually landed on the page -- an oracle independent of
    the production transformation expression, reporting the composited result
    rather than how the caller asked for it. The Pillow image XObject carries a
    later ``cm`` of its own; only the first one is the placement matrix.
    """
    page = pypdf.PdfReader(io.BytesIO(base64.b64decode(b64))).pages[page_index]
    contents = page["/Contents"].get_object()
    streams = contents if isinstance(contents, ArrayObject) else [contents]
    matrices = []
    for element in streams:
        obj = element.get_object()
        if b"Do" not in obj.get_data():
            continue
        stream = ContentStream(obj, page.pdf)
        leading_cm = next(ops for ops in stream.operations if ops[1] == b"cm")
        matrices.append(tuple(float(value) for value in leading_cm[0]))
    return matrices


def _cms_in_y_band(b64, y_lo, y_hi, page_index: int = 0):
    """Return every content-stream ``cm`` whose translation-y lands in a band.

    Where ``_overlay_cms`` takes the leading ``cm`` of each image-drawing
    stream, this scans all ``cm`` operators across all streams and selects them
    by where they land. A real carrier page that already draws its own images
    forces the first stamp overlay to be concatenated into the carrier's own
    content stream, so its leading ``cm`` is the carrier transform, not the
    stamp's -- a first-cm-per-stream read then misses that overlay entirely.
    Selecting by a measured anchor band (an independent literal derived from the
    seed's strip, not from the production transform) isolates exactly the stamp
    overlays, since the carrier's own transforms fall outside the band.
    """
    page = pypdf.PdfReader(io.BytesIO(base64.b64decode(b64))).pages[page_index]
    contents = page["/Contents"].get_object()
    streams = contents if isinstance(contents, ArrayObject) else [contents]
    matrices = []
    for element in streams:
        obj = element.get_object()
        if b"Do" not in obj.get_data():
            continue
        stream = ContentStream(obj, page.pdf)
        for ops in stream.operations:
            if ops[1] == b"cm":
                cm = tuple(float(value) for value in ops[0])
                if y_lo <= cm[5] <= y_hi:
                    matrices.append(cm)
    return matrices


class TestSniffDocumentFormat(unittest.TestCase):
    def test_detects_pdf(self):
        self.assertEqual(helpers.sniff_document_format(_b64(b"%PDF-1.4\n%rest")), "PDF")

    def test_detects_zpl(self):
        self.assertEqual(helpers.sniff_document_format(_b64(b"^XA^FO50,50^XZ")), "ZPL")

    def test_detects_png(self):
        self.assertEqual(
            helpers.sniff_document_format(_b64(b"\x89PNG\r\n\x1a\n\x00\x00")), "PNG"
        )

    def test_accepts_raw_bytes(self):
        self.assertEqual(helpers.sniff_document_format(b"%PDF-1.7"), "PDF")

    def test_tolerates_leading_whitespace(self):
        self.assertEqual(helpers.sniff_document_format(_b64(b"  \n^XA^XZ")), "ZPL")

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

        x, y, width, height = stamping.placement_to_pdf_rect(placement, page_height_pt)

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
        original = (
            pypdf.PdfReader(io.BytesIO(base64.b64decode(document)))
            .pages[0]
            .extract_text()
        )
        request = stamping.StampRequest(
            image=_signature_png_b64(), placement=_placement()
        )

        stamped = stamping.stamp_pdf(document, request)
        after = (
            pypdf.PdfReader(io.BytesIO(base64.b64decode(stamped)))
            .pages[0]
            .extract_text()
        )

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

    def test_layer_determines_image_z_order(self):
        # Falsifies a wrong `over` value: the stamp image must be composited
        # ABOVE carrier content for overlay and BENEATH it for underlay. The
        # oracle reads the output page's /Contents array order (= paint order),
        # never re-deriving `over=(layer != "underlay")`.
        document = _sentinel_pdf_b64()

        def carrier_and_image_indices(layer):
            request = stamping.StampRequest(
                image=_signature_png_b64(),
                placement=_placement(),
                layer=layer,
            )
            streams = _ordered_content_streams(stamping.stamp_pdf(document, request))
            carrier = [i for i, s in enumerate(streams) if b"654.321" in s]
            image = [i for i, s in enumerate(streams) if b"Do" in s]
            # Exactly one carrier stream and one distinct stamp-image stream.
            self.assertEqual(len(carrier), 1)
            self.assertEqual(len(image), 1)
            self.assertNotEqual(carrier[0], image[0])
            return carrier[0], image[0]

        carrier_over, image_over = carrier_and_image_indices("overlay")
        carrier_under, image_under = carrier_and_image_indices("underlay")

        # overlay paints the stamp after (above) carrier content...
        self.assertGreater(image_over, carrier_over)
        # ...underlay paints it before (beneath) carrier content.
        self.assertLess(image_under, carrier_under)

    def test_underlay_acroform_fields_remain_fillable(self):
        document = _acroform_pdf_b64()
        request = stamping.StampRequest(
            image=_signature_png_b64(),
            placement=_placement(),
            layer="underlay",
        )

        stamped = stamping.stamp_pdf(document, request)

        self.assertIn("signature_field", _fields(stamped))
        self.assertEqual(_page_count(stamped), _page_count(document))


def _rotated_placement(rotation: float) -> stamping.StampPlacement:
    return stamping.StampPlacement(
        x=40.0, y=200.0, width=60.0, height=20.0, rotation=rotation
    )


class TestPlacementRotation(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_rotation_composes_a_clockwise_matrix_at_the_anchor(self):
        # Oracle: the overlay's leading `cm`. A 90-degree clockwise rotation maps
        # the observed upright scale (sx, 0, 0, sy) to (0, -sx, sy, 0). The scale
        # (sx, sy) is read from the un-rotated stamp, never re-derived from the
        # production rotation expression, so a wrong angle or direction fails.
        document = _sentinel_pdf_b64()
        image = _signature_png_b64()

        (upright,) = _overlay_cms(
            stamping.stamp_pdf(
                document,
                stamping.StampRequest(image=image, placement=_placement()),
            )
        )
        (rotated,) = _overlay_cms(
            stamping.stamp_pdf(
                document,
                stamping.StampRequest(image=image, placement=_rotated_placement(90)),
            )
        )

        # The un-rotated placement is a pure scale (no shear, no rotation).
        self.assertAlmostEqual(upright[1], 0.0, places=9)
        self.assertAlmostEqual(upright[2], 0.0, places=9)
        sx, sy = upright[0], upright[3]

        a, b, c, d = rotated[:4]
        self.assertAlmostEqual(a, 0.0, places=6)
        self.assertAlmostEqual(b, -sx, places=6)
        self.assertAlmostEqual(c, sy, places=6)
        self.assertAlmostEqual(d, 0.0, places=6)

    def test_zero_rotation_is_byte_identical_to_no_rotation(self):
        # The backward-compat invariant (design.md): a 0-degree placement leaves
        # the shipped upright output byte-for-byte unchanged.
        document = _cn22_pdf_b64()
        image = _signature_png_b64()

        no_rotation = stamping.stamp_pdf(
            document, stamping.StampRequest(image=image, placement=_placement())
        )
        zero_rotation = stamping.stamp_pdf(
            document,
            stamping.StampRequest(image=image, placement=_rotated_placement(0)),
        )

        self.assertEqual(no_rotation, zero_rotation)


class TestConsumerDateStamp(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_date_precedes_signature_and_shares_its_rotation(self):
        document = _sentinel_pdf_b64()
        image = _signature_png_b64()

        # Un-rotated: reading order is left-to-right, so the leading (date)
        # overlay's translation-x sits left of the signature overlay's. The two
        # overlays are composited date-first, so paint order labels them.
        upright = _overlay_cms(
            stamping.stamp_pdf(
                document,
                stamping.StampRequest(
                    image=image, placement=_placement(), date="2026-09-22"
                ),
            )
        )
        self.assertEqual(len(upright), 2)
        date_cm, signature_cm = upright
        self.assertLess(date_cm[4], signature_cm[4])

        # Rotated: the date overlay's linear part equals the signature's, so the
        # date shares the signature's rotation; both are a genuine clockwise
        # 90-degree rotation (zero diagonal, b < 0 < c).
        rotated = _overlay_cms(
            stamping.stamp_pdf(
                document,
                stamping.StampRequest(
                    image=image, placement=_rotated_placement(90), date="2026-09-22"
                ),
            )
        )
        self.assertEqual(len(rotated), 2)
        date_cm, signature_cm = rotated
        # The rotation angle is atan2(b, a), scale-independent, so equal angles
        # mean shared rotation even though the two images scale differently.
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
        # Backward-compat: with no date the signature is the only overlay and it
        # spans the whole placement, so its x-scale exceeds the partitioned
        # signature's from the date-present path.
        document = _sentinel_pdf_b64()
        image = _signature_png_b64()

        absent = _overlay_cms(
            stamping.stamp_pdf(
                document,
                stamping.StampRequest(image=image, placement=_placement()),
            )
        )
        present = _overlay_cms(
            stamping.stamp_pdf(
                document,
                stamping.StampRequest(
                    image=image, placement=_placement(), date="2026-09-22"
                ),
            )
        )

        self.assertEqual(len(absent), 1)
        self.assertEqual(len(present), 2)
        self.assertGreater(absent[0][0], present[1][0])

    def test_empty_date_is_treated_as_absent(self):
        document = _sentinel_pdf_b64()
        image = _signature_png_b64()

        composited = _overlay_cms(
            stamping.stamp_pdf(
                document,
                stamping.StampRequest(image=image, placement=_placement(), date=""),
            )
        )

        self.assertEqual(len(composited), 1)

    def test_date_threads_through_lib_stamp_document(self):
        document = _pdf_document()

        stamped = lib.stamp_document(
            document,
            image=_signature_png_b64(),
            placement=_placement(),
            date="2026-09-22",
        )

        self.assertEqual(stamped.format, "PDF")
        self.assertEqual(len(_overlay_cms(stamped.base64)), 2)


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

    def test_stamps_zpl_document(self):
        # ZPL is now a backed format: a `^XA...^XZ` document composites and the
        # returned document is a `^XA`-prefixed ZPL stream carrying the spliced
        # `^GFA` graphic before its trailing `^XZ`.
        document = models.ShippingDocument(
            category="customs_declaration",
            format="ZPL",
            base64=_zpl_doc_b64(),
        )

        stamped = lib.stamp_document(
            document, image=_signature_png_b64(), placement=_zpl_placement()
        )

        self.assertEqual(stamped.format, "ZPL")
        zpl = _decode_zpl(stamped.base64)
        self.assertTrue(zpl.startswith("^XA"))
        self.assertIn("^GFA,", zpl)
        self.assertLess(zpl.index("^GFA,"), zpl.rindex("^XZ"))

    def test_graphic_name_threads_through_lib_stamp_document(self):
        # The re-export forwards `graphic_name` to the ZPL backend, opting into
        # the ~DY (download-once) / ^XG (recall-per-label) cache and replacing
        # the inline ^GFA field entirely, exactly as stamp_zpl does directly.
        document = models.ShippingDocument(
            category="customs_declaration",
            format="ZPL",
            base64=_zpl_doc_b64(),
        )

        stamped = lib.stamp_document(
            document,
            image=_signature_png_b64(),
            placement=_zpl_placement(),
            graphic_name="MYSIG",
        )

        self.assertEqual(stamped.format, "ZPL")
        zpl = _decode_zpl(stamped.base64)
        self.assertIn("~DYMYSIG,", zpl)
        self.assertIn("^XGMYSIG,1,1", zpl)
        self.assertNotIn("^GFA,", zpl)

    def test_default_path_omits_the_zpl_cache(self):
        # Without graphic_name the re-export leaves the inline ^GFA path intact.
        document = models.ShippingDocument(
            category="customs_declaration",
            format="ZPL",
            base64=_zpl_doc_b64(),
        )

        stamped = lib.stamp_document(
            document, image=_signature_png_b64(), placement=_zpl_placement()
        )

        zpl = _decode_zpl(stamped.base64)
        self.assertIn("^GFA,", zpl)
        self.assertNotIn("~DY", zpl)
        self.assertNotIn("^XG", zpl)

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
        self.assertEqual(seen, ["postnord/cn22/PDF/A4"])

    def test_registry_miss_raises_naming_the_key(self):
        # The measured CN22 seed now occupies postnord/cn22/PDF/A4 on the default
        # path, so this miss uses an unseeded doc_type on the same A4 fixture to
        # keep exercising the "a miss names the composed key" property.
        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(
                _pdf_document(),
                image=_signature_png_b64(),
                carrier="postnord",
                doc_type="commercial_invoice",
            )

        message = str(ctx.exception)
        self.assertIn("postnord/commercial_invoice/PDF/A4", message)

    def test_unkeyed_lookup_misses(self):
        with self.assertRaises(ValueError):
            lib.stamp_document(_pdf_document(), image=_signature_png_b64())


class TestPaperVariantDetection(unittest.TestCase):
    def test_detects_a4_from_mediabox_points(self):
        # A4 mediabox in points (210 x 297 mm).
        self.assertEqual(stamping._nearest_paper_variant(595.276, 841.890), "A4")

    def test_detects_letter_from_mediabox_points(self):
        # US Letter mediabox in points (216 x 279 mm = 612 x 792 pt).
        self.assertEqual(stamping._nearest_paper_variant(612.0, 792.0), "LETTER")

    def test_detection_is_orientation_independent(self):
        # A landscape A4 (dimensions swapped) still resolves to A4.
        self.assertEqual(stamping._nearest_paper_variant(841.890, 595.276), "A4")

    def test_unknown_size_is_inconclusive(self):
        # A square page matches no standard within tolerance.
        self.assertEqual(stamping._nearest_paper_variant(500.0, 500.0), "*")

    def test_cn22_fixture_detects_a4(self):
        self.assertEqual(stamping._detect_paper_variant(_cn22_pdf_b64(), "PDF"), "A4")

    def test_non_pdf_format_is_inconclusive(self):
        self.assertEqual(stamping._detect_paper_variant(_b64(b"^XA^XZ"), "ZPL"), "*")


class TestRegistryKey(unittest.TestCase):
    def test_category_normalization_converges(self):
        # The value form, the name form, and one composed literal all agree, so
        # a seed registered under either spelling resolves for the other.
        self.assertEqual(
            stamping._registry_key("postnord", "CustomsDeclaration", "PDF", "A4"),
            stamping._registry_key("postnord", "customs_declaration", "PDF", "A4"),
        )
        self.assertEqual(
            stamping._registry_key("postnord", "CustomsDeclaration", "PDF", "A4"),
            "postnord/customs_declaration/PDF/A4",
        )

    def test_unrecognized_doc_type_falls_back_to_raw(self):
        # PostNord's printoutComposition value "cn22" is not a category member,
        # so it survives verbatim rather than crashing the lookup.
        self.assertEqual(
            stamping._registry_key("postnord", "cn22", "PDF", "A4"),
            "postnord/cn22/PDF/A4",
        )

    def test_missing_segments_become_star(self):
        self.assertEqual(stamping._registry_key(None, None, "PDF", "*"), "*/*/PDF/*")


class TestDefaultRegistry(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_cn22_seed_resolves_to_the_documented_anchor(self):
        placement = stamping._default_registry("postnord/cn22/PDF/A4")

        self.assertIsNotNone(placement)
        self.assertAlmostEqual(placement.x, 53.3, places=1)
        self.assertAlmostEqual(placement.y, 91.4, places=1)
        self.assertAlmostEqual(placement.width, 7.6, places=1)
        self.assertAlmostEqual(placement.height, 49.1, places=1)
        self.assertEqual(placement.rotation, 90)

    def test_unseeded_key_misses(self):
        self.assertIsNone(stamping._default_registry("acme/unknown/PDF/A4"))

    def test_paper_agnostic_seed_resolves_via_fallback(self):
        # A seed registered without a paper variant (paper = "*") resolves for a
        # page whose paper was detected, via the 4-part -> 3-part key relaxation.
        seed = stamping.StampSeed(placement=_placement(), revision=0)
        stamping._SEED_REGISTRY["acme/receipt/PDF/*"] = seed
        self.addCleanup(stamping._SEED_REGISTRY.pop, "acme/receipt/PDF/*", None)

        resolved = stamping._default_registry("acme/receipt/PDF/LETTER")

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.x, _placement().x)

    def test_paper_specific_seed_does_not_leak_across_variants(self):
        # The A4-keyed CN22 seed must not resolve for a LETTER page: the fallback
        # only relaxes to "*", never across concrete paper variants.
        self.assertIsNone(stamping._default_registry("postnord/cn22/PDF/LETTER"))


class TestCn22Seed(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_seed_composites_at_the_measured_anchor(self):
        # Placement OMITTED on the real PostNord CN22 fixture: the default
        # registry must resolve the measured seed and composite date-then-
        # signature at its 90-degree rotation. The fixture draws its own image,
        # so overlays are isolated by the measured strip's vertical band rather
        # than by _overlay_cms's first-cm-per-stream read (which the carrier's
        # own transform would shadow). The band is an independent literal:
        # y 91.4-140.5 mm from the top of an A4 page is 443.6-582.8 pt in
        # bottom-left PDF coordinates.
        stamped = lib.stamp_document(
            _pdf_document(),
            image=_signature_png_b64(),
            date="2026-09-22",
            carrier="postnord",
            doc_type="cn22",
        )

        band = _cms_in_y_band(stamped.base64, 443.0, 583.0)
        self.assertEqual(len(band), 2)
        # Paint order labels the two overlays; the date leads the signature
        # along the strip (shipped 6.2 date-then-signature layout).
        date_cm, signature_cm = band
        self.assertLess(date_cm[4], signature_cm[4])

        # Each overlay's linear part encodes a clockwise 90-degree rotation: a
        # zero diagonal with b < 0 < c (same pattern the group-6 rotation tests
        # assert), confirming the seed's rotation=90 threaded through.
        for cm in band:
            self.assertAlmostEqual(cm[0], 0.0, places=6)
            self.assertAlmostEqual(cm[3], 0.0, places=6)
            self.assertLess(cm[1], 0.0)
            self.assertGreater(cm[2], 0.0)


class TestZplGrfEncoding(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

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
        # A 12-px row (not a byte multiple) pads to two bytes: black at x=0 sets
        # the first byte's MSB (0x80) and black at x=11 sets bit 3 of the second
        # byte (0x80 >> 3 = 0x10), with the trailing pad bits left clear.
        image = PIL.Image.new("1", (12, 1), 1)
        image.putpixel((0, 0), 0)
        image.putpixel((11, 0), 0)

        hexdata, total, bytes_per_row = stamping._encode_grf(image)

        self.assertEqual(bytes_per_row, 2)
        self.assertEqual(total, 2)
        self.assertEqual(hexdata, "8010")

    def test_hex_is_uppercase(self):
        # x=1 alone sets bit 6 (0x40 = "40"); x=0 and x=4 set 0x88 = "88": both
        # uppercase, confirming the encoder never emits lowercase nibbles.
        image = PIL.Image.new("1", (8, 1), 1)
        image.putpixel((0, 0), 0)
        image.putpixel((4, 0), 0)

        hexdata, _, _ = stamping._encode_grf(image)

        self.assertEqual(hexdata, "88")
        self.assertEqual(hexdata, hexdata.upper())


class TestZplDitherContinuity(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def _assert_connected_black_row(self, dpi):
        request = stamping.StampRequest(
            image=_solid_black_png_b64(), placement=_zpl_placement(dpi=dpi)
        )

        raster = stamping._build_zpl_raster(request)

        width, height = raster.size
        pixels = raster.load()
        # A solid-black stamp must survive flatten + resize + Floyd-Steinberg as a
        # fully connected black run: at least one row is black (value 0) across
        # its entire width. The oracle is the raster's own pixels, not the GRF
        # encoder, so an inverted set-bit convention or a lost stroke fails here.
        connected = any(
            all(pixels[x, y] == 0 for x in range(width)) for y in range(height)
        )
        self.assertTrue(connected)

    def test_stroke_stays_connected_at_203_dpi(self):
        self._assert_connected_black_row(203)

    def test_stroke_stays_connected_at_300_dpi(self):
        self._assert_connected_black_row(300)


class TestZplBackend(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_splices_single_grf_before_trailing_xz(self):
        stamped = stamping.stamp_zpl(
            _zpl_doc_b64(),
            stamping.StampRequest(
                image=_signature_png_b64(), placement=_zpl_placement()
            ),
        )
        zpl = _decode_zpl(stamped)

        self.assertTrue(zpl.startswith("^XA"))
        self.assertEqual(zpl.count("^XZ"), 1)
        fields = _grf_fields(zpl)
        self.assertEqual(len(fields), 1)
        # The graphic is drawn last (overlay), so it lands before the final ^XZ.
        self.assertLess(zpl.index("^GFA,"), zpl.index("^XZ"))
        # The carrier field stream survives ahead of the spliced graphic.
        self.assertIn("^GB100,100,2^FS", zpl)

    def test_grf_header_matches_the_raster_dimensions(self):
        request = stamping.StampRequest(
            image=_signature_png_b64(), placement=_zpl_placement()
        )
        raster = stamping._build_zpl_raster(request)
        width, height = raster.size
        expected_bpr = math.ceil(width / 8)

        zpl = _decode_zpl(stamping.stamp_zpl(_zpl_doc_b64(), request))
        (fo_x, fo_y, total, total2, bpr, hexdata), = _grf_fields(zpl)

        # 203 dpi: x=20 mm -> 160 dots, y=30 mm -> 240 dots (independent literals).
        self.assertEqual((fo_x, fo_y), (160, 240))
        self.assertEqual(bpr, expected_bpr)
        self.assertEqual(total, expected_bpr * height)
        self.assertEqual(total2, total)
        self.assertEqual(len(hexdata), total * 2)

    def test_date_composites_into_a_single_raster(self):
        # A supplied date is drawn into the same 1-bpp raster as the signature, so
        # only one GRF graphic is emitted and it differs from the date-less one.
        without_date = stamping.stamp_zpl(
            _zpl_doc_b64(),
            stamping.StampRequest(
                image=_signature_png_b64(), placement=_zpl_placement()
            ),
        )
        with_date = stamping.stamp_zpl(
            _zpl_doc_b64(),
            stamping.StampRequest(
                image=_signature_png_b64(),
                placement=_zpl_placement(),
                date="2026-09-22",
            ),
        )

        self.assertEqual(len(_grf_fields(_decode_zpl(with_date))), 1)
        self.assertNotEqual(
            _grf_fields(_decode_zpl(with_date))[0][5],
            _grf_fields(_decode_zpl(without_date))[0][5],
        )

    def test_underlay_layer_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            stamping.stamp_zpl(
                _zpl_doc_b64(),
                stamping.StampRequest(
                    image=_signature_png_b64(),
                    placement=_zpl_placement(),
                    layer="underlay",
                ),
            )

        self.assertIn("underlay", str(ctx.exception).lower())


class TestZplRotation(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_rotation_swaps_dimensions_and_preserves_center(self):
        # At 203 dpi the placement is 480x160 dots anchored at (160, 240). A
        # 90-degree clockwise rotation swaps the raster to 160x480, so the GRF
        # height becomes 480 (= the un-rotated width). The rotated field is
        # re-anchored so the graphic's centre is unchanged: the un-rotated centre
        # is (400, 320) and the rotated 160x480 graphic centres there only when
        # ^FO is (320, 80) -- an independent literal, not a re-run of the encoder.
        image = _signature_png_b64()

        upright = _decode_zpl(
            stamping.stamp_zpl(
                _zpl_doc_b64(),
                stamping.StampRequest(image=image, placement=_zpl_placement()),
            )
        )
        rotated = _decode_zpl(
            stamping.stamp_zpl(
                _zpl_doc_b64(),
                stamping.StampRequest(
                    image=image, placement=_zpl_placement(rotation=90)
                ),
            )
        )

        (up_x, up_y, up_total, _, up_bpr, _), = _grf_fields(upright)
        (ro_x, ro_y, ro_total, _, ro_bpr, _), = _grf_fields(rotated)

        self.assertEqual((up_x, up_y), (160, 240))
        # Row count is total/bytes_per_row; rotation swaps 480 wide -> 480 tall.
        self.assertEqual(up_total // up_bpr, 160)
        self.assertEqual(ro_total // ro_bpr, 480)
        # The rotated origin differs from the upright one, and re-anchors so the
        # graphic centre is preserved: (320 + 160/2, 80 + 480/2) == (400, 320).
        self.assertEqual((ro_x, ro_y), (320, 80))


class TestZplPrinterCache(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_default_inline_path_is_unaffected_when_caching_off(self):
        request = stamping.StampRequest(
            image=_signature_png_b64(), placement=_zpl_placement()
        )

        first = stamping.stamp_zpl(_zpl_doc_b64(), request)
        second = stamping.stamp_zpl(_zpl_doc_b64(), request)
        zpl = _decode_zpl(first)

        self.assertEqual(first, second)
        self.assertIn("^GFA,", zpl)
        self.assertNotIn("~DY", zpl)
        self.assertNotIn("^XG", zpl)

    def test_opt_in_emits_download_and_recall_with_matching_payload(self):
        inline = _decode_zpl(
            stamping.stamp_zpl(
                _zpl_doc_b64(),
                stamping.StampRequest(
                    image=_signature_png_b64(), placement=_zpl_placement()
                ),
            )
        )
        cached = _decode_zpl(
            stamping.stamp_zpl(
                _zpl_doc_b64(),
                stamping.StampRequest(
                    image=_signature_png_b64(),
                    placement=_zpl_placement(),
                    graphic_name="R:STAMP.GRF",
                ),
            )
        )

        # The opt-in path downloads once (~DY) and recalls per label (^XG),
        # replacing the inline ^GFA entirely, with a matching object name.
        self.assertIn("~DYR:STAMP.GRF,", cached)
        self.assertIn("^XGR:STAMP.GRF,1,1", cached)
        self.assertNotIn("^GFA,", cached)

        # The stored GRF payload is byte-identical to what the inline path packs.
        (_, _, inline_total, _, inline_bpr, inline_hex), = _grf_fields(inline)
        import re

        match = re.search(
            r"~DYR:STAMP\.GRF,A,G,(\d+),(\d+),([0-9A-F]*)", cached
        )
        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(1)), inline_total)
        self.assertEqual(int(match.group(2)), inline_bpr)
        self.assertEqual(match.group(3), inline_hex)


if __name__ == "__main__":
    unittest.main()
