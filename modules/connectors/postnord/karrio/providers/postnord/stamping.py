"""PostNord document-stamping seeds, declared through the plugin metadata."""

import karrio.lib as lib

# The CN22 "Date and Sender's signature" strip. On the A4 PDF it spans page
# x 53.34-60.96 mm and y 91.44-140.55 mm, encoded as a pre-rotation
# 49.11 x 7.62 mm extent turned 90 degrees clockwise so the stamp reads along
# the form's sideways (^FWR) field stream. On the ZPL form the same strip is an
# offset from the keyword field's ^FO20,35 origin and resolves to ^FO7,303, a
# 61 x 392-dot raster whose bottom edge sits on the form box's bottom rule.
# The two encodings were cross-checked by mapping the PDF form XObject onto
# the ZPL label frame. Revision 3 supersedes an earlier centre-pivot
# measurement whose algebraic conversion swapped the rendered axes.
CN22_SEED = lib.StampSeed(
    placement=lib.StampPlacement(
        x=53.34, y=91.44, width=49.11, height=7.62, rotation=90
    ),
    revision=3,
    keyword="Date and Sender's signature",
    keyword_placement=lib.StampPlacement(
        x=-1.673, y=33.529, width=49.1, height=7.6, rotation=90, dpi=203
    ),
)

# The combined label + CN22 printout carries the CN22 keyword once, either in
# the rotated (^FWR) letter CN22 sharing the label's ZPL format or, for the
# International Parcel (91), in an upright (^FWN) CN22 format of its own.
# Both ZPL layouts anchor on the keyword in its reading frame, from where the
# text starts on its glyph-top edge: the strip starts 33.529 mm along the text
# and 3.4245 mm before that edge, and extends 49.1 x 7.6 mm along the text. On
# the rotated form that is the lone CN22's ^FO7,303 strip; on the upright V2
# form it resolves to ^FO293,758, clear of the keyword text (whose ink ends at
# x 229 in a Labelary render), 12 dots below the certification text's ink and
# 15 dots above the box's bottom rule, within the format's ^LL840.
# PostNord's PDF printout comes in two layouts: one A4 page with the
# CN22 turned beside the label (the by-id capture) and, in the booking
# captures, the label on page 1 and an upright CN22 on page 2. The PDF
# anchors on the keyword, in its reading frame: the strip starts 33.53 mm along
# the text from the keyword run's origin and 5.32 mm above its baseline, and
# extends 49.11 x 7.62 mm along the text. That is the signature strip measured
# on the single-page layout (label x 6.63-67.53, y 302.97-695.44 dots), edge
# aligned with the CN22 box's right and bottom rules. The upright form's box is
# wider and deeper, so there the same strip sits inside the free signature area
# (1.1 mm below the certification text, 2.2 mm above the bottom rule, 18.1 mm
# short of the right rule) rather than on its rules. ``placement`` keeps the
# single-page layout's coordinates. Revision 2 superseded the coordinate-only
# revision 1, which stamped the two-page layout's CN22 across its
# explanation, contents and tariff rows; revision 3 supersedes the label-axis
# ZPL offset of revision 2, which placed the upright CN22's stamp beyond its
# format's ^LL840.
LABEL_CN22_SEED = lib.StampSeed(
    placement=lib.StampPlacement(
        x=53.34, y=91.44, width=49.11, height=7.62, rotation=90
    ),
    revision=3,
    keyword=CN22_SEED.keyword,
    zpl_keyword_frame_placement=lib.StampPlacement(
        x=33.529, y=-3.4245, width=49.1, height=7.6, rotation=0, dpi=203
    ),
    pdf_keyword_placement=lib.StampPlacement(
        x=33.53, y=-5.32, width=49.11, height=7.62, rotation=0
    ),
)

# A ZPL key resolves the keyword anchor; a PDF key resolves the keyword anchor
# when the seed carries PDF keyword geometry and the coordinate placement
# otherwise, so the lone CN22 PDF stays coordinate-anchored.
STAMP_SEEDS = {
    "cn22/PDF/A4": CN22_SEED,
    "cn22/ZPL/*": CN22_SEED,
    "label_cn22/PDF/A4": LABEL_CN22_SEED,
    "label_cn22/ZPL/*": LABEL_CN22_SEED,
}

# PostNord composes the CN22 and the label into one printout. The export
# letter is a single ZPL format (one ^XZ), and in PDF either one A4 page or, in
# the sandbox booking capture, a label page followed by a CN22 page. The
# International Parcel (91) is two ZPL formats, a parcel label then an upright
# CN22, and in PDF a label page followed by a CN22 page. The sections are told
# apart by PostNord's own ^FX field comments in ZPL and by page text in PDF;
# each template's label markers occur in no CN22 section of any capture.
DOCUMENT_SECTIONS = {
    "ZPL": {
        "cn22": lib.AnyOf(
            "^FX CUSTOMS_CN22_ROTATED^FS",
            "^FX CUSTOMS_CN22_V2^FS",
        ),
        "label": lib.AnyOf(
            "^FX SE_INTERNATIONAL_LETTER_LABEL^FS",
            "^FX NORDIC_SHIPPING_LABEL^FS",
        ),
    },
    "PDF": {
        "cn22": ("CUSTOMS DECLARATION", "CN22"),
        "label": lib.AnyOf(
            ("Brev utrikes", "Parcel ID"),
            ("PostNord Tracked Letter", "Item-ID"),
            ("International Parcel", "Item-ID"),
        ),
    },
}
