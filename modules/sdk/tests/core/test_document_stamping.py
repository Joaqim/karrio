import base64
import unittest

import karrio.core.utils.helpers as helpers


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("utf-8")


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


if __name__ == "__main__":
    unittest.main()
