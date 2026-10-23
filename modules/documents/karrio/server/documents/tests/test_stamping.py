import io
import base64
from unittest import mock

import pypdf
import PIL.Image
import PIL.ImageDraw
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from karrio.server.core.tests import APITestCase
from karrio.server.core.models import APILogIndex
import karrio.lib as lib
import karrio.core.metadata as metadata


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("utf-8")


def _a4_pdf_b64(pages: int = 1) -> str:
    """A minimal blank A4 PDF (595 x 842 pt) that detects as the A4 variant."""
    writer = pypdf.PdfWriter()
    for _ in range(pages):
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

# A carrier plugin declaring one A4 PDF seed, standing in for any connector
# that contributes stamp_seeds through its PluginMetadata.
ACME_PROVIDERS = {
    "acme": metadata.PluginMetadata(
        id="acme",
        label="Acme",
        stamp_seeds={
            "customs_declaration/PDF/A4": lib.StampSeed(
                placement=lib.StampPlacement(
                    x=50.0, y=90.0, width=50.0, height=8.0, rotation=90
                ),
                revision=1,
            )
        },
    )
}


def _providers(providers=ACME_PROVIDERS):
    return mock.patch(
        "karrio.references.collect_providers_data", return_value=providers
    )


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
        """Omitting placement resolves the carrier plugin's A4 seed."""
        with _providers():
            response = self.client.post(
                self.url,
                {
                    "document": A4_PDF_BASE64,
                    "image": SIGNATURE_PNG_BASE64,
                    "carrier": "acme",
                    "doc_type": "customs_declaration",
                },
                format="json",
            )

        self.assertResponseNoErrors(response)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data.get("format"), "PDF")
        decoded = base64.b64decode(response.data["doc_file"])
        self.assertTrue(decoded.startswith(b"%PDF"))

    def test_stamp_seed_on_the_requested_page(self):
        """A page applies the carrier plugin's page-1 seed on that page."""
        with _providers():
            response = self.client.post(
                self.url,
                {
                    "document": _a4_pdf_b64(pages=2),
                    "image": SIGNATURE_PNG_BASE64,
                    "carrier": "acme",
                    "doc_type": "customs_declaration",
                    "page": 2,
                },
                format="json",
            )

        self.assertResponseNoErrors(response)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        pages = pypdf.PdfReader(
            io.BytesIO(base64.b64decode(response.data["doc_file"]))
        ).pages
        self.assertEqual(
            ["/Contents" in page for page in pages],
            [False, True],
        )

    def test_stamp_seed_page_beyond_the_document_returns_400(self):
        """A requested page past the last page is a 400 naming the bounds."""
        with _providers():
            response = self.client.post(
                self.url,
                {
                    "document": A4_PDF_BASE64,
                    "image": SIGNATURE_PNG_BASE64,
                    "carrier": "acme",
                    "doc_type": "customs_declaration",
                    "page": 2,
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("1 page(s)", str(response.content))

    def test_stamp_placement_outside_the_page_returns_400(self):
        """A placement drawn past the mediabox is a 400 naming the edge."""
        response = self.client.post(
            self.url,
            {
                "document": A4_PDF_BASE64,
                "image": SIGNATURE_PNG_BASE64,
                "placement": {"x": 200.0, "y": 50.0, "width": 20.0, "height": 10.0},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("right edge", str(response.content))

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
        with _providers():
            response = self.client.post(
                self.url,
                {
                    "document": A4_PDF_BASE64,
                    "image": SIGNATURE_PNG_BASE64,
                    "carrier": "acme",
                    "doc_type": "commercial_invoice",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("acme/commercial_invoice/PDF/A4", str(response.content))

    def test_stamp_zpl_with_graphic_name_reaches_the_cache_over_http(self):
        """graphic_name threads through the endpoint into the ZPL ~DY/^XG cache."""
        response = self.client.post(
            self.url,
            {
                "document": ZPL_DOCUMENT_BASE64,
                "image": SIGNATURE_PNG_BASE64,
                "placement": ZPL_PLACEMENT,
                "graphic_name": "R:STAMP.GRF",
            },
            format="json",
        )

        self.assertResponseNoErrors(response)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        decoded = base64.b64decode(response.data["doc_file"]).decode("utf-8")
        self.assertIn("~DYR:STAMP.GRF,", decoded)
        self.assertIn("^XGR:STAMP.GRF,1,1", decoded)
        self.assertNotIn("^GFA,", decoded)

    def test_stamp_zpl_underlay_returns_400(self):
        """ZPL has no z-order: an underlay layer is a client fault (400, not 500)."""
        response = self.client.post(
            self.url,
            {
                "document": ZPL_DOCUMENT_BASE64,
                "image": SIGNATURE_PNG_BASE64,
                "placement": ZPL_PLACEMENT,
                "layer": "underlay",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("underlay", str(response.content))

    def test_stamp_unbacked_format_returns_400(self):
        """Bytes matching no backed format and no hint are a 400, not a 500."""
        unbacked = base64.b64encode(
            b"plain text that is neither a PDF nor a ZPL document"
        ).decode("utf-8")
        response = self.client.post(
            self.url,
            {
                "document": unbacked,
                "image": SIGNATURE_PNG_BASE64,
                "placement": {"x": 10.0, "y": 10.0, "width": 20.0, "height": 20.0},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("backend", str(response.content))

    def test_stamp_without_image_returns_400(self):
        """The image is required: omitting it is a client fault, not a 500."""
        response = self.client.post(
            self.url,
            {"document": A4_PDF_BASE64, "placement": PDF_PLACEMENT},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_stamp_undecodable_image_returns_400(self):
        """Image bytes Pillow cannot identify are a client fault, not a 500."""
        response = self.client.post(
            self.url,
            {
                "document": A4_PDF_BASE64,
                "image": _b64(b"not a png image"),
                "placement": PDF_PLACEMENT,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("image", str(response.content))

    def test_stamp_corrupt_pdf_returns_400(self):
        """A document with a PDF signature that pypdf cannot parse is a 400."""
        response = self.client.post(
            self.url,
            {
                "document": _b64(b"%PDF-1.4 truncated garbage"),
                "image": SIGNATURE_PNG_BASE64,
                "placement": PDF_PLACEMENT,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("PDF", str(response.content))

    def test_stamp_page_beyond_the_document_returns_400(self):
        """A placement page past the last page is a 400 naming the page."""
        response = self.client.post(
            self.url,
            {
                "document": A4_PDF_BASE64,
                "image": SIGNATURE_PNG_BASE64,
                "placement": {**PDF_PLACEMENT, "page": 2},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("StampPlacement.page", str(response.content))

    def test_stamp_non_positive_page_returns_400(self):
        """Pages are 1-based: zero and negative pages fail validation."""
        responses = [
            self.client.post(
                self.url,
                {
                    "document": A4_PDF_BASE64,
                    "image": SIGNATURE_PNG_BASE64,
                    "placement": {**PDF_PLACEMENT, "page": page},
                },
                format="json",
            )
            for page in (0, -1)
        ]

        self.assertEqual(
            [response.status_code for response in responses],
            [status.HTTP_400_BAD_REQUEST, status.HTTP_400_BAD_REQUEST],
        )

    def test_stamp_graphic_name_with_zpl_commands_returns_400(self):
        """A graphic name carrying ZPL command characters is rejected."""
        response = self.client.post(
            self.url,
            {
                "document": ZPL_DOCUMENT_BASE64,
                "image": SIGNATURE_PNG_BASE64,
                "placement": ZPL_PLACEMENT,
                "graphic_name": "A^FDinjected",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn(b"injected", response.content)

    def test_successful_stamp_is_not_indexed_in_api_log(self):
        """The endpoint skips LoggingMixin, so the base64 never lands in APILogIndex.

        DocumentStamper extends BaseAPIView (no LoggingMixin), unlike the logged
        GenericAPIView/APIView bases, so a successful stamp adds no log row and
        the base64 response is absent from every APILogIndex row.
        """
        before = APILogIndex.objects.count()

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

        doc_file = response.data["doc_file"]
        self.assertEqual(APILogIndex.objects.count(), before)
        self.assertFalse(
            APILogIndex.objects.filter(response__contains=doc_file[:120]).exists()
        )

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


# A ZPL label whose keyword field sits at ^FO160,240.
KEYWORD_ZPL_BASE64 = _zpl_doc_b64("^XA^FO160,240^FDSender signature^FS^XZ")
# Two ZPL formats; the second opens just after the first ^XZ.
TWO_FORMAT_ZPL = "^XA^FO10,10^GB100,100,2^FS^XZ^XA^FO20,20^GB50,50,1^FS^XZ"


def _decoded(response) -> str:
    return base64.b64decode(response.data["doc_file"]).decode("utf-8")


class TestDocumentStamperGeometryFields(APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.url = reverse("karrio.server.documents:document-stamper")

    def _post(self, **data):
        return self.client.post(
            self.url,
            {"image": SIGNATURE_PNG_BASE64, **data},
            format="json",
        )

    def test_keyword_with_an_extent_only_placement_stamps_zpl(self):
        response = self._post(
            document=KEYWORD_ZPL_BASE64,
            keyword="Sender signature",
            placement={"width": 60.0, "height": 20.0, "rotation": 0},
        )

        self.assertResponseNoErrors(response)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertDictEqual(
            dict(response.data), {"doc_file": mock.ANY, "format": "ZPL"}
        )
        self.assertIn("^FO160,240^GFA,", _decoded(response))

    def test_keyword_offsets_the_located_field(self):
        # 10 mm and 5 mm at 203 dpi are 80 and 40 dots from ^FO160,240.
        response = self._post(
            document=KEYWORD_ZPL_BASE64,
            keyword="Sender signature",
            placement={"x": 10.0, "y": 5.0, "width": 60.0, "height": 20.0},
        )

        self.assertResponseNoErrors(response)
        self.assertIn("^FO240,280^GFA,", _decoded(response))

    def test_pixel_units_and_z64_compression(self):
        response = self._post(
            document=ZPL_DOCUMENT_BASE64,
            placement={
                "unit": "px",
                "x": 40,
                "y": 60,
                "width": 400,
                "height": 140,
                "dpi": 203,
            },
            compression="z64",
        )

        self.assertResponseNoErrors(response)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("^FO40,60^GFA,7000,7000,50,:Z64:", _decoded(response))

    def test_page_two_stamps_the_second_zpl_format(self):
        response = self._post(
            document=_zpl_doc_b64(TWO_FORMAT_ZPL),
            placement={**ZPL_PLACEMENT, "page": 2},
        )

        self.assertResponseNoErrors(response)
        zpl = _decoded(response)
        first_format = "^XA^FO10,10^GB100,100,2^FS^XZ"
        self.assertTrue(zpl.startswith(first_format + "^XA^FO20,20^GB50,50,1^FS"))
        self.assertGreater(zpl.index("^GFA,"), len(first_format))

    def test_one_anchor_without_a_keyword_returns_400(self):
        response = self._post(
            document=A4_PDF_BASE64,
            placement={"x": 40.0, "width": 60.0, "height": 20.0},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertDictEqual(
            response.json(),
            {
                "errors": [
                    {
                        "message": "Invalid input data",
                        "details": {
                            "placement": [
                                "StampPlacement.y is required with "
                                "StampPlacement.x unless a keyword is supplied"
                            ]
                        },
                    }
                ]
            },
        )

    def test_no_anchor_without_a_keyword_returns_400_naming_the_keyword(self):
        response = self._post(
            document=A4_PDF_BASE64,
            placement={"width": 60.0, "height": 20.0},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertDictEqual(
            response.json(),
            {
                "errors": [
                    {
                        "message": "Invalid input data",
                        "details": {
                            "placement": [
                                "A placement without x and y needs a keyword "
                                "to locate it"
                            ]
                        },
                    }
                ]
            },
        )

    def test_unknown_unit_or_compression_returns_400(self):
        for field, data in (
            ("placement", {"placement": {**PDF_PLACEMENT, "unit": "in"}}),
            ("compression", {"placement": PDF_PLACEMENT, "compression": "gzip"}),
        ):
            with self.subTest(field=field):
                response = self._post(document=A4_PDF_BASE64, **data)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.json()["errors"][0]["details"])
