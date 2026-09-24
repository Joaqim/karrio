"""Composite a consumer-supplied raster image onto a returned carrier document.

The utility sniffs the document format and dispatches to the matching backend,
returning the document in the same format and shape it arrived in so consumers
never branch on document format themselves. It composites pixels only: it stores
nothing and asserts nothing about the legal validity or signature semantics of
the stamped content — that responsibility belongs to the consumer.
"""

import io
import base64
import typing

import attr
import pypdf
import PIL.Image

import karrio.core.models as models
import karrio.core.utils.helpers as helpers

MM_PER_INCH: float = 25.4
POINTS_PER_INCH: float = 72.0

# Resolution of the PDF backend's image-PDF overlay save.
OVERLAY_DPI: int = 300


@attr.s(auto_attribs=True)
class StampPlacement:
    """Anchor rectangle for compositing an image onto a document page.

    Coordinates are millimetres measured from the top-left of a one-based
    ``page`` index; ``width`` and ``height`` are the image's drawn dimensions.
    """

    page: int = 1
    x: float = None
    y: float = None
    width: float = None
    height: float = None


@attr.s(auto_attribs=True)
class StampRequest:
    """One resolved image-compositing operation handed to a format backend.

    ``image`` is a base64-encoded PNG and ``placement`` the resolved anchor.
    ``layer`` is ``overlay`` for signatures (drawn over content) or
    ``underlay`` for letterheads (drawn beneath content).
    """

    image: str = None
    placement: StampPlacement = None
    layer: str = "overlay"


def mm_to_points(value: float) -> float:
    """Convert a millimetre measure to PDF points (1 pt = 1/72 in)."""
    return value * POINTS_PER_INCH / MM_PER_INCH


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
    semi-transparent mark render fully opaque. A missing or undecodable image
    raises ``ValueError``.
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

    Placement coordinates are millimetres from the page top-left, so a
    negative anchor lies off the page and is rejected before any backend work;
    width and height must be positive measures.
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


# Per-format compositing backends. PNG is recognized by the sniffer but has no
# backend, so the dispatcher rejects it.
_BACKENDS: typing.Dict[str, typing.Callable[[str, StampRequest], str]] = {
    "PDF": stamp_pdf,
}


def stamp_document(
    document: models.ShippingDocument,
    image: str = None,
    placement: StampPlacement = None,
    layer: str = "overlay",
) -> models.ShippingDocument:
    """Composite a base64 PNG onto a returned carrier document.

    The document format is detected from its bytes and dispatched to the
    matching backend; the returned document preserves the input's format and
    shape, replacing only its ``base64`` content. A document whose format has
    no active backend (including PNG) is rejected explicitly, as is an omitted
    ``placement``.

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
    )
    stamped = _BACKENDS[document_format](document.base64, request)

    return attr.evolve(document, base64=stamped)
