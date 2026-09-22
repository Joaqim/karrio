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
import PIL.ImageDraw
import PIL.ImageFont

import karrio.core.models as models
import karrio.core.units as units
import karrio.core.utils.helpers as helpers

RegistryLookup = typing.Callable[[str], typing.Optional["StampPlacement"]]

MM_PER_INCH: float = 25.4
POINTS_PER_INCH: float = 72.0

# Fraction of the placement's primary (un-rotated) axis given to the date strip
# when a date is supplied; the signature takes the remainder. A simple even
# split until the group-4 CN22 seed measures a per-carrier partition (Q9).
DATE_STRIP_FRACTION: float = 0.5

# Standard portrait page sizes in millimetres, keyed by the paper-variant
# segment they contribute to a registry key. Detection compares a page's
# mediabox against these on the orientation-independent (short, long) axes.
STANDARD_PAPER_MM: typing.Dict[str, typing.Tuple[float, float]] = {
    "A4": (210.0, 297.0),
    "LETTER": (216.0, 279.0),
}

# Per-axis millimetre tolerance for matching a page to a standard size. A4 and
# LETTER differ by 6 mm in width and 18 mm in height, so 3 mm separates them
# unambiguously while absorbing sub-millimetre rendering rounding.
PAPER_VARIANT_TOLERANCE_MM: float = 3.0


@attr.s(auto_attribs=True)
class StampPlacement:
    """Anchor rectangle for compositing an image onto a document page.

    Coordinates are millimetres measured from the top-left of a one-based
    ``page`` index. ``rotation`` is degrees clockwise about the rectangle's
    centre, defaulting to ``0`` (upright); ``width`` and ``height`` are the
    image's dimensions before rotation. ``dpi`` is the ZPL target density and
    is ignored by the PDF backend.
    """

    page: int = 1
    x: float = None
    y: float = None
    width: float = None
    height: float = None
    rotation: float = 0
    dpi: int = 203


@attr.s(auto_attribs=True)
class StampRequest:
    """One image-compositing operation against a returned carrier document.

    ``image`` is a base64-encoded PNG. A consumer-supplied ``placement`` is the
    primary path and is used directly; ``carrier`` and ``doc_type`` key an
    optional registry seed lookup consulted only when ``placement`` is omitted.
    ``layer`` is ``overlay`` for signatures (drawn over content) or ``underlay``
    for letterheads (drawn beneath content, PDF only). ``date`` is an optional
    pre-formatted date string composited preceding the signature at the same
    rotation; the caller owns its format and locale.
    """

    image: str = None
    placement: StampPlacement = None
    carrier: str = None
    doc_type: str = None
    layer: str = "overlay"
    date: str = None


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


def _render_date_image(date: str) -> str:
    """Render a pre-formatted date string to a transparent base64 PNG.

    The caller owns the string's format and locale; the text is rendered
    verbatim with Pillow's built-in font (no bundled asset, Q8) as black glyphs
    on a fully transparent ground, so the shared overlay path trims and
    white-flattens the date exactly as it does a signature.
    """
    font = PIL.ImageFont.load_default()
    ruler = PIL.ImageDraw.Draw(PIL.Image.new("RGBA", (1, 1)))
    left, top, right, bottom = ruler.textbbox((0, 0), date, font=font)
    width = int(max(right - left, 1))
    height = int(max(bottom - top, 1))

    image = PIL.Image.new("RGBA", (width, height), (255, 255, 255, 0))
    PIL.ImageDraw.Draw(image).text((-left, -top), date, fill=(0, 0, 0, 255), font=font)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _merge_overlay(
    page: "pypdf.PageObject",
    image_b64: str,
    rect: typing.Tuple[float, float, float, float],
    rotation: float,
    over: bool,
) -> None:
    """Composite one base64 PNG into ``rect`` (PDF points) on ``page``.

    The image PDF is scaled to the rectangle and, when ``rotation`` is nonzero,
    rotated clockwise about the rectangle's centre before translation. A zero
    rotation takes the shipped scale/translate chain unchanged, so an upright
    placement is byte-for-byte identical whether or not a rotation is specified.
    """
    x, y, width, height = rect
    overlay = _build_overlay_page(image_b64)
    transformation = pypdf.Transformation().scale(
        width / float(overlay.mediabox.width),
        height / float(overlay.mediabox.height),
    )

    if rotation:
        transformation = (
            transformation.translate(-width / 2.0, -height / 2.0)
            .rotate(-rotation)
            .translate(x + width / 2.0, y + height / 2.0)
        )
    else:
        transformation = transformation.translate(x, y)

    page.merge_transformed_page(overlay, transformation, over=over)


def stamp_pdf(document_b64: str, request: StampRequest) -> str:
    """Composite the request image onto a base64 PDF, returning base64 PDF.

    The carrier document is cloned whole — pages, text layer, and AcroForm
    dictionaries survive untouched — then the placement page receives the
    image via a scale/rotate/translate transformation merge. ``overlay`` draws
    the image over the page content; ``underlay`` draws it beneath, so carrier
    content stays legible above a letterhead. When ``request.date`` is supplied,
    the rendered date occupies the leading portion of the placement along its
    primary (un-rotated) axis and the signature the remainder, both sharing the
    placement's rotation. The page count is invariant.
    """
    placement = request.placement
    reader = pypdf.PdfReader(helpers.to_buffer(document_b64))
    writer = pypdf.PdfWriter()
    writer.clone_document_from_reader(reader)

    page = writer.pages[(placement.page or 1) - 1]
    rect = placement_to_pdf_rect(placement, float(page.mediabox.height))
    rotation = placement.rotation or 0
    over = request.layer != "underlay"

    if request.date:
        x, y, width, height = rect
        date_width = width * DATE_STRIP_FRACTION
        _merge_overlay(
            page,
            _render_date_image(request.date),
            (x, y, date_width, height),
            rotation,
            over,
        )
        _merge_overlay(
            page,
            request.image,
            (x + date_width, y, width - date_width, height),
            rotation,
            over,
        )
    else:
        _merge_overlay(page, request.image, rect, rotation, over)

    result = io.BytesIO()
    writer.write(result)

    return base64.b64encode(result.getvalue()).decode("utf-8")


# Per-format compositing backends. Only PDF is active at launch; ZPL is
# recognized by the sniffer but has no backend yet, so it is rejected.
_BACKENDS: typing.Dict[str, typing.Callable[[str, StampRequest], str]] = {
    "PDF": stamp_pdf,
}


def _nearest_paper_variant(width_pt: float, height_pt: float) -> str:
    """Return the standard paper variant nearest a mediabox, or ``*``.

    The point dimensions are converted to millimetres and compared on the
    orientation-independent (short, long) axes against ``STANDARD_PAPER_MM``,
    so a landscape page matches the same variant as its portrait form. The
    nearest standard within ``PAPER_VARIANT_TOLERANCE_MM`` on both axes wins;
    a page matching no standard is inconclusive and yields ``*``.
    """
    short_mm, long_mm = sorted(
        value * MM_PER_INCH / POINTS_PER_INCH for value in (width_pt, height_pt)
    )

    best: typing.Optional[typing.Tuple[str, float]] = None
    for name, dimensions in STANDARD_PAPER_MM.items():
        std_short, std_long = sorted(dimensions)
        distance = max(abs(short_mm - std_short), abs(long_mm - std_long))
        if distance <= PAPER_VARIANT_TOLERANCE_MM and (
            best is None or distance < best[1]
        ):
            best = (name, distance)

    return best[0] if best is not None else "*"


def _detect_paper_variant(document_b64: str, document_format: str) -> str:
    """Detect the paper-variant key segment from a document's first page.

    Only the PDF backend carries a mediabox to measure; any other format, and
    any first page that fails to parse, is inconclusive and yields ``*`` rather
    than raising, so paper detection never blocks a stamp.
    """
    if document_format != "PDF":
        return "*"

    try:
        page = pypdf.PdfReader(helpers.to_buffer(document_b64)).pages[0]
    except (pypdf.errors.PdfReadError, IndexError):
        return "*"

    return _nearest_paper_variant(
        float(page.mediabox.width), float(page.mediabox.height)
    )


def _registry_key(
    carrier: str,
    doc_type: str,
    document_format: str,
    paper: str,
) -> str:
    """Compose the four-part registry lookup key.

    The key is ``carrier/doc_type/format/paper`` with ``*`` for any missing
    segment. The ``doc_type`` segment is normalized through
    ``ShippingDocumentCategory`` so a category name, its value, and a PostNord
    ``printoutComposition`` string converge on one segment; an unrecognized
    value survives verbatim (``name_or_key`` returns the raw key) rather than
    crashing the lookup.
    """
    category = units.ShippingDocumentCategory.map(doc_type).name_or_key
    return "/".join(
        str(part or "*") for part in (carrier, category, document_format, paper)
    )


@attr.s(auto_attribs=True)
class StampSeed:
    """A measured registry seed: a placement plus a supersession revision.

    ``revision`` is a monotonic integer that a later re-measurement bumps to
    supersede an earlier seed, so a carrier re-rendering a form (which can
    drift a karrio-supplied anchor) is handled by shipping a higher revision
    rather than silently changing an anchor consumers may already rely on.
    """

    placement: StampPlacement = None
    revision: int = 0


# Measured PostNord CN22 anchor: a ~7.6 mm-wide x ~49 mm-tall vertical strip
# along the sideways "Date and Sender's signature" line, at x 53.3 mm, y 91.4 mm
# from the A4 page top-left (design.md "CN22 seed provenance").
#
# The 90-degree magnitude is measured, but the rotation DIRECTION (clockwise vs
# counter-clockwise) is provisional: the probe render used to measure it is not
# vendored, so Q10 stays open. The clockwise convention (6.1) is applied here
# pending a live-render confirmation; StampSeed.revision exists to bump the seed
# once the direction is confirmed.
_CN22_PLACEMENT: StampPlacement = StampPlacement(
    x=53.3, y=91.4, width=7.6, height=49.1, rotation=90
)

# revision 1: the first shipped measured seed. A confirmed Q10 direction (or any
# re-measurement) supersedes it with revision 2.
_SEED_REGISTRY: typing.Dict[str, StampSeed] = {
    "postnord/cn22/PDF/A4": StampSeed(placement=_CN22_PLACEMENT, revision=1),
}


def _default_registry(key: str) -> typing.Optional[StampPlacement]:
    """Resolve a measured seed's placement for a composed registry key.

    The full four-part ``carrier/doc_type/format/paper`` key is tried first; on
    a miss the paper segment is relaxed to ``*`` so a paper-agnostic seed still
    resolves for a page whose paper variant was detected. A concrete paper seed
    (for example the A4 CN22 anchor) never leaks across variants, because the
    fallback relaxes only to ``*`` and never between two concrete variants.
    """
    seed = _SEED_REGISTRY.get(key)
    if seed is None:
        carrier, doc_type, document_format, _ = key.split("/")
        seed = _SEED_REGISTRY.get("/".join((carrier, doc_type, document_format, "*")))

    return seed.placement if seed is not None else None


def stamp_document(
    document: models.ShippingDocument,
    image: str = None,
    placement: StampPlacement = None,
    layer: str = "overlay",
    carrier: str = None,
    doc_type: str = None,
    registry: RegistryLookup = None,
    date: str = None,
) -> models.ShippingDocument:
    """Composite a base64 PNG onto a returned carrier document.

    The document format is detected from its bytes and dispatched to the
    matching backend; the returned document preserves the input's format and
    shape, replacing only its ``base64`` content. A consumer-supplied
    ``placement`` is used directly with no registry lookup. When ``placement``
    is omitted, the registry hook is consulted and a miss raises an explicit
    error naming the missing key rather than guessing an anchor. A document
    whose format has no active backend (including PNG) is rejected explicitly.
    An optional pre-formatted ``date`` string is composited preceding the
    signature within the placement, at the placement's rotation.

    The utility composites pixels only: it stores nothing and makes no
    assertion about the legal validity or signature semantics of the result.
    """
    lookup = registry if registry is not None else _default_registry
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
        paper = _detect_paper_variant(document.base64, document_format)
        key = _registry_key(carrier, doc_type, document_format, paper)
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
        date=date,
    )
    stamped = _BACKENDS[document_format](document.base64, request)

    return attr.evolve(document, base64=stamped)
