"""Generated fixtures and output oracles shared by the document stamping suites.

Every carrier document is generated in-process so the suites stay
carrier-neutral; the one checked-in fixture is a real anti-aliased signature
PNG. The oracles read the written output (content-stream ``cm`` matrices,
parsed ``^GFA`` headers, raster pixels) and never re-run production maths.
"""

import io
import os
import re
import base64

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

import karrio.core.models as models
import karrio.core.utils.stamping as stamping

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

SIGNATURE_FIXTURE = os.path.join(FIXTURES_DIR, "signature_test.png")

# The text the generated PDF form prints in its selectable text layer.
FORM_TEXT = "Customs declaration"

# Where the generated PDF form draws its own image: translation-y 151.7 pt,
# outside every stamp band the suites select on.
FORM_IMAGE_Y_PT = 151.7


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("utf-8")


def _png_b64(image: "PIL.Image.Image") -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return b64(buffer.getvalue())


def _pdf_b64(writer: "pypdf.PdfWriter") -> str:
    buffer = io.BytesIO()
    writer.write(buffer)
    return b64(buffer.getvalue())


def signature_png_b64() -> str:
    """A synthetic RGBA signature PNG on a transparent background."""
    image = PIL.Image.new("RGBA", (400, 140), (255, 255, 255, 0))
    draw = PIL.ImageDraw.Draw(image)
    draw.line((20, 70, 380, 70), fill=(0, 0, 0, 180), width=6)
    draw.ellipse((120, 30, 280, 110), outline=(0, 0, 0, 220), width=4)
    return _png_b64(image)


def real_signature_b64() -> str:
    """The checked-in signature: 450x180 RGBA, anti-aliased ink on alpha."""
    with open(SIGNATURE_FIXTURE, "rb") as handle:
        return b64(handle.read())


def blank_pdf_b64(pages: int = 1, width: float = 595, height: float = 842) -> str:
    """A PDF of blank pages; the default 595 x 842 pt page is A4."""
    writer = pypdf.PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=width, height=height)
    return _pdf_b64(writer)


def form_pdf_b64(with_image: bool = False) -> str:
    """A 1-page A4 form with a selectable text layer.

    The page's content stream sets ``FORM_TEXT`` in the standard-14 Helvetica
    font (no embedding), so ``extract_text`` reads it back. With
    ``with_image`` the page also draws its own image at ``FORM_IMAGE_Y_PT``,
    which makes pypdf concatenate the first stamp overlay into the form's own
    image-drawing stream, as carrier documents with logos do.
    """
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=595, height=842)

    font = DictionaryObject()
    font.update(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    fonts = DictionaryObject({NameObject("/F1"): writer._add_object(font)})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): fonts})

    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 72 720 Td ({FORM_TEXT}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(content)

    if with_image:
        logo = PIL.Image.new("RGB", (120, 40), (0, 0, 0))
        buffer = io.BytesIO()
        logo.save(buffer, format="PDF", dpi=(300, 300))
        logo_page = pypdf.PdfReader(buffer).pages[0]
        page.merge_transformed_page(
            logo_page, pypdf.Transformation().translate(72, FORM_IMAGE_Y_PT)
        )

    return _pdf_b64(writer)


def acroform_pdf_b64() -> str:
    """A 2-page PDF whose first page carries one fillable text field."""
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

    return _pdf_b64(writer)


def sentinel_pdf_b64() -> str:
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

    return _pdf_b64(writer)


def page_count(document_b64: str) -> int:
    return len(pypdf.PdfReader(io.BytesIO(base64.b64decode(document_b64))).pages)


def form_fields(document_b64: str):
    return (
        pypdf.PdfReader(io.BytesIO(base64.b64decode(document_b64))).get_fields() or {}
    )


def page_text(document_b64: str, page_index: int = 0) -> str:
    return (
        pypdf.PdfReader(io.BytesIO(base64.b64decode(document_b64)))
        .pages[page_index]
        .extract_text()
    )


def ordered_content_streams(document_b64: str, page_index: int = 0):
    """Return a page's content streams as bytes in ``/Contents`` array order.

    Per the PDF spec, when ``/Contents`` is an array of streams they are
    concatenated in array order to form the page content, so a lower array
    index is painted first and therefore drawn *beneath* higher indices.
    Observing this order in the written-out PDF reports where the stamp image
    actually landed, not how the caller asked for it.
    """
    page = pypdf.PdfReader(io.BytesIO(base64.b64decode(document_b64))).pages[page_index]
    contents = page["/Contents"].get_object()
    if isinstance(contents, ArrayObject):
        return [element.get_object().get_data() for element in contents]
    return [contents.get_data()]


def _image_streams(document_b64: str, page_index: int):
    page = pypdf.PdfReader(io.BytesIO(base64.b64decode(document_b64))).pages[page_index]
    if "/Contents" not in page:
        return []
    contents = page["/Contents"].get_object()
    streams = contents if isinstance(contents, ArrayObject) else [contents]
    return [
        ContentStream(element.get_object(), page.pdf)
        for element in streams
        if b"Do" in element.get_object().get_data()
    ]


def overlay_cms(document_b64: str, page_index: int = 0):
    """Return each overlay stream's leading ``cm`` matrix, in paint order.

    An overlay stream is a page content stream carrying an image draw (``Do``).
    ``merge_transformed_page`` prepends the placement transformation as the
    stream's first ``cm`` operator, so the leading ``cm`` of each overlay stream
    is where that image landed on the page. The image XObject carries a later
    ``cm`` of its own; only the first one is the placement matrix.
    """
    return [
        tuple(
            float(value)
            for value in next(ops for ops in stream.operations if ops[1] == b"cm")[0]
        )
        for stream in _image_streams(document_b64, page_index)
    ]


def cms_in_y_band(document_b64: str, y_lo: float, y_hi: float, page_index: int = 0):
    """Return every image-stream ``cm`` whose translation-y lands in a band.

    A page that already draws its own image makes pypdf concatenate the first
    stamp overlay into that image-drawing stream, so its leading ``cm`` is the
    page's own transform. Selecting ``cm`` operators by where they land
    isolates the stamp overlays, since the page's own transform falls outside
    the band.
    """
    return [
        cm
        for stream in _image_streams(document_b64, page_index)
        for cm in (
            tuple(float(value) for value in ops[0])
            for ops in stream.operations
            if ops[1] == b"cm"
        )
        if y_lo <= cm[5] <= y_hi
    ]


def placement() -> stamping.StampPlacement:
    return stamping.StampPlacement(x=40.0, y=200.0, width=60.0, height=20.0)


def pdf_document() -> models.ShippingDocument:
    return models.ShippingDocument(
        category="customs_declaration", format="PDF", base64=form_pdf_b64()
    )


def acroform_document() -> models.ShippingDocument:
    return models.ShippingDocument(
        category="customs_declaration", format="PDF", base64=acroform_pdf_b64()
    )


def png_document() -> models.ShippingDocument:
    return models.ShippingDocument(
        category="customs_declaration", format="PNG", base64=signature_png_b64()
    )


# A carrier-style ZPL form: a redundant second ^XA open, ^LL label length, a
# ^FWR-rotated field stream with ^FB blocks, float ^FO operands and an ^FD
# block whose text spans physical lines. The keyword field sits at ^FO20,35.
EXAMPLE_ZPL_FORM = "\n".join(
    [
        "^XA",
        "^LL1520",
        "^FX utf-8^FS   ^CI28",
        "^XA",
        "^LH0,0",
        "^FWN",
        "^FO10,15",
        "^GB820,680,1,^FS",
        "^FO420,468.3333333333333",
        "^GB170,0,1^FS",
        "^CF0,20,20",
        "^FWR",
        "^FB300,2, 0,L",
        "^FO740,35",
        "^FDCUSTOMS DECLARATION^FS",
        "^FB186.66666666666666,1, 0,C",
        "^FO385,488.3333333333333",
        "^FDTotal Weight (in kg)^FS",
        "^FB620,6, 0,L",
        "^FO25,35",
        "^FDI, the undersigned, certify that the particulars given ",
        "  in this declaration are correct^FS",
        "^FB620,1, 0,L",
        "^FO20,35",
        "^FDSender signature^FS",
        "^FO165,295",
        "^FDREF0012345^FS",
        "^XZ",
    ]
)


def example_zpl_form_b64() -> str:
    return b64(EXAMPLE_ZPL_FORM.encode("utf-8"))


def zpl_doc_b64(stream: str = "^XA^FO10,10^GB100,100,2^FS^XZ") -> str:
    return b64(stream.encode("utf-8"))


def decode_zpl(document_b64: str) -> str:
    return base64.b64decode(document_b64).decode("utf-8")


def zpl_document(stream: str = None) -> models.ShippingDocument:
    return models.ShippingDocument(
        category="customs_declaration",
        format="ZPL",
        base64=zpl_doc_b64(stream) if stream else zpl_doc_b64(),
    )


def zpl_placement(rotation: float = 0, dpi: int = 203) -> stamping.StampPlacement:
    # At 203 dpi 20/30/60/20 mm resolve to 160/240/480/160 dots.
    return stamping.StampPlacement(
        x=20.0, y=30.0, width=60.0, height=20.0, rotation=rotation, dpi=dpi
    )


def rotated_placement(rotation: float) -> stamping.StampPlacement:
    return stamping.StampPlacement(
        x=40.0, y=200.0, width=60.0, height=20.0, rotation=rotation
    )


def grf_fields(zpl: str):
    """Return each inline ``^FO..^GFA..^FS`` field as a parsed tuple.

    The tuple is ``(fo_x, fo_y, total, total2, bytes_per_row, hexdata)`` with the
    four numeric header fields as ints and the hex payload verbatim, so a test
    can assert the exact origin, byte counts, and bytes-per-row independently of
    the production encoder.
    """
    return [
        (int(x), int(y), int(t1), int(t2), int(bpr), hexdata)
        for x, y, t1, t2, bpr, hexdata in re.findall(
            r"\^FO(\d+),(\d+)\^GFA,(\d+),(\d+),(\d+),([0-9A-F]*)\^FS", zpl
        )
    ]


def solid_black_png_b64(width: int = 400, height: int = 140) -> str:
    """An opaque solid-black PNG: flattens to pure black at any density."""
    return _png_b64(PIL.Image.new("RGBA", (width, height), (0, 0, 0, 255)))


def faint_stroke_png_b64(width: int = 400, height: int = 140) -> str:
    """A semi-transparent signature stroke: flattens to gray ~115 on white."""
    image = PIL.Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = PIL.ImageDraw.Draw(image)
    draw.line((20, height // 2, width - 20, height // 2), fill=(0, 0, 0, 140), width=3)
    return _png_b64(image)
