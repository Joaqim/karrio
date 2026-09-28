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

# The combined label + CN22 printout carries the CN22 section unchanged, with
# the keyword occurring once, so its ZPL anchor is the lone CN22's keyword and
# offset.
LABEL_CN22_SEED = lib.StampSeed(
    keyword=CN22_SEED.keyword,
    keyword_placement=CN22_SEED.keyword_placement,
)

# One seed serves both formats: a PDF key resolves the coordinate placement and
# a ZPL key the keyword anchor.
STAMP_SEEDS = {
    "cn22/PDF/A4": CN22_SEED,
    "cn22/ZPL/*": CN22_SEED,
    "label_cn22/ZPL/*": LABEL_CN22_SEED,
}

# PostNord composes the CN22 and the letter label into one printout: a single
# ZPL format (one ^XZ) and a single A4 PDF page. The sections are told apart by
# PostNord's own ^FX field comments in ZPL and by page text in PDF, where the
# label markers occur only in the label section of the live captures.
DOCUMENT_SECTIONS = {
    "ZPL": {
        "cn22": "^FX CUSTOMS_CN22_ROTATED^FS",
        "label": "^FX SE_INTERNATIONAL_LETTER_LABEL^FS",
    },
    "PDF": {
        "cn22": ("CUSTOMS DECLARATION", "CN22"),
        "label": ("Brev utrikes", "Parcel ID"),
    },
}
