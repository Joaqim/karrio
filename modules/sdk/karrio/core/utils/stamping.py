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

import karrio.core.utils.helpers as helpers

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
