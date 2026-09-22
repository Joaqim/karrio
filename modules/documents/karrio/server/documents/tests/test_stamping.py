import io
import base64

import pypdf
import PIL.Image
import PIL.ImageDraw
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from karrio.server.core.tests import APITestCase


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("utf-8")


def _a4_pdf_b64() -> str:
    """A minimal 1-page A4 PDF (595 x 842 pt) that detects as the A4 variant."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buffer = io.BytesIO()
    writer.write(buffer)
    return _b64(buffer.getvalue())


def _signature_png_b64() -> str:
    """A synthetic RGBA signature PNG on a transparent background."""
    image = PIL.Image.new("RGBA", (400, 140), (255, 255, 255, 0))
    draw = PIL.ImageDraw.Draw(image)
    draw.line((20, 70, 380, 70), fill=(0, 0, 0, 180), width=6)
    draw.ellipse((120, 30, 280, 110), outline=(0, 0, 0, 220), width=4)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return _b64(buffer.getvalue())


def _zpl_doc_b64(stream: str = "^XA^FO10,10^GB100,100,2^FS^XZ") -> str:
    return _b64(stream.encode("utf-8"))


A4_PDF_BASE64 = _a4_pdf_b64()
SIGNATURE_PNG_BASE64 = _signature_png_b64()
PNG_DOCUMENT_BASE64 = _signature_png_b64()
ZPL_DOCUMENT_BASE64 = _zpl_doc_b64()

PDF_PLACEMENT = {"x": 40.0, "y": 200.0, "width": 60.0, "height": 20.0}
ZPL_PLACEMENT = {"x": 20.0, "y": 30.0, "width": 60.0, "height": 20.0, "dpi": 203}


class TestDocumentStamper(APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.url = reverse("karrio.server.documents:document-stamper")

    def test_stamp_pdf_returns_base64_same_format(self):
        """A valid PDF + supplied placement returns a stamped base64 PDF."""
        response = self.client.post(
            self.url,
            {
                "document": A4_PDF_BASE64,
                "image": SIGNATURE_PNG_BASE64,
                "placement": PDF_PLACEMENT,
            },
            format="json",
        )

        self.assertResponseNoErrors(response)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data.get("format"), "PDF")
        decoded = base64.b64decode(response.data["doc_file"])
        self.assertTrue(decoded.startswith(b"%PDF"))

    def test_stamp_zpl_returns_base64_same_format(self):
        """A valid ZPL document + supplied placement returns a stamped ZPL."""
        response = self.client.post(
            self.url,
            {
                "document": ZPL_DOCUMENT_BASE64,
                "image": SIGNATURE_PNG_BASE64,
                "placement": ZPL_PLACEMENT,
            },
            format="json",
        )

        self.assertResponseNoErrors(response)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data.get("format"), "ZPL")
        decoded = base64.b64decode(response.data["doc_file"]).decode("utf-8")
        self.assertTrue(decoded.startswith("^XA"))
        self.assertIn("^GFA,", decoded)

    def test_stamp_seed_path_resolves_and_stamps(self):
        """Omitting placement resolves the shipped PostNord CN22 A4 seed."""
        response = self.client.post(
            self.url,
            {
                "document": A4_PDF_BASE64,
                "image": SIGNATURE_PNG_BASE64,
                "carrier": "postnord",
                "doc_type": "cn22",
            },
            format="json",
        )

        self.assertResponseNoErrors(response)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data.get("format"), "PDF")
        decoded = base64.b64decode(response.data["doc_file"])
        self.assertTrue(decoded.startswith(b"%PDF"))

    def test_stamp_rejects_png_document(self):
        """A PNG document is a client fault: 400, not 500."""
        response = self.client.post(
            self.url,
            {
                "document": PNG_DOCUMENT_BASE64,
                "image": SIGNATURE_PNG_BASE64,
                "placement": {"x": 10.0, "y": 10.0, "width": 20.0, "height": 20.0},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("PNG", str(response.content))

    def test_stamp_registry_miss_returns_400_naming_key(self):
        """No placement and no matching seed returns 400 naming the missed key."""
        response = self.client.post(
            self.url,
            {
                "document": A4_PDF_BASE64,
                "image": SIGNATURE_PNG_BASE64,
                "carrier": "postnord",
                "doc_type": "commercial_invoice",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("postnord/commercial_invoice/PDF/A4", str(response.content))

    def test_stamp_requires_authentication(self):
        """An unauthenticated request is rejected."""
        anonymous = APIClient()
        response = anonymous.post(
            self.url,
            {
                "document": A4_PDF_BASE64,
                "image": SIGNATURE_PNG_BASE64,
                "placement": PDF_PLACEMENT,
            },
            format="json",
        )

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
