"""Fixture-backed stamping suite: real signature, real carrier documents.

Where ``test_document_stamping`` exercises the backends with synthetic images
and minimal streams, this suite composites the actual consumer signature PNG
and the actual PostNord CN22 documents, so the flatten / dither / splice
pipeline runs against real-world bytes: an anti-aliased RGBA signature, a ZPL
field stream carrying ``^FB`` blocks, float ``^FO`` operands and two ``^XA``
opens, and the carrier PDF with its own drawn images.
"""

import io
import os
import re
import base64
import unittest

import pypdf
import PIL.Image
from pypdf.generic import ArrayObject, ContentStream

import karrio.lib as lib
import karrio.core.models as models
import karrio.core.utils.stamping as stamping

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

SIGNATURE_FIXTURE = os.path.join(FIXTURES_DIR, "signature_test.png")
CN22_ZPL_FIXTURE = os.path.join(FIXTURES_DIR, "postnord_cn22.zpl")
CN22_PDF_FIXTURE = os.path.join(FIXTURES_DIR, "postnord_cn22.pdf")


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("utf-8")


def _signature_b64() -> str:
    """The real consumer signature: 450x180 RGBA, anti-aliased ink on alpha."""
    with open(SIGNATURE_FIXTURE, "rb") as handle:
        return _b64(handle.read())


def _cn22_zpl_b64() -> str:
    """The real PostNord CN22 ZPL form (^LL1520, ^FWR-rotated field stream)."""
    with open(CN22_ZPL_FIXTURE, "rb") as handle:
        return _b64(handle.read())


def _cn22_pdf_b64() -> str:
    with open(CN22_PDF_FIXTURE, "rb") as handle:
        return _b64(handle.read())


def _decode_zpl(b64: str) -> str:
    return base64.b64decode(b64).decode("utf-8")


def _grf_fields(zpl: str):
    """Parse each inline ``^FO..^GFA..^FS`` field as ``(x, y, t1, t2, bpr, hex)``."""
    return [
        (int(x), int(y), int(t1), int(t2), int(bpr), hexdata)
        for x, y, t1, t2, bpr, hexdata in re.findall(
            r"\^FO(\d+),(\d+)\^GFA,(\d+),(\d+),(\d+),([0-9A-F]*)\^FS", zpl
        )
    ]


def _cms_in_y_band(b64, y_lo, y_hi, page_index: int = 0):
    """Return every content-stream ``cm`` whose translation-y lands in a band.

    The CN22 PDF draws its own images, so the first stamp overlay is
    concatenated into a carrier stream whose leading ``cm`` is the carrier's
    transform. Selecting ``cm`` operators by where they land isolates the stamp
    overlays: the carrier's own transforms fall outside the measured band.
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


# The suite's standing ZPL placement: a 33x12 mm strip at (5, 100) mm rotated 90
# clockwise at 203 dpi, landing in the blank stock below the form box (which
# ends at y=695 dots). At 203 dpi the millimetres resolve to whole dots --
# 40/799/264/96 -- and the rotated 96x264 raster anchors with its top-left at
# the placement's own ^FO40,799, hanging down-right into the blank stock.
_ZPL_PLACEMENT = stamping.StampPlacement(
    x=5.0, y=100.0, width=33.0, height=12.0, rotation=90, dpi=203
)

# The probe-measured CN22 signature strip's anchor band on the A4 PDF
# (revision 3, PRDs/KEYWORD_ANCHORED_STAMPING.md appendix B): the strip's
# rotated extent anchors top-left at page 53.34, 91.44 mm, so the
# single-image overlay's translation sits at 582.7 pt in bottom-left PDF
# coordinates (841.9 pt page height minus the anchor's 259.2 pt). The band
# brackets that translation while excluding the carrier's own image transform
# at 151.7 pt.
_CN22_BAND_PT = (575.0, 590.0)


class TestVendoredFixtures(unittest.TestCase):
    def test_signature_fixture_is_a_transparent_rgba_png(self):
        image = PIL.Image.open(SIGNATURE_FIXTURE)

        self.assertEqual(image.size, (450, 180))
        self.assertEqual(image.mode, "RGBA")
        alpha = image.getchannel("A").histogram()
        # A transparent ground plus substantive opaque ink: the flatten path
        # must composite anti-aliased alpha, not an opaque rectangle.
        self.assertGreater(alpha[0], 0)
        self.assertGreater(sum(alpha[128:]), 0)

    def test_cn22_zpl_fixture_is_the_pristine_rotated_form(self):
        stream = _decode_zpl(_cn22_zpl_b64())

        self.assertTrue(stream.startswith("^XA"))
        self.assertIn("^LL1520", stream)
        self.assertIn("^FWR", stream)
        self.assertIn("Date and Sender's signature", stream)
        # The unstamped form carries no graphic fields of its own, so any ^GFA
        # in a stamped output comes from the stamp.
        self.assertNotIn("^GFA", stream)


class TestStampRealZplForm(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.request = stamping.StampRequest(
            image=_signature_b64(), placement=_ZPL_PLACEMENT
        )

    def test_stamp_splices_one_grf_onto_the_real_form(self):
        zpl = _decode_zpl(stamping.stamp_zpl(_cn22_zpl_b64(), self.request))

        self.assertTrue(zpl.startswith("^XA"))
        self.assertEqual(zpl.count("^XZ"), 1)
        # The carrier field stream survives the splice.
        self.assertIn("CUSTOMS DECLARATION", zpl)
        self.assertIn("SE5561234711", zpl)
        fields = _grf_fields(zpl)
        self.assertEqual(len(fields), 1)
        self.assertLess(zpl.index("^GFA,"), zpl.rindex("^XZ"))

    def test_rotation_anchors_the_rotated_corner_on_the_real_form(self):
        # Independent literals: 5/100/33/12 mm at 203 dpi resolve to
        # 40/799/264/96 dots; the 90-degree clockwise rotation swaps the raster
        # to 96x264 dots whose top-left anchors at the placement's own ^FO40,799.
        zpl = _decode_zpl(stamping.stamp_zpl(_cn22_zpl_b64(), self.request))

        ((fo_x, fo_y, total, total2, bpr, hexdata),) = _grf_fields(zpl)

        self.assertEqual((fo_x, fo_y), (40, 799))
        self.assertEqual(bpr, 12)
        self.assertEqual(total, 3168)
        self.assertEqual(total2, total)
        self.assertEqual(len(hexdata), total * 2)

    def test_incident_placement_anchors_the_rotated_corner(self):
        # The 2026-09-22 live incident: (0, 0, 70, 20, rotation=90) at 203 dpi
        # against this form must anchor the rotated strip's top-left at the page
        # corner -- ^FO0,0 with a 160x559-dot raster -- never a centre-pivot
        # ^FO200,-200 that sits half off-label.
        placement = stamping.StampPlacement(
            x=0.0, y=0.0, width=70.0, height=20.0, rotation=90, dpi=203
        )

        zpl = _decode_zpl(
            stamping.stamp_zpl(
                _cn22_zpl_b64(),
                stamping.StampRequest(image=_signature_b64(), placement=placement),
            )
        )

        ((fo_x, fo_y, total, _, bpr, _),) = _grf_fields(zpl)

        self.assertEqual((fo_x, fo_y), (0, 0))
        self.assertEqual(bpr, 20)
        self.assertEqual(total, 11180)

    def test_fo_operands_stay_within_the_zpl_valid_range(self):
        # ^FO operands are valid from 0 to 32000 dots, so a placement whose
        # rotated extent leaves the label must surface as a rejected placement,
        # never as a silently emitted out-of-spec operand.
        zpl = _decode_zpl(stamping.stamp_zpl(_cn22_zpl_b64(), self.request))

        ((fo_x, fo_y, *_),) = _grf_fields(zpl)

        for operand in (fo_x, fo_y):
            self.assertTrue(0 <= operand <= 32000, operand)

    def test_real_signature_keeps_ink_through_flatten_and_dither(self):
        raster = stamping._build_zpl_raster(self.request)

        self.assertEqual(raster.mode, "1")
        self.assertEqual(raster.size, (264, 96))
        black = raster.histogram()[0]
        fraction = black / (264 * 96)
        # The real signature is sparse anti-aliased ink: it survives the
        # white-flatten and Floyd-Steinberg dither as neither blank nor solid.
        self.assertGreater(fraction, 0.005)
        self.assertLess(fraction, 0.30)

    def test_lib_stamp_document_returns_a_new_zpl_document(self):
        document = models.ShippingDocument(
            category="customs_declaration", format="ZPL", base64=_cn22_zpl_b64()
        )

        stamped = lib.stamp_document(
            document, image=_signature_b64(), placement=_ZPL_PLACEMENT
        )

        self.assertEqual(stamped.format, "ZPL")
        self.assertEqual(stamped.category, document.category)
        self.assertIn("^GFA,", _decode_zpl(stamped.base64))
        self.assertEqual(document.base64, _cn22_zpl_b64())


class TestStampRealPdfForm(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_real_signature_preserves_the_text_layer(self):
        document = _cn22_pdf_b64()
        original = (
            pypdf.PdfReader(io.BytesIO(base64.b64decode(document)))
            .pages[0]
            .extract_text()
        )
        request = stamping.StampRequest(
            image=_signature_b64(),
            # A neutral valid placement: the test is seed-independent, so any
            # on-page placement exercises the text layer the same way and
            # future seed revisions never touch it.
            placement=stamping.StampPlacement(
                x=100.0, y=100.0, width=40.0, height=20.0
            ),
        )

        stamped = stamping.stamp_pdf(document, request)
        reader = pypdf.PdfReader(io.BytesIO(base64.b64decode(stamped)))

        self.assertEqual(len(reader.pages), 1)
        self.assertEqual(reader.pages[0].extract_text().strip(), original.strip())

    def test_registry_seed_composites_the_real_signature_clockwise(self):
        # Placement omitted: the default registry resolves the measured
        # postnord/cn22/PDF/A4 seed and composites the real signature at the
        # probe-measured anchor. For rotation 90 the merged overlay's
        # translation equals its anchor (_rotated_corner_extents yields
        # (0, 0)), so the expected values are computed from the probe literals
        # and the A4 page height, never read from the seed object.
        anchor_x_pt = 53.34 * 72.0 / 25.4
        anchor_y_pt = 297.0 * 72.0 / 25.4 - 91.44 * 72.0 / 25.4

        stamped = lib.stamp_document(
            models.ShippingDocument(
                category="customs_declaration", format="PDF", base64=_cn22_pdf_b64()
            ),
            image=_signature_b64(),
            carrier="postnord",
            doc_type="cn22",
        )

        band = _cms_in_y_band(stamped.base64, *_CN22_BAND_PT)

        self.assertEqual(len(band), 1)
        (cm,) = band
        self.assertAlmostEqual(cm[4], anchor_x_pt, places=1)
        self.assertAlmostEqual(cm[5], anchor_y_pt, places=1)
        # The clockwise 90-degree linear part (zero diagonal, b < 0 < c) that
        # matches the ZPL form's ^FWR axis; this discriminates the rotation=90
        # encoding from an upright rotation=0 encoding of the same rectangle.
        self.assertAlmostEqual(cm[0], 0.0, places=6)
        self.assertAlmostEqual(cm[3], 0.0, places=6)
        self.assertLess(cm[1], 0.0)
        self.assertGreater(cm[2], 0.0)


def _cn22_zpl_document() -> models.ShippingDocument:
    return models.ShippingDocument(
        category="customs_declaration", format="ZPL", base64=_cn22_zpl_b64()
    )


class TestCn22KeywordStamp(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        # The shipped seed for the ZPL sibling key (D12): the same StampSeed
        # object as the PDF entry, carrying the form keyword and the strip
        # geometry whose x/y are the offsets from the located ^FO origin.
        self.seed = stamping._SEED_REGISTRY["postnord/cn22/ZPL/*"]

    def test_keyword_stamp_resolves_from_the_signature_field(self):
        # The consumer keyword against the real form, with the geometry coming
        # from the seed: exactly one ^GFA field spliced at the measured anchor
        # -- ^FO7,303 with a 61x392-dot rotated raster, bpr 8, total 3136 --
        # and the carrier text surviving.
        stamped = lib.stamp_document(
            _cn22_zpl_document(),
            image=_signature_b64(),
            carrier="postnord",
            doc_type="cn22",
            keyword=self.seed.keyword,
        )

        zpl = _decode_zpl(stamped.base64)
        fields = _grf_fields(zpl)
        self.assertEqual(len(fields), 1)
        ((fo_x, fo_y, total, total2, bpr, hexdata),) = fields
        self.assertEqual((fo_x, fo_y), (7, 303))
        self.assertEqual(bpr, 8)
        self.assertEqual(total, 3136)
        self.assertEqual(total2, total)
        self.assertEqual(len(hexdata), total * 2)
        self.assertIn(self.seed.keyword, zpl)
        self.assertEqual(zpl.count("^XZ"), 1)

    def test_keyword_stamp_with_date_composites_one_strip(self):
        # The single call with image AND date composites one combined strip at
        # the measured origin (never two graphics), and the strip's ink
        # survives flatten + dither as neither blank nor solid. The rotated
        # raster is 61 dots wide against bpr 8, so each row carries 3 zero pad
        # bits and the ink fraction needs no pad-bit masking.
        stamped = lib.stamp_document(
            _cn22_zpl_document(),
            image=_signature_b64(),
            carrier="postnord",
            doc_type="cn22",
            keyword=self.seed.keyword,
            date="2026-09-24",
        )

        zpl = _decode_zpl(stamped.base64)
        fields = _grf_fields(zpl)
        self.assertEqual(len(fields), 1)
        ((fo_x, fo_y, total, _, _, hexdata),) = fields
        self.assertEqual((fo_x, fo_y), (7, 303))

        fraction = bin(int(hexdata, 16)).count("1") / (total * 8)
        self.assertGreater(fraction, 0.005)
        self.assertLess(fraction, 0.30)


if __name__ == "__main__":
    unittest.main()
