"""PostNord CN22 stamping: the plugin's seeds against the real CN22 documents."""

import io
import os
import re
import base64
import unittest

import pypdf
import PIL.Image
import PIL.ImageDraw
from pypdf.generic import ArrayObject, ContentStream

import karrio.lib as lib
import karrio.references as references
import karrio.core.models as models
import karrio.core.utils.stamping as stamping
import karrio.providers.postnord.stamping as postnord_stamping

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

KEYWORD = "Date and Sender's signature"

# The measured signature strip on the A4 CN22 PDF, as independent literals:
# page x 53.34-60.96 mm, y 91.44-140.55 mm, encoded as a pre-rotation
# 49.11 x 7.62 mm extent at rotation 90 anchored top-left at (53.34, 91.44).
STRIP_ANCHOR_MM = (53.34, 91.44)
STRIP_EXTENT_MM = (49.11, 7.62)

# The fixture page's A4 height (mediabox 841.8898 pt).
PAGE_HEIGHT_MM = 297.0


def _read_b64(name: str) -> str:
    with open(os.path.join(FIXTURES_DIR, name), "rb") as handle:
        return base64.b64encode(handle.read()).decode("utf-8")


def _cn22_pdf() -> models.ShippingDocument:
    return models.ShippingDocument(
        category="customs_declaration",
        format="PDF",
        base64=_read_b64("postnord_cn22.pdf"),
    )


def _cn22_zpl() -> models.ShippingDocument:
    return models.ShippingDocument(
        category="customs_declaration",
        format="ZPL",
        base64=_read_b64("postnord_cn22.zpl"),
    )


def _signature_png_b64() -> str:
    image = PIL.Image.new("RGBA", (400, 140), (255, 255, 255, 0))
    draw = PIL.ImageDraw.Draw(image)
    draw.line((20, 70, 380, 70), fill=(0, 0, 0, 180), width=6)
    draw.ellipse((120, 30, 280, 110), outline=(0, 0, 0, 220), width=4)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _decode_zpl(document_b64: str) -> str:
    return base64.b64decode(document_b64).decode("utf-8")


def _grf_fields(zpl: str):
    return [
        (int(x), int(y), int(t1), int(t2), int(bpr), hexdata)
        for x, y, t1, t2, bpr, hexdata in re.findall(
            r"\^FO(\d+),(\d+)\^GFA,(\d+),(\d+),(\d+),([0-9A-F]*)\^FS", zpl
        )
    ]


def _cms_in_y_band(document_b64: str, y_lo: float, y_hi: float):
    """Every image-stream ``cm`` whose translation-y lands in a band.

    The CN22 PDF draws its own images, so the first stamp overlay joins a
    carrier stream whose leading ``cm`` is the carrier's transform (151.7 pt);
    selecting by band isolates the stamp overlays.
    """
    page = pypdf.PdfReader(io.BytesIO(base64.b64decode(document_b64))).pages[0]
    contents = page["/Contents"].get_object()
    streams = contents if isinstance(contents, ArrayObject) else [contents]
    return [
        cm
        for element in streams
        if b"Do" in element.get_object().get_data()
        for cm in (
            tuple(float(value) for value in ops[0])
            for ops in ContentStream(element.get_object(), page.pdf).operations
            if ops[1] == b"cm"
        )
        if y_lo <= cm[5] <= y_hi
    ]


def _anchor_pt():
    # For rotation 90 the merged overlay's translation equals its anchor.
    return (
        STRIP_ANCHOR_MM[0] * 72.0 / 25.4,
        (PAGE_HEIGHT_MM - STRIP_ANCHOR_MM[1]) * 72.0 / 25.4,
    )


class TestPostnordStampSeeds(unittest.TestCase):
    def test_plugin_metadata_declares_the_cn22_seeds(self):
        # Resolved through the loaded plugins, exactly as the stamping core
        # reads them, without importing the connector first.
        seeds = references.collect_providers_data()["postnord"].stamp_seeds

        self.assertEqual(set(seeds), {"cn22/PDF/A4", "cn22/ZPL/*"})
        self.assertIs(seeds["cn22/PDF/A4"], postnord_stamping.CN22_SEED)

    def test_cn22_seed_resolves_to_the_measured_strip(self):
        # The oracle literals come from the measurement, never from the seed
        # object, so a seed change without a re-measurement breaks here.
        placement = stamping._default_registry("postnord/cn22/PDF/A4")

        self.assertAlmostEqual(placement.x, STRIP_ANCHOR_MM[0], places=2)
        self.assertAlmostEqual(placement.y, STRIP_ANCHOR_MM[1], places=2)
        self.assertAlmostEqual(placement.width, STRIP_EXTENT_MM[0], places=2)
        self.assertAlmostEqual(placement.height, STRIP_EXTENT_MM[1], places=2)
        self.assertEqual(placement.rotation, 90)
        # Under rotation 90 the rendered rectangle is `height` wide and
        # `width` tall hanging down-right from the anchor.
        self.assertAlmostEqual(placement.x + placement.height, 60.96, places=2)
        self.assertAlmostEqual(placement.y + placement.width, 140.55, places=2)

    def test_cn22_seed_supersedes_revision_two(self):
        self.assertEqual(postnord_stamping.CN22_SEED.revision, 3)

    def test_a4_seed_does_not_leak_to_letter(self):
        self.assertIsNone(stamping._default_registry("postnord/cn22/PDF/LETTER"))

    def test_cn22_pdf_fixture_detects_a4(self):
        self.assertEqual(
            stamping._detect_paper_variant(_cn22_pdf().base64, "PDF"), "A4"
        )

    def test_cn22_zpl_fixture_is_the_pristine_rotated_form(self):
        stream = _decode_zpl(_cn22_zpl().base64)

        self.assertTrue(stream.startswith("^XA"))
        self.assertIn("^LL1520", stream)
        self.assertIn("^FWR", stream)
        self.assertIn(KEYWORD, stream)
        self.assertNotIn("^GFA", stream)


class TestCn22PdfStamp(unittest.TestCase):
    def test_seed_composites_date_and_signature_at_the_strip(self):
        stamped = lib.stamp_document(
            _cn22_pdf(),
            image=_signature_png_b64(),
            date="2026-09-22",
            carrier="postnord",
            doc_type="cn22",
        )

        anchor_x, anchor_y = _anchor_pt()
        date_width_pt = STRIP_EXTENT_MM[0] * 72.0 / 25.4 * 0.5
        band = _cms_in_y_band(stamped.base64, 505.0, 590.0)

        self.assertEqual(len(band), 2)
        date_cm, signature_cm = band
        self.assertGreater(date_cm[5], signature_cm[5])
        self.assertAlmostEqual(date_cm[4], anchor_x, places=1)
        self.assertAlmostEqual(date_cm[5], anchor_y, places=1)
        self.assertAlmostEqual(signature_cm[4], anchor_x, places=1)
        self.assertAlmostEqual(signature_cm[5], anchor_y - date_width_pt, places=1)
        # A clockwise quarter turn: zero diagonal with b < 0 < c.
        for cm in band:
            self.assertAlmostEqual(cm[0], 0.0, places=6)
            self.assertAlmostEqual(cm[3], 0.0, places=6)
            self.assertLess(cm[1], 0.0)
            self.assertGreater(cm[2], 0.0)

    def test_stamp_preserves_the_text_layer(self):
        document = _cn22_pdf()
        original = (
            pypdf.PdfReader(io.BytesIO(base64.b64decode(document.base64)))
            .pages[0]
            .extract_text()
        )

        stamped = lib.stamp_document(
            document, image=_signature_png_b64(), carrier="postnord", doc_type="cn22"
        )
        after = (
            pypdf.PdfReader(io.BytesIO(base64.b64decode(stamped.base64)))
            .pages[0]
            .extract_text()
        )

        self.assertTrue(original.strip())
        self.assertEqual(after.strip(), original.strip())


class TestCn22ZplStamp(unittest.TestCase):
    def test_seeded_form_resolves_implicitly_by_keyword(self):
        # The keyword field sits at ^FO20,35 in the form; the measured offset
        # resolves to ^FO7,303 with a 61 x 392-dot raster (8 bytes/row).
        stamped = lib.stamp_document(
            _cn22_zpl(), image=_signature_png_b64(), carrier="postnord", doc_type="cn22"
        )

        zpl = _decode_zpl(stamped.base64)
        ((fo_x, fo_y, total, total2, bpr, hexdata),) = _grf_fields(zpl)
        self.assertEqual((fo_x, fo_y), (7, 303))
        self.assertEqual((bpr, total, total2), (8, 3136, 3136))
        self.assertEqual(len(hexdata), total * 2)
        self.assertIn(KEYWORD, zpl)
        self.assertIn("CUSTOMS DECLARATION", zpl)
        self.assertEqual(zpl.count("^XZ"), 1)

    def test_consumer_keyword_outranks_the_seed_keyword(self):
        # The Total Weight field's ^FO385,488.33 origin (form line 107) differs
        # from the seed keyword's ^FO20,35, so the operands identify the winner.
        stamped = lib.stamp_document(
            _cn22_zpl(),
            image=_signature_png_b64(),
            carrier="postnord",
            doc_type="cn22",
            keyword="Total Weight (in kg)",
        )

        ((fo_x, fo_y, *_),) = _grf_fields(_decode_zpl(stamped.base64))
        self.assertEqual(
            (fo_x, fo_y),
            (
                int(round(((385 * 25.4 / 203) - 1.673) / 25.4 * 203)),
                int(round(((488.3333333333333 * 25.4 / 203) + 33.529) / 25.4 * 203)),
            ),
        )

    def test_keyword_stamp_with_date_composites_one_strip(self):
        stamped = lib.stamp_document(
            _cn22_zpl(),
            image=_signature_png_b64(),
            carrier="postnord",
            doc_type="cn22",
            keyword=KEYWORD,
            date="2026-09-24",
        )

        ((fo_x, fo_y, total, _, _, hexdata),) = _grf_fields(_decode_zpl(stamped.base64))
        self.assertEqual((fo_x, fo_y), (7, 303))
        fraction = bin(int(hexdata, 16)).count("1") / (total * 8)
        self.assertGreater(fraction, 0.005)
        self.assertLess(fraction, 0.30)

    def test_rotated_placement_anchors_the_corner_on_the_form(self):
        # 5/100/33/12 mm at 203 dpi resolve to 40/799/264/96 dots; rotated 90
        # the 96 x 264 raster hangs down-right from ^FO40,799 in blank stock.
        stamped = lib.stamp_document(
            _cn22_zpl(),
            image=_signature_png_b64(),
            placement=lib.StampPlacement(
                x=5.0, y=100.0, width=33.0, height=12.0, rotation=90, dpi=203
            ),
        )

        ((fo_x, fo_y, total, _, bpr, _),) = _grf_fields(_decode_zpl(stamped.base64))
        self.assertEqual((fo_x, fo_y), (40, 799))
        self.assertEqual((bpr, total), (12, 3168))


if __name__ == "__main__":
    unittest.main()
