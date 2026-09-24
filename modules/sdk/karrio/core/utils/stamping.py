"""Composite a consumer-supplied raster image onto a returned carrier document.

The utility sniffs the document format and dispatches to the matching backend,
returning the document in the same format and shape it arrived in so consumers
never branch on document format themselves. It composites pixels only: it stores
nothing and asserts nothing about the legal validity or signature semantics of
the stamped content — that responsibility belongs to the consumer.
"""

import io
import re
import base64
import typing

import attr
import pypdf
import PIL.Image

import karrio.core.models as models
import karrio.core.utils.helpers as helpers

MM_PER_INCH: float = 25.4
POINTS_PER_INCH: float = 72.0

# ZPL ^FO and graphic operands are valid from 0 to 32000 dots, so any placement
# whose rotated origin or extent resolves outside that range is rejected rather
# than emitted as out-of-spec ZPL that printers interpret inconsistently.
ZPL_OPERAND_LIMIT: int = 32000

# A ZPL stored-object name: an optional device prefix, a 1-8 character name and
# an optional .GRF extension. Anything else could inject ZPL commands into the
# ~DY / ^XG fields the name is interpolated into.
ZPL_GRAPHIC_NAME_PATTERN: str = r"^(?:[A-Z]:)?[A-Z0-9_]{1,8}(?:\.GRF)?$"

# Luminance bound below which a pixel binarizes to ink in the ZPL raster. A
# fixed threshold (not error diffusion) keeps anti-aliased glyph edges solid
# and faint signature strokes connected; error diffusion renders exactly
# those pixels as scattered speckle.
ZPL_INK_THRESHOLD: int = 200

# Resolution of the PDF backend's image-PDF overlay save.
OVERLAY_DPI: int = 300


@attr.s(auto_attribs=True)
class StampPlacement:
    """Anchor rectangle for compositing an image onto a document page.

    Coordinates are millimetres measured from the top-left of a one-based
    ``page`` index; ``width`` and ``height`` are the image's drawn dimensions.
    ``dpi`` is the ZPL target density and is ignored by the PDF backend.
    """

    page: int = 1
    x: float = None
    y: float = None
    width: float = None
    height: float = None
    dpi: int = 203


@attr.s(auto_attribs=True)
class StampRequest:
    """One resolved image-compositing operation handed to a format backend.

    ``image`` is a base64-encoded PNG and ``placement`` the resolved anchor.
    ``layer`` is ``overlay`` for signatures (drawn over content) or
    ``underlay`` for letterheads (drawn beneath content, PDF only).
    ``graphic_name`` opts the ZPL backend into the send-once-per-printer cache:
    the raster is downloaded once as a stored ``~DY`` object and recalled per
    label with ``^XG`` instead of inlining ``^GFA``; the PDF backend ignores it.
    """

    image: str = None
    placement: StampPlacement = None
    layer: str = "overlay"
    graphic_name: str = None


def mm_to_points(value: float) -> float:
    """Convert a millimetre measure to PDF points (1 pt = 1/72 in)."""
    return value * POINTS_PER_INCH / MM_PER_INCH


def mm_to_dots(value: float, dpi: int) -> int:
    """Convert a millimetre measure to whole printer dots at ``dpi``.

    ZPL addresses the label in dots at the printer's density (203 dpi is the
    common default), so a placement's millimetre anchor and extent round to the
    nearest dot: ``dots = round(mm / 25.4 * dpi)``.
    """
    return int(round(value / MM_PER_INCH * dpi))


def placement_to_pdf_rect(
    placement: StampPlacement,
    page_height_pt: float,
) -> typing.Tuple[float, float, float, float]:
    """Return the placement rectangle in PDF points with a bottom-left origin.

    Placement anchors are millimetres from the page top-left, whereas PDF uses a
    bottom-left origin in points. The top-anchored ``y`` is therefore flipped
    against the page height and the rectangle's own height so the returned
    ``(x, y, width, height)`` locates the rectangle's bottom-left corner.
    """
    x = mm_to_points(placement.x)
    width = mm_to_points(placement.width)
    height = mm_to_points(placement.height)
    y = page_height_pt - mm_to_points(placement.y) - height

    return (x, y, width, height)


def _flatten_to_rgb(image_b64: str) -> "PIL.Image.Image":
    """Return a base64 PNG trimmed and white-flattened to an opaque RGB image.

    The image is auto-trimmed to its non-transparent bounding box and
    alpha-composited onto opaque white. Pillow's PDF writer emits no soft mask,
    so alpha would otherwise be dropped on the image-PDF save and a
    semi-transparent mark render fully opaque; the ZPL backend binarizes the
    same flattened image. A missing or undecodable image raises ``ValueError``.
    """
    if not image_b64:
        raise ValueError("A base64 PNG stamp image is required")

    try:
        source = PIL.Image.open(helpers.to_buffer(image_b64)).convert("RGBA")
    except PIL.UnidentifiedImageError as error:
        raise ValueError(
            "The stamp image could not be decoded as a PNG image"
        ) from error

    bounds = source.getchannel("A").getbbox()
    trimmed = source.crop(bounds) if bounds is not None else source

    backdrop = PIL.Image.new("RGBA", trimmed.size, (255, 255, 255, 255))

    return PIL.Image.alpha_composite(backdrop, trimmed).convert("RGB")


def _build_overlay_page(image_b64: str) -> "pypdf.PageObject":
    """Return a single-page image-PDF page built from a base64 PNG."""
    buffer = io.BytesIO()
    _flatten_to_rgb(image_b64).save(
        buffer, format="PDF", dpi=(OVERLAY_DPI, OVERLAY_DPI)
    )

    return pypdf.PdfReader(buffer).pages[0]


def _validate_anchor(placement: StampPlacement) -> None:
    """Reject anchors outside the printable coordinate domain.

    Placement coordinates are millimetres from the page top-left and become ZPL
    ``^FO`` operands valid only from 0, so a negative anchor is rejected before
    any backend work; width and height must be positive measures.
    """
    for field in ("x", "y"):
        value = getattr(placement, field)
        if value is None or value < 0:
            raise ValueError(
                f"StampPlacement.{field} must be a non-negative millimetre "
                f"measure from the page top-left (got {value})"
            )

    for field in ("width", "height"):
        value = getattr(placement, field)
        if value is None or value <= 0:
            raise ValueError(
                f"StampPlacement.{field} must be a positive millimetre measure "
                f"(got {value})"
            )


def _merge_overlay(
    page: "pypdf.PageObject",
    image_b64: str,
    rect: typing.Tuple[float, float, float, float],
    over: bool,
) -> None:
    """Composite one base64 PNG into ``rect`` (PDF points) on ``page``.

    The image PDF is scaled to the rectangle and translated to ``rect``'s
    bottom-left corner.
    """
    x, y, width, height = rect
    overlay = _build_overlay_page(image_b64)
    transformation = (
        pypdf.Transformation()
        .scale(
            width / float(overlay.mediabox.width),
            height / float(overlay.mediabox.height),
        )
        .translate(x, y)
    )

    page.merge_transformed_page(overlay, transformation, over=over)


def _clone_pdf(document_b64: str) -> "pypdf.PdfWriter":
    """Return a writer holding a whole-document clone of a base64 PDF.

    Pages, the text layer and AcroForm dictionaries survive untouched. A
    document pypdf cannot parse raises ``ValueError``.
    """
    writer = pypdf.PdfWriter()
    try:
        writer.clone_document_from_reader(
            pypdf.PdfReader(helpers.to_buffer(document_b64))
        )
    except pypdf.errors.PyPdfError as error:
        raise ValueError(f"The PDF document could not be parsed: {error}") from error

    return writer


def _validate_page(page: int, page_count: int) -> int:
    """Return the zero-based index of a one-based placement page.

    An omitted page means the first; a page outside ``1..page_count`` raises
    rather than stamping a page counted from the end or failing on an index.
    """
    number = 1 if page is None else page
    if not 1 <= number <= page_count:
        raise ValueError(
            f"StampPlacement.page must be between 1 and the document's "
            f"{page_count} page(s) (got {page})"
        )

    return number - 1


def stamp_pdf(document_b64: str, request: StampRequest) -> str:
    """Composite the request image onto a base64 PDF, returning base64 PDF.

    The carrier document is cloned whole — pages, text layer, and AcroForm
    dictionaries survive untouched — then the placement page receives the
    image via a scale/translate transformation merge. ``overlay`` draws the
    image over the page content; ``underlay`` draws it beneath, so carrier
    content stays legible above a letterhead. The page count is invariant.
    """
    placement = request.placement
    _validate_anchor(placement)
    writer = _clone_pdf(document_b64)

    page = writer.pages[_validate_page(placement.page, len(writer.pages))]
    rect = placement_to_pdf_rect(placement, float(page.mediabox.height))
    _merge_overlay(page, request.image, rect, request.layer != "underlay")

    result = io.BytesIO()
    writer.write(result)

    return base64.b64encode(result.getvalue()).decode("utf-8")


def _build_zpl_raster(request: StampRequest) -> "PIL.Image.Image":
    """Return the placement's 1-bpp ink-threshold raster for the ZPL backend.

    The signature is resized onto a white canvas sized to the placement's dot
    extent, then binarized with the fixed ``ZPL_INK_THRESHOLD``. A threshold
    rather than error diffusion keeps the signature's faint strokes solid ink
    instead of scattered speckle; the signature resamples with LANCZOS to
    preserve stroke connectivity across the resize.
    """
    placement = request.placement
    width = max(mm_to_dots(placement.width, placement.dpi), 1)
    height = max(mm_to_dots(placement.height, placement.dpi), 1)

    canvas = PIL.Image.new("RGB", (width, height), (255, 255, 255))
    signature = _flatten_to_rgb(request.image)
    canvas.paste(signature.resize((width, height), PIL.Image.LANCZOS), (0, 0))

    return (
        canvas.convert("L")
        .point(lambda value: 255 if value >= ZPL_INK_THRESHOLD else 0)
        .convert("1", dither=PIL.Image.Dither.NONE)
    )


def _encode_grf(image: "PIL.Image.Image") -> typing.Tuple[str, int, int]:
    """Pack a 1-bpp image into ZPL GRF hex, returning ``(hex, total, per_row)``.

    Rows are byte-padded (``bytes_per_row = ceil(width / 8)``) and bits run
    MSB-first, so the left-most pixel is a byte's high bit; a set bit is black
    (value ``0`` in Pillow's ``"1"`` mode). ``total`` is ``bytes_per_row *
    height`` and the hex is uppercase, matching the ``^GFA`` header operands.
    """
    width, height = image.size
    bytes_per_row = (width + 7) // 8
    pixels = image.load()

    rows = []
    for y in range(height):
        row = bytearray(bytes_per_row)
        for x in range(width):
            if pixels[x, y] == 0:
                row[x // 8] |= 0x80 >> (x % 8)
        rows.append(bytes(row).hex().upper())

    return "".join(rows), bytes_per_row * height, bytes_per_row


def _splice_zpl_field(stream: str, field: str) -> str:
    """Insert ``field`` immediately before the carrier stream's trailing ``^XZ``.

    ZPL has no z-order; a later field is drawn on top, so splicing before the
    format-close ``^XZ`` draws the graphic over the carrier content. A stream
    with no ``^XZ`` is closed after the appended field.
    """
    marker = "^XZ"
    index = stream.rfind(marker)
    if index == -1:
        return f"{stream}{field}{marker}"

    return f"{stream[:index]}{field}{stream[index:]}"


def _zpl_raster_extent(placement: StampPlacement) -> typing.Tuple[int, int]:
    """Return the raster's dot extent without building the raster."""
    return (
        max(mm_to_dots(placement.width, placement.dpi), 1),
        max(mm_to_dots(placement.height, placement.dpi), 1),
    )


def _validate_zpl_operands(x_dots: int, y_dots: int, width: int, height: int) -> None:
    """Reject a ZPL origin or extent outside the ``^FO`` operand range."""
    for edge, operand in (
        ("x origin", x_dots),
        ("y origin", y_dots),
        ("x extent", x_dots + width),
        ("y extent", y_dots + height),
    ):
        if not 0 <= operand <= ZPL_OPERAND_LIMIT:
            raise ValueError(
                f"The stamp's {edge} resolves to {operand} dots, outside the "
                f"ZPL ^FO operand range 0-{ZPL_OPERAND_LIMIT}"
            )


def _validate_graphic_name(graphic_name: str) -> None:
    """Reject a ZPL stored-object name that is not a plain object name."""
    if not re.match(ZPL_GRAPHIC_NAME_PATTERN, graphic_name):
        raise ValueError(
            f"The ZPL graphic name '{graphic_name}' must be an optional device "
            "prefix, 1-8 uppercase letters, digits or underscores, and an "
            "optional .GRF extension (for example R:SIGN.GRF)"
        )


def stamp_zpl(document_b64: str, request: StampRequest) -> str:
    """Composite the request image onto a base64 ZPL stream, returning base64.

    The image is flattened, resized to the placement's dot extent, binarized to
    a 1-bpp raster, and encoded as a GRF graphic spliced over the carrier field
    stream at the placement's ``^FO`` origin. Any origin or extent operand
    resolving outside the ZPL range 0-32000 is rejected before the raster is
    built. ``request.graphic_name`` opts into the ``~DY`` / ``^XG``
    send-once cache. ZPL has no z-order, so an ``underlay`` layer (letterhead)
    is out of practical scope and is rejected.
    """
    if request.layer == "underlay":
        raise ValueError(
            "ZPL stamping supports only the overlay layer; a ZPL underlay "
            "(letterhead) is out of practical scope because ZPL has no z-order"
        )

    if request.graphic_name:
        _validate_graphic_name(request.graphic_name)

    placement = request.placement
    _validate_anchor(placement)
    x_dots = mm_to_dots(placement.x, placement.dpi)
    y_dots = mm_to_dots(placement.y, placement.dpi)
    _validate_zpl_operands(x_dots, y_dots, *_zpl_raster_extent(placement))

    stream = helpers.decode_bytes(base64.b64decode(document_b64))
    hexdata, total, bytes_per_row = _encode_grf(_build_zpl_raster(request))

    if request.graphic_name:
        download = f"~DY{request.graphic_name},A,G,{total},{bytes_per_row},{hexdata}"
        field = f"^FO{x_dots},{y_dots}^XG{request.graphic_name},1,1^FS"
        result = f"{download}\n{_splice_zpl_field(stream, field)}"
    else:
        field = (
            f"^FO{x_dots},{y_dots}^GFA,{total},{total}," f"{bytes_per_row},{hexdata}^FS"
        )
        result = _splice_zpl_field(stream, field)

    return base64.b64encode(result.encode("utf-8")).decode("utf-8")


# Per-format compositing backends. PNG is recognized by the sniffer but has no
# backend, so the dispatcher rejects it.
_BACKENDS: typing.Dict[str, typing.Callable[[str, StampRequest], str]] = {
    "PDF": stamp_pdf,
    "ZPL": stamp_zpl,
}


def stamp_document(
    document: models.ShippingDocument,
    image: str = None,
    placement: StampPlacement = None,
    layer: str = "overlay",
    graphic_name: str = None,
) -> models.ShippingDocument:
    """Composite a base64 PNG onto a returned carrier document.

    The document format is detected from its bytes and dispatched to the
    matching backend; the returned document preserves the input's format and
    shape, replacing only its ``base64`` content. A document whose format has
    no active backend (including PNG) is rejected explicitly, as is an omitted
    ``placement``. An optional ``graphic_name`` opts the ZPL backend into
    the ``~DY`` / ``^XG`` printer cache.

    The utility composites pixels only: it stores nothing and makes no
    assertion about the legal validity or signature semantics of the result.
    """
    document_format = helpers.sniff_document_format(
        document.base64,
        content_type=document.format,
        default=document.format,
    )

    if document_format not in _BACKENDS:
        raise ValueError(
            f"Document stamping has no active backend for the "
            f"'{document_format}' format; the document cannot be stamped"
        )

    if placement is None:
        raise ValueError(
            "No stamp placement was supplied; a StampPlacement anchoring the "
            "image is required"
        )

    request = StampRequest(
        image=image,
        placement=placement,
        layer=layer,
        graphic_name=graphic_name,
    )
    stamped = _BACKENDS[document_format](document.base64, request)

    return attr.evolve(document, base64=stamped)
