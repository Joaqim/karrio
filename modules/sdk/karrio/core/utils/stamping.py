"""Composite a consumer-supplied raster image onto a returned carrier document.

The utility sniffs the document format and dispatches to the matching backend,
returning the document in the same format and shape it arrived in so consumers
never branch on document format themselves. It composites pixels only: it stores
nothing and asserts nothing about the legal validity or signature semantics of
the stamped content — that responsibility belongs to the consumer.
"""

import io
import re
import math
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

# ZPL ^FO and graphic operands are valid from 0 to 32000 dots, so any placement
# whose rotated origin or extent resolves outside that range is rejected rather
# than emitted as out-of-spec ZPL that printers interpret inconsistently.
ZPL_OPERAND_LIMIT: int = 32000

# A ZPL stored-object name: an optional device prefix, a 1-8 character name and
# an optional .GRF extension. Anything else could inject ZPL commands into the
# ~DY / ^XG fields the name is interpolated into.
ZPL_GRAPHIC_NAME_PATTERN: str = r"^(?:[A-Z]:)?[A-Z0-9_]{1,8}(?:\.GRF)?$"

# Fraction of the placement's primary (un-rotated) axis given to the date strip
# when a date is supplied; the signature takes the remainder.
DATE_STRIP_FRACTION: float = 0.5

# Glyph height of the rendered date as a fraction of the placement's short
# (pre-rotation height) axis, so the date stays physically constant across
# printer densities.
DATE_FONT_HEIGHT_FRACTION: float = 0.30

# Luminance bound below which a pixel binarizes to ink in the ZPL raster. A
# fixed threshold (not error diffusion) keeps anti-aliased glyph edges solid
# and faint signature strokes connected; error diffusion renders exactly
# those pixels as scattered speckle.
ZPL_INK_THRESHOLD: int = 200

# Resolution of the PDF backend's image-PDF overlay save. The date renders at
# this density so its scale into the placement rectangle stays uniform.
OVERLAY_DPI: int = 300

# Largest side, in pixels at OVERLAY_DPI, of the date raster the PDF backend
# renders (about 1.7 m), bounding the allocation a single request can cause.
MAX_DATE_RASTER_PX: int = 20000

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
    ``page`` index. ``width`` and ``height`` are the image's dimensions before
    rotation; a nonzero ``rotation`` (degrees clockwise) rotates the image and
    anchors the rotated extent's top-left corner at ``(x, y)``, so the anchor
    means the same thing rotated or upright. ``dpi`` is the ZPL target density
    and is ignored by the PDF backend.
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
    """One resolved image-compositing operation handed to a format backend.

    ``image`` is a base64-encoded PNG and ``placement`` the resolved anchor.
    ``layer`` is ``overlay`` for signatures (drawn over content) or
    ``underlay`` for letterheads (drawn beneath content, PDF only). ``date`` is
    an optional pre-formatted date string composited preceding the signature
    at the same rotation; the caller owns its format and locale.
    ``graphic_name`` opts the ZPL backend into the send-once-per-printer cache:
    the raster is downloaded once as a stored ``~DY`` object and recalled per
    label with ``^XG`` instead of inlining ``^GFA``; the PDF backend ignores it.
    """

    image: str = None
    placement: StampPlacement = None
    layer: str = "overlay"
    date: str = None
    graphic_name: str = None


@attr.s(auto_attribs=True)
class StampSeed:
    """Measured anchor data for one carrier document form.

    ``placement`` is the PDF coordinate anchor. ``keyword`` and
    ``keyword_placement`` are the ZPL anchor: the carrier form's keyword field,
    and the strip geometry (extent, rotation, ``dpi``) whose ``x``/``y`` are
    millimetre offsets from the located ``^FO`` origin. ``revision`` is a
    monotonic integer bumped when a re-measurement supersedes an earlier seed,
    so a carrier re-rendering a form is handled by shipping a higher revision
    rather than silently moving an anchor consumers may rely on.
    """

    placement: StampPlacement = None
    revision: int = 0
    keyword: str = None
    keyword_placement: StampPlacement = None


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


def dots_to_mm(value: float, dpi: int) -> float:
    """Convert a printer-dot measure at ``dpi`` to millimetres.

    The inverse of :func:`mm_to_dots`, kept float with no rounding: a located
    ``^FO`` origin converts to millimetres for anchor arithmetic and only
    rounds back to whole dots inside the ZPL backend.
    """
    return value * MM_PER_INCH / dpi


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


def _render_date_image(date: str, width: int, height: int) -> str:
    """Render a pre-formatted date string onto an opaque white base64 PNG.

    The caller owns the string's format and locale; the text renders verbatim
    with Pillow's built-in scalable font (no bundled asset), centered on a
    ``width`` x ``height`` white ground at its natural aspect. The glyph
    height is ``DATE_FONT_HEIGHT_FRACTION`` of ``height``, reduced
    proportionally when the text would overflow ``width``. The opaque ground —
    not an ink-trimmed transparency — is what keeps the image at the target
    aspect: the shared overlay path trims by the alpha bounding box, which
    would otherwise crop back to the ink and reintroduce the stretch.
    """
    font_size = max(int(round(height * DATE_FONT_HEIGHT_FRACTION)), 1)
    font = PIL.ImageFont.load_default(size=font_size)
    ruler = PIL.ImageDraw.Draw(PIL.Image.new("RGBA", (1, 1)))
    left, top, right, bottom = ruler.textbbox((0, 0), date, font=font)

    if right - left > width:
        font_size = max(int(font_size * width / (right - left)), 1)
        font = PIL.ImageFont.load_default(size=font_size)
        left, top, right, bottom = ruler.textbbox((0, 0), date, font=font)

    image = PIL.Image.new("RGB", (max(width, 1), max(height, 1)), (255, 255, 255))
    origin = (
        (width - (right - left)) // 2 - left,
        (height - (bottom - top)) // 2 - top,
    )
    PIL.ImageDraw.Draw(image).text(origin, date, fill=(0, 0, 0), font=font)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    return base64.b64encode(buffer.getvalue()).decode("utf-8")


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


def _rotate_clockwise(
    point: typing.Tuple[float, float], radians: float
) -> typing.Tuple[float, float]:
    """Rotate a PDF-space point clockwise about the origin.

    This matches pypdf's ``Transformation.rotate(-degrees)`` so the maths below
    locates exactly what the merged overlay draws.
    """
    px, py = point

    return (
        px * math.cos(radians) + py * math.sin(radians),
        -px * math.sin(radians) + py * math.cos(radians),
    )


def _rotated_bounds(
    width: float, height: float, rotation: float
) -> typing.Tuple[float, float, float, float]:
    """Return ``(min_x, max_x, min_y, max_y)`` of a rect rotated clockwise.

    The ``width`` x ``height`` rect is rotated by ``rotation`` degrees
    clockwise about its own origin corner (the PDF-space origin); the extrema
    over all four corners locate the rotated bounding box relative to that
    corner.
    """
    radians = math.radians(rotation)
    corners = [
        _rotate_clockwise(corner, radians)
        for corner in ((0.0, 0.0), (width, 0.0), (0.0, height), (width, height))
    ]

    return (
        min(cx for cx, _ in corners),
        max(cx for cx, _ in corners),
        min(cy for _, cy in corners),
        max(cy for _, cy in corners),
    )


def _merge_overlay(
    page: "pypdf.PageObject",
    image_b64: str,
    rect: typing.Tuple[float, float, float, float],
    rotation: float,
    over: bool,
    origin: typing.Tuple[float, float] = None,
) -> None:
    """Composite one base64 PNG into ``rect`` (PDF points) on ``page``.

    The image PDF is scaled to the rectangle. A zero rotation translates the
    scaled image to ``rect``'s bottom-left corner. A nonzero rotation rotates
    the scaled image clockwise about that corner and translates the corner to
    ``origin`` (bottom-left-origin PDF points), which the caller derives from
    the placement anchor.
    """
    x, y, width, height = rect
    overlay = _build_overlay_page(image_b64)
    transformation = pypdf.Transformation().scale(
        width / float(overlay.mediabox.width),
        height / float(overlay.mediabox.height),
    )

    if rotation:
        transformation = transformation.rotate(-rotation).translate(*origin)
    else:
        transformation = transformation.translate(x, y)

    page.merge_transformed_page(overlay, transformation, over=over)


def _validate_pdf_extent(
    anchor: typing.Tuple[float, float],
    bounds: typing.Tuple[float, float, float, float],
    page_width_pt: float,
    page_height_pt: float,
) -> None:
    """Reject a rotated extent that leaves the page mediabox.

    The drawn extent is the rotated bounding box ``bounds`` with its top-left
    corner on ``anchor``; an edge crossing the mediabox raises, naming the edge
    and the bound. Unrotated placements skip this check.
    """
    min_x, max_x, min_y, max_y = bounds
    left, top = anchor
    right = left + (max_x - min_x)
    bottom = top - (max_y - min_y)

    for edge, value in (("left", left), ("bottom", bottom)):
        if value < -0.5:
            raise ValueError(
                f"The rotated stamp extent's {edge} edge ({value:.1f} pt) starts "
                f"before the page mediabox origin of the page "
                f"({page_width_pt:.1f} x {page_height_pt:.1f} pt)"
            )

    for edge, value, bound in (
        ("right", right, page_width_pt),
        ("top", top, page_height_pt),
    ):
        if value > bound + 0.5:
            raise ValueError(
                f"The rotated stamp extent's {edge} edge ({value:.1f} pt) leaves "
                f"the page mediabox ({page_width_pt:.1f} x {page_height_pt:.1f} pt)"
            )


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


def _date_raster_size(width_pt: float, height_pt: float) -> typing.Tuple[int, int]:
    """Return the PDF date raster's pixel size, rejecting oversized strips."""
    size = tuple(
        max(int(round(value / POINTS_PER_INCH * OVERLAY_DPI)), 1)
        for value in (width_pt, height_pt)
    )
    if max(size) > MAX_DATE_RASTER_PX:
        raise ValueError(
            f"The date strip resolves to {size[0]} x {size[1]} px at "
            f"{OVERLAY_DPI} dpi, beyond the {MAX_DATE_RASTER_PX} px limit per side"
        )

    return size


def stamp_pdf(document_b64: str, request: StampRequest) -> str:
    """Composite the request image onto a base64 PDF, returning base64 PDF.

    The carrier document is cloned whole — pages, text layer, and AcroForm
    dictionaries survive untouched — then the placement page receives the
    image via a scale/rotate/translate transformation merge. A nonzero
    rotation rotates the image clockwise and anchors the rotated extent's
    bounding box's top-left corner at the placement's ``(x, y)``; a rotated
    extent crossing the mediabox is rejected. ``overlay`` draws the image over the page
    content; ``underlay`` draws it beneath, so carrier content stays legible
    above a letterhead. When ``request.date`` is supplied, the rendered date
    occupies the leading portion of the placement along its primary
    (un-rotated) axis and the signature the remainder; both are parts of the
    one rotated rectangle. The page count is invariant.
    """
    placement = request.placement
    _validate_anchor(placement)
    writer = _clone_pdf(document_b64)

    page = writer.pages[_validate_page(placement.page, len(writer.pages))]
    page_width_pt = float(page.mediabox.width)
    page_height_pt = float(page.mediabox.height)
    rect = placement_to_pdf_rect(placement, page_height_pt)
    rotation = placement.rotation or 0
    over = request.layer != "underlay"

    origin = None
    if rotation:
        x, y, width, height = rect
        anchor = (
            mm_to_points(placement.x),
            page_height_pt - mm_to_points(placement.y),
        )
        bounds = _rotated_bounds(width, height, rotation)
        _validate_pdf_extent(anchor, bounds, page_width_pt, page_height_pt)
        origin = (anchor[0] - bounds[0], anchor[1] - bounds[3])

    if request.date:
        x, y, width, height = rect
        date_width = width * DATE_STRIP_FRACTION
        date_size = _date_raster_size(date_width, height)
        signature_origin = None
        if rotation:
            offset = _rotate_clockwise((date_width, 0.0), math.radians(rotation))
            signature_origin = (origin[0] + offset[0], origin[1] + offset[1])
        _merge_overlay(
            page,
            _render_date_image(request.date, *date_size),
            (x, y, date_width, height),
            rotation,
            over,
            origin=origin,
        )
        _merge_overlay(
            page,
            request.image,
            (x + date_width, y, width - date_width, height),
            rotation,
            over,
            origin=signature_origin,
        )
    else:
        _merge_overlay(page, request.image, rect, rotation, over, origin=origin)

    result = io.BytesIO()
    writer.write(result)

    return base64.b64encode(result.getvalue()).decode("utf-8")


def _build_zpl_raster(request: StampRequest) -> "PIL.Image.Image":
    """Return the placement's 1-bpp ink-threshold raster for the ZPL backend.

    The signature (and, when supplied, the rendered date preceding it along the
    placement's primary axis per ``DATE_STRIP_FRACTION``) is composited onto one
    white canvas sized to the placement's dot extent, then binarized with the
    fixed ``ZPL_INK_THRESHOLD``. A threshold rather than error diffusion keeps
    the date's anti-aliased edges and the signature's faint strokes solid ink
    instead of scattered speckle; the signature resamples with LANCZOS to
    preserve stroke connectivity across the resize.
    """
    placement = request.placement
    width = max(mm_to_dots(placement.width, placement.dpi), 1)
    height = max(mm_to_dots(placement.height, placement.dpi), 1)

    canvas = PIL.Image.new("RGB", (width, height), (255, 255, 255))
    signature = _flatten_to_rgb(request.image)

    if request.date:
        date_width = max(int(round(width * DATE_STRIP_FRACTION)), 1)
        date_image = PIL.Image.open(
            helpers.to_buffer(_render_date_image(request.date, date_width, height))
        ).convert("RGB")
        canvas.paste(date_image, (0, 0))
        canvas.paste(
            signature.resize((max(width - date_width, 1), height), PIL.Image.LANCZOS),
            (date_width, 0),
        )
    else:
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


# A caret command token: two leading uppercase/alphanumeric characters then the
# parameters up to the next caret. ZPL field data cannot contain a raw caret
# (carets are hex-escaped via ^FH), so an ^FD token's parameters are exactly
# its field's text, spanning physical lines when the generator wrapped them.
_ZPL_COMMAND_PATTERN = re.compile(r"\^([A-Z][A-Z0-9])([^^]*)")


def _locate_zpl_field(stream: str, keyword: str) -> typing.Tuple[float, float]:
    """Return the ``^FO`` origin (dots) of the first field whose text matches.

    The scan walks command tokens rather than lines because carrier streams mix
    inline and newline-separated styles and an ``^FD`` block's text may span
    physical lines. Each ``^FO`` token updates the running origin with its first
    two operands parsed as floats (generators emit float operands such as
    ``^FO385,488.3333333333333``); the first ``^FD`` block whose text contains
    ``keyword`` resolves to the nearest preceding ``^FO``. Zero matches raise
    naming the keyword.
    """
    origin: typing.Optional[typing.Tuple[float, float]] = None

    for command in _ZPL_COMMAND_PATTERN.finditer(stream):
        name, parameters = command.group(1), command.group(2)

        if name == "FO":
            operands = parameters.split(",")
            try:
                origin = (float(operands[0]), float(operands[1]))
            except (IndexError, ValueError):
                continue
        elif name == "FD" and keyword in parameters:
            if origin is None:
                raise ValueError(
                    "The ZPL field matching the stamp keyword "
                    f"'{keyword}' has no preceding ^FO origin"
                )
            return origin

    raise ValueError(
        f"No ZPL field matching the stamp keyword '{keyword}' was found "
        "in the document"
    )


def _zpl_raster_extent(placement: StampPlacement) -> typing.Tuple[int, int]:
    """Return the rotated raster's dot extent without building the raster.

    Exact for right-angle rotations; for any other angle it is a lower bound
    (Pillow's expanded rotation rounds its bounding box outward), so a
    placement it rejects is one the built raster would also reject.
    """
    width = max(mm_to_dots(placement.width, placement.dpi), 1)
    height = max(mm_to_dots(placement.height, placement.dpi), 1)
    radians = math.radians(placement.rotation or 0)
    cosine, sine = abs(math.cos(radians)), abs(math.sin(radians))

    return (
        math.floor(width * cosine + height * sine),
        math.floor(width * sine + height * cosine),
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
    stream at the placement's ``^FO`` origin. A nonzero rotation rotates the
    raster clockwise and the rotated raster's top-left anchors at the
    placement's own ``^FO``. Any origin or extent operand resolving outside
    the ZPL range 0-32000 is rejected before the raster is built.
    ``request.date`` is composited into the same raster preceding the
    signature. ``request.graphic_name`` opts into the ``~DY`` / ``^XG``
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
    raster = _build_zpl_raster(request)
    rotation = placement.rotation or 0

    if rotation:
        raster = raster.rotate(-rotation, expand=True, fillcolor=1)

    _validate_zpl_operands(x_dots, y_dots, *raster.size)
    hexdata, total, bytes_per_row = _encode_grf(raster)

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
    any first page that fails to parse, is inconclusive and yields ``*``
    rather than raising, so paper detection never blocks a stamp.
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
    ``ShippingDocumentCategory`` so a category name and its value converge on
    one segment; an unrecognized value such as a carrier's own form name
    survives verbatim (``name_or_key`` returns the raw key) rather than
    crashing the lookup.
    """
    category = units.ShippingDocumentCategory.map(doc_type).name_or_key
    return "/".join(
        str(part or "*") for part in (carrier, category, document_format, paper)
    )


def _resolve_keyword_placement(
    document_b64: str, keyword: str, geometry: StampPlacement
) -> StampPlacement:
    """Return ``geometry`` with its position derived from the located field.

    Only the position comes from the carrier form: the matched field's ``^FO``
    origin converts from dots to millimetres at the geometry's ``dpi``, and the
    geometry's own ``x``/``y`` (``None`` meaning 0) add as millimetre offsets.
    Extent, rotation, and ``dpi`` stay geometry-owned, so the resolved
    placement meets the same anchor and operand validation as a
    consumer-supplied one.
    """
    stream = helpers.decode_bytes(base64.b64decode(document_b64))
    origin_x, origin_y = _locate_zpl_field(stream, keyword)

    return attr.evolve(
        geometry,
        x=dots_to_mm(origin_x, geometry.dpi) + (geometry.x or 0.0),
        y=dots_to_mm(origin_y, geometry.dpi) + (geometry.y or 0.0),
    )


def _carrier_seeds(carrier: str) -> typing.Dict[str, StampSeed]:
    """Return the ``stamp_seeds`` a carrier plugin declares in its metadata.

    Seeds are keyed ``doc_type/FORMAT/paper``; the carrier segment comes from
    the plugin id. Plugins load on demand, so a seed resolves without the
    caller importing the carrier's connector first.
    """
    if carrier == "*":
        return {}

    # Deferred: karrio.references imports karrio.lib, which imports this module.
    import karrio.references as references

    metadata = references.collect_providers_data().get(carrier)

    return (getattr(metadata, "stamp_seeds", None) or {}) if metadata else {}


def _resolve_seed(key: str) -> typing.Optional[StampSeed]:
    """Return the carrier seed for a composed key, paper segment relaxed.

    The full four-part ``carrier/doc_type/format/paper`` key is tried first; on
    a miss the paper segment is relaxed to ``*`` so a paper-agnostic seed still
    resolves for a page whose paper variant was detected. A concrete paper seed
    never leaks across variants, because the fallback relaxes only to ``*``
    and never between two concrete variants.
    """
    carrier, doc_type, document_format, paper = key.split("/")
    seeds = _carrier_seeds(carrier)
    seed = seeds.get("/".join((doc_type, document_format, paper)))
    if seed is None:
        seed = seeds.get("/".join((doc_type, document_format, "*")))

    return seed


def _default_registry(key: str) -> typing.Optional[StampPlacement]:
    """Resolve a carrier seed's placement for a composed registry key."""
    seed = _resolve_seed(key)

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
    graphic_name: str = None,
    keyword: str = None,
) -> models.ShippingDocument:
    """Composite a base64 PNG onto a returned carrier document.

    The document format is detected from its bytes and dispatched to the
    matching backend; the returned document preserves the input's format and
    shape, replacing only its ``base64`` content. The anchor resolves through
    an explicit chain: a fully anchored ``placement`` (both ``x`` and ``y``
    set) is used directly with no keyword or registry consultation, and a
    ``keyword`` supplied alongside one raises rather than silently ignoring
    either of the two contradictory anchors. A keyword with a geometry-only
    placement (``x``/``y`` left ``None``) takes its position from the ZPL
    field whose text contains the keyword and its extent and rotation from the
    placement; a keyword with no placement takes its geometry from the
    registry for the document's key — the injected ``registry`` lookup when
    one is supplied, else the carrier plugin's seed — and a miss raises naming
    what is missing. With neither placement nor keyword the registry is
    consulted: a PDF key resolves the seed's coordinate placement, a ZPL key
    whose seed carries a keyword resolves implicitly from the carrier form's
    own field, and a miss raises an explicit error naming the missing key
    rather than guessing an anchor. Keyword anchoring locates ZPL field
    origins only: a keyword supplied against another format is rejected
    explicitly. A document whose format has no active backend (including PNG)
    is rejected explicitly. An optional pre-formatted ``date`` string is
    composited preceding the signature within the placement, at the
    placement's rotation.

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

    if keyword and document_format != "ZPL":
        raise ValueError(
            f"Keyword anchoring is unsupported for the '{document_format}' "
            "format; a stamp keyword can only locate a field in a ZPL document"
        )

    fully_anchored = (
        placement is not None and placement.x is not None and placement.y is not None
    )

    if fully_anchored and keyword:
        raise ValueError(
            "A stamp keyword cannot be combined with a fully anchored "
            "placement (both x and y set); supply one anchor, not two"
        )

    if fully_anchored:
        resolved = placement
    elif keyword:
        geometry = placement
        if geometry is None:
            key = _registry_key(
                carrier,
                doc_type,
                document_format,
                _detect_paper_variant(document.base64, document_format),
            )
            if registry is None:
                seed = _resolve_seed(key)
                geometry = seed.keyword_placement if seed is not None else None
            else:
                # A supplied registry replaces the carrier seeds wherever they
                # would be consulted, so a custom lookup never silently falls
                # back to a plugin-declared anchor.
                geometry = registry(key)
            if geometry is None:
                raise ValueError(
                    "A stamp keyword was supplied without a placement and no "
                    f"registry seed with keyword geometry resolves for key "
                    f"'{key}'"
                )
        resolved = _resolve_keyword_placement(document.base64, keyword, geometry)
    else:
        paper = _detect_paper_variant(document.base64, document_format)
        key = _registry_key(carrier, doc_type, document_format, paper)
        resolved = None
        if registry is None:
            seed = _resolve_seed(key)
            if seed is not None:
                if document_format == "ZPL":
                    if seed.keyword and seed.keyword_placement is not None:
                        resolved = _resolve_keyword_placement(
                            document.base64, seed.keyword, seed.keyword_placement
                        )
                else:
                    resolved = seed.placement
        else:
            resolved = registry(key)
        if resolved is None:
            raise ValueError(
                "No stamp placement was supplied and no registry seed "
                f"resolves for key '{key}'"
            )

    request = StampRequest(
        image=image,
        placement=resolved,
        layer=layer,
        date=date,
        graphic_name=graphic_name,
    )
    stamped = _BACKENDS[document_format](document.base64, request)

    return attr.evolve(document, base64=stamped)
