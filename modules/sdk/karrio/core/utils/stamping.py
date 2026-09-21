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

RegistryLookup = typing.Callable[[str], typing.Optional["StampPlacement"]]

MM_PER_INCH: float = 25.4
POINTS_PER_INCH: float = 72.0


@attr.s(auto_attribs=True)
class StampPlacement:
    """Anchor rectangle for compositing an image onto a document page.

    Coordinates are millimetres measured from the top-left of a one-based
    ``page`` index. ``dpi`` is the ZPL target density and is ignored by the
    PDF backend.
    """

    page: int = 1
    x: float = None
    y: float = None
    width: float = None
    height: float = None
    dpi: int = 203


@attr.s(auto_attribs=True)
class StampRequest:
    """One image-compositing operation against a returned carrier document.

    ``image`` is a base64-encoded PNG. A consumer-supplied ``placement`` is the
    primary path and is used directly; ``carrier`` and ``doc_type`` key an
    optional registry seed lookup consulted only when ``placement`` is omitted.
    ``layer`` is ``overlay`` for signatures (drawn over content) or ``underlay``
    for letterheads (drawn beneath content, PDF only).
    """

    image: str = None
    placement: StampPlacement = None
    carrier: str = None
    doc_type: str = None
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


def _build_overlay_page(image_b64: str) -> "pypdf.PageObject":
    """Return a single-page image-PDF page built from a base64 PNG.

    The image is auto-trimmed to its non-transparent bounding box and
    white-flattened before the image-PDF save: Pillow's PDF writer emits no
    soft mask, so alpha is dropped on save (Q6) and a semi-transparent mark
    would otherwise render fully opaque. Compositing onto opaque white
    preserves the mark's intended tone against a blank block.
    """
    source = PIL.Image.open(helpers.to_buffer(image_b64)).convert("RGBA")

    bounds = source.getchannel("A").getbbox()
    trimmed = source.crop(bounds) if bounds is not None else source

    backdrop = PIL.Image.new("RGBA", trimmed.size, (255, 255, 255, 255))
    flattened = PIL.Image.alpha_composite(backdrop, trimmed).convert("RGB")

    buffer = io.BytesIO()
    flattened.save(buffer, format="PDF", dpi=(300, 300))

    return pypdf.PdfReader(buffer).pages[0]


def stamp_pdf(document_b64: str, request: StampRequest) -> str:
    """Composite the request image onto a base64 PDF, returning base64 PDF.

    The carrier document is cloned whole — pages, text layer, and AcroForm
    dictionaries survive untouched — then the placement page receives the
    image via a scale/translate transformation merge. ``overlay`` draws the
    image over the page content; ``underlay`` draws it beneath, so carrier
    content stays legible above a letterhead. The page count is invariant.
    """
    placement = request.placement
    reader = pypdf.PdfReader(helpers.to_buffer(document_b64))
    writer = pypdf.PdfWriter()
    writer.clone_document_from_reader(reader)

    page = writer.pages[(placement.page or 1) - 1]
    x, y, width, height = placement_to_pdf_rect(
        placement, float(page.mediabox.height)
    )

    overlay = _build_overlay_page(request.image)
    transformation = (
        pypdf.Transformation()
        .scale(width / float(overlay.mediabox.width), height / float(overlay.mediabox.height))
        .translate(x, y)
    )
    page.merge_transformed_page(
        overlay, transformation, over=(request.layer != "underlay")
    )

    result = io.BytesIO()
    writer.write(result)

    return base64.b64encode(result.getvalue()).decode("utf-8")


# Per-format compositing backends. Only PDF is active at launch; ZPL is
# recognized by the sniffer but has no backend yet, so it is rejected.
_BACKENDS: typing.Dict[str, typing.Callable[[str, StampRequest], str]] = {
    "PDF": stamp_pdf,
}


def _registry_key(carrier: str, doc_type: str, document_format: str) -> str:
    """Compose the registry lookup key from the request and document format."""
    return "/".join(str(part or "*") for part in (carrier, doc_type, document_format))


def _empty_registry(key: str) -> typing.Optional[StampPlacement]:
    """Launch registry: no seeds are measured yet, so every key misses.

    Registry seeds are a follow-up (task group 4); until they land, this hook
    resolves nothing, forcing the consumer-supplied placement to be the only
    path that produces a stamp.
    """
    return None


def stamp_document(
    document: models.ShippingDocument,
    image: str = None,
    placement: StampPlacement = None,
    layer: str = "overlay",
    carrier: str = None,
    doc_type: str = None,
    registry: RegistryLookup = None,
) -> models.ShippingDocument:
    """Composite a base64 PNG onto a returned carrier document.

    The document format is detected from its bytes and dispatched to the
    matching backend; the returned document preserves the input's format and
    shape, replacing only its ``base64`` content. A consumer-supplied
    ``placement`` is used directly with no registry lookup. When ``placement``
    is omitted, the registry hook is consulted and a miss raises an explicit
    error naming the missing key rather than guessing an anchor. A document
    whose format has no active backend (including PNG) is rejected explicitly.

    The utility composites pixels only: it stores nothing and makes no
    assertion about the legal validity or signature semantics of the result.
    """
    lookup = registry if registry is not None else _empty_registry
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

    resolved = placement
    if resolved is None:
        key = _registry_key(carrier, doc_type, document_format)
        resolved = lookup(key)
        if resolved is None:
            raise ValueError(
                "No stamp placement was supplied and no registry seed "
                f"resolves for key '{key}'"
            )

    request = StampRequest(
        image=image,
        placement=resolved,
        carrier=carrier,
        doc_type=doc_type,
        layer=layer,
    )
    stamped = _BACKENDS[document_format](document.base64, request)

    return attr.evolve(document, base64=stamped)
