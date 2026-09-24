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

# Fraction of the placement's primary (un-rotated) axis given to the date strip
# when a date is supplied; the signature takes the remainder. A simple even
# split until the group-4 CN22 seed measures a per-carrier partition (Q9). The
# even split also keeps the two sub-rects congruent, which is what makes the
# rotated sub-anchor offset (d*cos r, -d*sin r) tile exactly at every angle;
# an unequal partition must instead anchor each sub-rect on its own rotated
# bounding-box extrema.
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
    ``page`` index. ``width`` and ``height`` are the image's dimensions before
    rotation; a nonzero ``rotation`` (degrees clockwise) rotates the image and
    anchors the rotated extent's top-left corner at ``(x, y)``, so the anchor
    means the same thing rotated or upright. ``rotation`` defaults to ``0``
    (upright, byte-identical to the pre-rotation behavior). ``dpi`` is the ZPL
    target density and is ignored by the PDF backend.
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
    rotation; the caller owns its format and locale. ``graphic_name`` opts the
    ZPL backend into the send-once-per-printer cache: when set, the raster is
    downloaded once as a stored ``~DY`` object and recalled per label with
    ``^XG`` instead of inlining ``^GFA``; it is ignored by the PDF backend.
    ``keyword`` anchors the placement at the carrier ZPL field whose rendered
    text contains it; it is ZPL-only, is consumed entirely by placement
    resolution, and is never read by the compositing backends.
    """

    image: str = None
    placement: StampPlacement = None
    carrier: str = None
    doc_type: str = None
    layer: str = "overlay"
    date: str = None
    graphic_name: str = None
    keyword: str = None


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


def _rotated_corner_extents(
    width: float, height: float, rotation: float
) -> typing.Tuple[float, float]:
    """Return the (min-x, max-y) of a width x height rect rotated clockwise.

    The rect is rotated about its own corner (the PDF-space origin) by
    ``rotation`` degrees clockwise, matching pypdf's ``rotate(-rotation)``; the
    returned extrema locate the rotated bounding box relative to that corner so
    the caller can translate the box's top-left onto an anchor point.
    """
    radians = math.radians(rotation)
    corners = [
        (
            px * math.cos(radians) + py * math.sin(radians),
            -px * math.sin(radians) + py * math.cos(radians),
        )
        for px, py in ((width, 0.0), (0.0, height), (width, height))
    ]

    return min(cx for cx, _ in corners), max(cy for _, cy in corners)


def _merge_overlay(
    page: "pypdf.PageObject",
    image_b64: str,
    rect: typing.Tuple[float, float, float, float],
    rotation: float,
    over: bool,
    anchor: typing.Tuple[float, float] = None,
) -> None:
    """Composite one base64 PNG into ``rect`` (PDF points) on ``page``.

    The image PDF is scaled to the rectangle. A zero rotation translates the
    scaled image to ``rect``'s bottom-left corner, taking the shipped chain
    unchanged so an upright placement is byte-for-byte identical whether or not
    a rotation is specified. A nonzero rotation rotates the scaled image
    clockwise about its corner and translates the rotated extent's top-left to
    ``anchor`` (bottom-left-origin PDF points), which the caller derives from
    the placement so rotated sub-images tile along the rotated axis.
    """
    x, y, width, height = rect
    overlay = _build_overlay_page(image_b64)
    transformation = pypdf.Transformation().scale(
        width / float(overlay.mediabox.width),
        height / float(overlay.mediabox.height),
    )

    if rotation:
        min_x, max_y = _rotated_corner_extents(width, height, rotation)
        transformation = transformation.rotate(-rotation).translate(
            anchor[0] - min_x, anchor[1] - max_y
        )
    else:
        transformation = transformation.translate(x, y)

    page.merge_transformed_page(overlay, transformation, over=over)


def _validate_pdf_extent(
    placement: StampPlacement,
    anchor: typing.Tuple[float, float],
    page_width_pt: float,
    page_height_pt: float,
) -> None:
    """Reject a rotated extent that leaves the page mediabox.

    The rotated bounding box is measured around the anchor the same way
    ``_merge_overlay`` positions it; an edge crossing the mediabox raises,
    naming the edge and the bound. Unrotated placements skip this check and
    keep the shipped permissive behavior.
    """
    radians = math.radians(placement.rotation or 0)
    corners = [
        (
            anchor[0] + px * math.cos(radians) + py * math.sin(radians),
            anchor[1] - px * math.sin(radians) + py * math.cos(radians),
        )
        for px, py in (
            (0.0, 0.0),
            (mm_to_points(placement.width), 0.0),
            (0.0, mm_to_points(placement.height)),
            (mm_to_points(placement.width), mm_to_points(placement.height)),
        )
    ]
    for edge, value in (
        ("left", min(cx for cx, _ in corners)),
        ("bottom", min(cy for _, cy in corners)),
    ):
        if value < -0.5:
            raise ValueError(
                f"The rotated stamp extent's {edge} edge ({value:.1f} pt) starts "
                f"before the page mediabox origin of the page "
                f"({page_width_pt:.1f} x {page_height_pt:.1f} pt)"
            )

    for edge, value, bound in (
        ("right", max(cx for cx, _ in corners), page_width_pt),
        ("top", max(cy for _, cy in corners), page_height_pt),
    ):
        if value > bound + 0.5:
            raise ValueError(
                f"The rotated stamp extent's {edge} edge ({value:.1f} pt) leaves "
                f"the page mediabox ({page_width_pt:.1f} x {page_height_pt:.1f} pt)"
            )


def stamp_pdf(document_b64: str, request: StampRequest) -> str:
    """Composite the request image onto a base64 PDF, returning base64 PDF.

    The carrier document is cloned whole — pages, text layer, and AcroForm
    dictionaries survive untouched — then the placement page receives the
    image via a scale/rotate/translate transformation merge. A nonzero
    rotation rotates the image clockwise and anchors the rotated extent's
    top-left corner at the placement's ``(x, y)``; a rotated extent crossing
    the mediabox is rejected. ``overlay`` draws the image over the page
    content; ``underlay`` draws it beneath, so carrier content stays legible
    above a letterhead. When ``request.date`` is supplied, the rendered date
    occupies the leading portion of the placement along its primary
    (un-rotated) axis and the signature the remainder, both sharing the
    placement's rotation. The page count is invariant.
    """
    placement = request.placement
    _validate_anchor(placement)
    reader = pypdf.PdfReader(helpers.to_buffer(document_b64))
    writer = pypdf.PdfWriter()
    writer.clone_document_from_reader(reader)

    page = writer.pages[(placement.page or 1) - 1]
    page_width_pt = float(page.mediabox.width)
    page_height_pt = float(page.mediabox.height)
    rect = placement_to_pdf_rect(placement, page_height_pt)
    rotation = placement.rotation or 0
    over = request.layer != "underlay"

    anchor = None
    if rotation:
        anchor = (
            mm_to_points(placement.x),
            page_height_pt - mm_to_points(placement.y),
        )
        _validate_pdf_extent(placement, anchor, page_width_pt, page_height_pt)

    if request.date:
        x, y, width, height = rect
        date_width = width * DATE_STRIP_FRACTION
        date_anchor = signature_anchor = None
        if rotation:
            radians = math.radians(rotation)
            offset = (
                date_width * math.cos(radians),
                -date_width * math.sin(radians),
            )
            date_anchor = anchor
            signature_anchor = (anchor[0] + offset[0], anchor[1] + offset[1])
        _merge_overlay(
            page,
            _render_date_image(request.date),
            (x, y, date_width, height),
            rotation,
            over,
            anchor=date_anchor,
        )
        _merge_overlay(
            page,
            request.image,
            (x + date_width, y, width - date_width, height),
            rotation,
            over,
            anchor=signature_anchor,
        )
    else:
        _merge_overlay(page, request.image, rect, rotation, over, anchor=anchor)

    result = io.BytesIO()
    writer.write(result)

    return base64.b64encode(result.getvalue()).decode("utf-8")


def _flatten_to_rgb(image_b64: str) -> "PIL.Image.Image":
    """Return a base64 PNG trimmed and white-flattened to an opaque RGB image.

    This mirrors the PDF backend's Q6 flatten (auto-trim to the non-transparent
    bounding box, then alpha-composite onto opaque white) but stops at a Pillow
    image rather than an image PDF, so the ZPL backend can resize and dither it
    into a 1-bpp raster.
    """
    source = PIL.Image.open(helpers.to_buffer(image_b64)).convert("RGBA")

    bounds = source.getchannel("A").getbbox()
    trimmed = source.crop(bounds) if bounds is not None else source

    backdrop = PIL.Image.new("RGBA", trimmed.size, (255, 255, 255, 255))

    return PIL.Image.alpha_composite(backdrop, trimmed).convert("RGB")


def _build_zpl_raster(request: StampRequest) -> "PIL.Image.Image":
    """Return the placement's 1-bpp Floyd-Steinberg raster for the ZPL backend.

    The signature (and, when supplied, the rendered date preceding it along the
    placement's primary axis per ``DATE_STRIP_FRACTION``) is composited onto one
    white canvas sized to the placement's dot extent, then converted to 1-bpp
    with a single Floyd-Steinberg dither. Building the whole raster before the
    one dither keeps the date and signature on a shared halftone grid.
    """
    placement = request.placement
    width = max(mm_to_dots(placement.width, placement.dpi), 1)
    height = max(mm_to_dots(placement.height, placement.dpi), 1)

    canvas = PIL.Image.new("RGB", (width, height), (255, 255, 255))
    signature = _flatten_to_rgb(request.image)

    if request.date:
        date_width = max(int(round(width * DATE_STRIP_FRACTION)), 1)
        date_image = _flatten_to_rgb(_render_date_image(request.date))
        canvas.paste(date_image.resize((date_width, height)), (0, 0))
        canvas.paste(
            signature.resize((max(width - date_width, 1), height)),
            (date_width, 0),
        )
    else:
        canvas.paste(signature.resize((width, height)), (0, 0))

    return canvas.convert("1", dither=PIL.Image.Dither.FLOYDSTEINBERG)


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


def stamp_zpl(document_b64: str, request: StampRequest) -> str:
    """Composite the request image onto a base64 ZPL stream, returning base64.

    The image is flattened, resized to the placement's dot extent, dithered to a
    1-bpp raster, and encoded as a GRF graphic spliced over the carrier field
    stream at the placement's ``^FO`` origin. A nonzero rotation rotates the
    raster clockwise and the rotated raster's top-left anchors at the
    placement's own ``^FO``. Any origin or extent operand resolving outside
    the ZPL range 0-32000 is rejected. ``request.date`` is composited into the
    same raster preceding the signature. ``request.graphic_name`` opts into the
    ``~DY`` / ``^XG`` send-once cache. ZPL has no z-order, so an ``underlay``
    layer (letterhead) is out of practical scope and is rejected.
    """
    if request.layer == "underlay":
        raise ValueError(
            "ZPL stamping supports only the overlay layer; a ZPL underlay "
            "(letterhead) is out of practical scope because ZPL has no z-order"
        )

    placement = request.placement
    _validate_anchor(placement)
    stream = helpers.decode_bytes(base64.b64decode(document_b64))
    raster = _build_zpl_raster(request)
    rotation = placement.rotation or 0

    if rotation:
        raster = raster.rotate(-rotation, expand=True, fillcolor=1)

    x_dots = mm_to_dots(placement.x, placement.dpi)
    y_dots = mm_to_dots(placement.y, placement.dpi)
    rotated_width, rotated_height = raster.size
    for edge, operand in (
        ("x origin", x_dots),
        ("y origin", y_dots),
        ("x extent", x_dots + rotated_width),
        ("y extent", y_dots + rotated_height),
    ):
        if not 0 <= operand <= ZPL_OPERAND_LIMIT:
            raise ValueError(
                f"The stamp's {edge} resolves to {operand} dots, outside the "
                f"ZPL ^FO operand range 0-{ZPL_OPERAND_LIMIT}"
            )

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


# Per-format compositing backends. PDF and ZPL are active; PNG is recognized by
# the sniffer but has no backend, so it is rejected by the dispatcher.
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


@attr.s(auto_attribs=True)
class StampSeed:
    """A measured registry seed: anchor data plus a supersession revision.

    ``placement`` is the PDF coordinate anchor. ``keyword`` and
    ``keyword_placement`` are the ZPL currency: the carrier form's keyword
    field, and the strip geometry (extent, rotation, ``dpi``) whose ``x``/``y``
    are millimetre offsets from the located ``^FO`` origin. ``revision`` is a
    monotonic integer that a later re-measurement bumps to supersede an
    earlier seed, so a carrier re-rendering a form (which can drift a
    karrio-supplied anchor) is handled by shipping a higher revision rather
    than silently changing an anchor consumers may already rely on.
    """

    placement: StampPlacement = None
    revision: int = 0
    keyword: str = None
    keyword_placement: StampPlacement = None


# Measured PostNord CN22 anchor: a ~7.6 mm-wide x ~49 mm-tall vertical strip
# along the sideways "Date and Sender's signature" line, whose rotated extent's
# top-left sits at x 32.55 mm, y 112.15 mm from the A4 page top-left (design.md
# "CN22 seed provenance").
#
# The rotation direction is confirmed by the vendored ZPL form
# (tests/core/fixtures/postnord_cn22.zpl): its field stream runs under ^FWR with
# glyph-up = page +x -- it reads with the head tilted right, matching the
# clockwise convention -- so rotation=90 aligns the signature with the form.
#
# Known defect (measured 2026-09-24, PRDs/KEYWORD_ANCHORED_STAMPING.md
# appendix B): revision 2's extent axes are swapped relative to the archived
# probe, so this placement renders a horizontal 49.1x7.6 mm strip starting
# ~20 mm off the label's left edge. The PDF re-measurement (vertical 7.62x49.11
# at page 53.34,91.44, rotation 0, revision 3) is a follow-up change; the ZPL
# keyword anchor below already pins the measured strip.
_CN22_PLACEMENT: StampPlacement = StampPlacement(
    x=32.55, y=112.15, width=7.6, height=49.1, rotation=90
)

# Measured PostNord CN22 ZPL keyword anchor: the located "Date and Sender's
# signature" origin (^FO20,35) plus this offset resolves to ^FO7,303, and the
# pre-rotation 49.1x7.6 mm extent at 203 dpi rotates to a 61x392-dot vertical
# strip (x 7..68, y 303..695) over the signature column with its bottom edge
# on the form box's bottom rule (^GB820,680 ends at y 695). Measured by
# mapping the CN22 PDF's /Form1 XObject onto the label frame -- eight
# separator columns and the rule span agree with the ZPL form at sub-dot
# precision -- and anchoring the archived probe strip (page x 53.34..60.96,
# y 91.44..140.55 mm) onto the keyword field; arithmetic in
# PRDs/KEYWORD_ANCHORED_STAMPING.md appendix B.
_CN22_KEYWORD_PLACEMENT: StampPlacement = StampPlacement(
    x=-1.673, y=33.529, width=49.1, height=7.6, rotation=90, dpi=203
)

# revision 2: re-expresses revision 1's identical physical strip under
# corner-anchored rotation semantics -- (x + (w-h)/2, y + (h-w)/2) from the
# centre-pivot anchor (53.3, 91.4). The keyword fields are additive anchor
# data, not a re-measurement of the PDF placement, so the revision stays 2.
_CN22_SEED: StampSeed = StampSeed(
    placement=_CN22_PLACEMENT,
    revision=2,
    keyword="Date and Sender's signature",
    keyword_placement=_CN22_KEYWORD_PLACEMENT,
)

_SEED_REGISTRY: typing.Dict[str, StampSeed] = {
    "postnord/cn22/PDF/A4": _CN22_SEED,
    # The same seed object reached by a ZPL document's natural key, so one
    # entry anchors both formats of the CN22: the format-to-currency choice
    # (PDF resolves `placement`, ZPL resolves `keyword` + `keyword_placement`)
    # happens at resolution, not here.
    "postnord/cn22/ZPL/*": _CN22_SEED,
}


def _resolve_seed(key: str) -> typing.Optional[StampSeed]:
    """Return the registry seed for a composed key, paper segment relaxed.

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

    return seed


def _default_registry(key: str) -> typing.Optional[StampPlacement]:
    """Resolve a measured seed's placement for a composed registry key."""
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
    one is supplied, else the built-in seed — and a miss raises naming what
    is missing. With neither placement nor keyword the registry is consulted: a
    PDF key resolves the seed's coordinate placement, a ZPL key whose seed
    carries a keyword resolves implicitly from the carrier form's own field,
    and a miss raises an explicit error naming the missing key rather than
    guessing an anchor. Keyword anchoring locates ZPL field origins only: a
    keyword supplied against another format is rejected explicitly. A document
    whose format has no active backend (including PNG) is rejected explicitly.
    An optional pre-formatted ``date`` string is composited preceding the
    signature within the placement, at the placement's rotation.

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
                # Injection owns resolution: a supplied registry replaces the
                # built-in seeds wherever they would be consulted, so a custom
                # lookup never silently falls back to a shipped anchor.
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
        carrier=carrier,
        doc_type=doc_type,
        layer=layer,
        date=date,
        graphic_name=graphic_name,
        keyword=keyword,
    )
    stamped = _BACKENDS[document_format](document.base64, request)

    return attr.evolve(document, base64=stamped)
