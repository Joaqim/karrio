"""Document stamping: opt-in Z64 compression of the ZPL graphic."""

import re
import zlib
import base64
import inspect
import unittest

import karrio.lib as lib
import karrio.core.models as models
import karrio.core.utils.stamping as stamping

from .stamping_helpers import decode_zpl, rows_png_b64, zpl_doc_b64

# A 16 x 4-dot image stamped at its own size, so each row packs to two bytes:
# FF00, FFFF, 0000 and 00FF.
IMAGE_ROWS = (
    "########........",
    "################",
    "................",
    "........########",
)
PLACEMENT = stamping.StampPlacement(unit="px", x=0, y=0, width=16, height=4)
GOLDEN_HEX = "FF00FFFF000000FF"
GOLDEN_STREAM = "^XA^FO10,10^GB100,100,2^FS^FO0,0^GFA,8,8,2,FF00FFFF000000FF^FS^XZ"


def crc16_xmodem(data: bytes) -> int:
    """Bitwise CRC-16/XMODEM: polynomial 0x1021, initial value 0."""
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def _stamp(**fields):
    return decode_zpl(
        stamping.stamp_zpl(
            zpl_doc_b64(),
            stamping.StampRequest(
                image=rows_png_b64(IMAGE_ROWS), placement=PLACEMENT, **fields
            ),
        )
    )


class TestReferenceCrc(unittest.TestCase):
    def test_reference_matches_the_xmodem_check_value(self):
        self.assertEqual(crc16_xmodem(b"123456789"), 0x31C3)


class TestZ64Compression(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_default_output_is_the_uncompressed_hex_golden(self):
        self.assertEqual(_stamp(), GOLDEN_STREAM)
        self.assertEqual(_stamp(compression=None), GOLDEN_STREAM)

    def test_z64_keeps_the_totals_and_round_trips_to_the_golden(self):
        zpl = _stamp(compression="z64")

        match = re.fullmatch(
            r"\^XA\^FO10,10\^GB100,100,2\^FS\^FO0,0"
            r"\^GFA,(\d+),(\d+),(\d+),:Z64:([A-Za-z0-9+/=]+):([0-9A-F]{4})\^FS\^XZ",
            zpl,
        )
        self.assertIsNotNone(match, zpl)
        total, total2, bpr, data, crc = match.groups()
        self.assertEqual((total, total2, bpr), ("8", "8", "2"))
        self.assertEqual(
            zlib.decompress(base64.b64decode(data)), bytes.fromhex(GOLDEN_HEX)
        )
        self.assertEqual(int(crc, 16), crc16_xmodem(data.encode("ascii")))

    def test_z64_applies_to_the_printer_cache_download(self):
        zpl = _stamp(compression="z64", graphic_name="R:SIGN.GRF")

        download, stream = zpl.split("\n", 1)
        match = re.fullmatch(
            r"~DYR:SIGN\.GRF,A,G,(\d+),(\d+),:Z64:([A-Za-z0-9+/=]+):([0-9A-F]{4})",
            download,
        )
        self.assertIsNotNone(match, download)
        total, bpr, data, crc = match.groups()
        self.assertEqual((total, bpr), ("8", "2"))
        self.assertEqual(
            zlib.decompress(base64.b64decode(data)), bytes.fromhex(GOLDEN_HEX)
        )
        self.assertEqual(int(crc, 16), crc16_xmodem(data.encode("ascii")))
        self.assertEqual(
            stream, "^XA^FO10,10^GB100,100,2^FS^FO0,0^XGR:SIGN.GRF,1,1^FS^XZ"
        )

    def test_unknown_compression_is_rejected_naming_the_accepted_values(self):
        with self.assertRaises(ValueError) as ctx:
            _stamp(compression="gzip")

        self.assertIn("gzip", str(ctx.exception))
        self.assertIn("z64", str(ctx.exception))

    def test_compression_threads_through_lib_stamp_document(self):
        document = models.ShippingDocument(
            category="label", format="ZPL", base64=zpl_doc_b64()
        )

        stamped = lib.stamp_document(
            document,
            image=rows_png_b64(IMAGE_ROWS),
            placement=PLACEMENT,
            compression="z64",
        )

        self.assertIn("^GFA,8,8,2,:Z64:", decode_zpl(stamped.base64))

    def test_stamp_document_rejects_an_unknown_compression(self):
        document = models.ShippingDocument(
            category="label", format="ZPL", base64=zpl_doc_b64()
        )

        with self.assertRaises(ValueError) as ctx:
            lib.stamp_document(
                document,
                image=rows_png_b64(IMAGE_ROWS),
                placement=PLACEMENT,
                compression="gzip",
            )

        self.assertIn("z64", str(ctx.exception))


class TestLibForwarding(unittest.TestCase):
    def test_accepted_compressions_are_exported(self):
        self.assertEqual(lib.STAMP_COMPRESSIONS, ("z64",))

    def test_lib_stamp_document_takes_every_stamping_parameter(self):
        self.assertEqual(
            list(inspect.signature(lib.stamp_document).parameters),
            list(inspect.signature(stamping.stamp_document).parameters),
        )


if __name__ == "__main__":
    unittest.main()
