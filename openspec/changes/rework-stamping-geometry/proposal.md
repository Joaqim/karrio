# Proposal

## Why

A consumer stamped a 400 x 140 px signature with the placement `{"page": 2, "x": 440, "y": 400, "width": 400, "height": 140}` onto a ZPL label rendered at 203 dpi.
The values were meant as printer dots, but placement units are always millimetres, so the utility emitted a 3200 x 1119-dot `^GFA` (0.9 MB of ZPL, 1.2 MB of base64, over 2 MB at 300 dpi) far outside the label, and raised no error.
The same placement on a PDF lands off the page, also silently.

The probes behind this change found the image preparation sound: the image is converted to RGBA from any mode, trimmed to its alpha bounding box, flattened onto white, binarized at the fixed luminance threshold 200 without dithering, and emitted as uncompressed 1-bpp `^GFA`.
The `document` field is the base document and `image` the overlay; a swap fails clearly.
The geometry around that raster is what misleads consumers:

- placements accept millimetres only, with no way to state points or pixels;
- the image is stretched to fill the box, distorting its aspect ratio;
- ZPL ignores `placement.page`, and a coordinate placement always splices before the last `^XZ`;
- `stamp_document(page=)` raises for ZPL instead of selecting a format;
- no page or label bounds check exists beyond the 0-32000 dot operand range and the rotated-PDF mediabox check;
- ZPL graphics are always uncompressed hex;
- when PDF pages share one `/Resources` object, stamping page 2 also adds the image to page 1's resources;
- paper detection reads page 1 only;
- classification knows only the `cn22` declaration kind;
- the REST endpoint requires `x`/`y` and has no keyword field, so keyword stamping is unreachable over REST.

## What Changes

- `StampPlacement` and the REST placement gain `unit`: `mm` (default, current behaviour), `pt` (1/72 in) or `px`, where `px` means printer dots at `dpi` for ZPL and pixels of the PDF page rendered at `dpi` for PDF; placements are normalized to millimetres internally, so seeds and registry values stay in millimetres.
- The image is fitted inside its box with its aspect ratio preserved, left-aligned and vertically centred, while the box itself keeps its size; with a date strip the fit applies inside the signature's share.
- On ZPL, `placement.page` selects the Nth `^XA`...`^XZ` format, one-based like PDF pages; the default page 1 is now the first format rather than the last, and an out-of-range page raises.
  `stamp_document(page=)` selects the format for ZPL instead of raising.
- A placement whose resolved rectangle leaves the PDF mediabox, or the ZPL label (`^LL` length, and `^PW` width when present), raises `ValueError`, which the endpoint maps to 400; the check applies to the final resolved rectangle only, never to keyword-relative offsets.
- An opt-in `compression="z64"` emits ZPL graphics as `^GFA,total,total,bpr,:Z64:<base64(zlib)>:<crc16>`; the `~DY` download of the `graphic_name` cache carries the same Z64 data; the default stays byte-identical uncompressed hex.
- Without a keyword, `stamp_document` raises for partial placement geometry, a placement with only one of `x`/`y` or with neither, instead of silently falling back to the registry; with a keyword, the placement's `x` and `y` are optional offsets from the located anchor, each defaulting to 0.
- `karrio.lib` exports the accepted units, compressions, declaration kinds and combined document types.
- The stamped PDF page gets its own resources copy, so shared `/Resources` no longer leak the stamp to other pages.
- The paper variant used in the registry key is detected from the stamped page rather than page 1.
- Classification gains a carrier-neutral `cn23` declaration kind, with the combined type `label_cn23`; consumers add their own `label_cn23` seeds.
- The REST endpoint accepts `unit`, a top-level `keyword` and `compression`, and `x`/`y` become optional, acting as offsets beside a keyword.

Behaviour changes for existing callers: a ZPL coordinate placement without an explicit page now stamps the first format instead of the last; images whose aspect differs from their box are no longer stretched; unrotated PDF placements extending past the mediabox and ZPL placements extending past `^LL`/`^PW` now raise; partial placements without a keyword that previously fell back to the registry now raise; a keyword beside a placement carrying `x` and `y` now offsets the keyword instead of raising.

Out of scope: a byte cap on the emitted graphic or the request payload (kept as an open question in design.md), `^LH` and `^FT` offsets in bounds or keyword location, the consumers' `label_cn23` seeds, and re-detecting the paper on a seed's own page after the lookup (a follow-up in design.md).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `documents/stamping`: placement units, aspect-preserving fit, ZPL format selection by page, page and label bounds, Z64 graphic compression, per-page resources and paper detection, the `cn23` declaration kind, and the REST placement fields.

## Impact

- `modules/sdk/karrio/core/utils/stamping.py`, `modules/sdk/karrio/lib.py` re-exports, and the stamping test modules under `modules/sdk/tests/core/`, with fixtures built at test time in `stamping_helpers.py`; no captured carrier document is vendored.
- `modules/documents/karrio/server/documents/serializers/base.py`, `views/stamping.py` and `tests/test_stamping.py`.
- `PRDs/DOCUMENT_STAMPING.md` records the decisions on the upstream-bound branch `feat-document-stamping`, which carries the implementation; no new branch, generated file, migration or dependency (zlib and base64 are standard library).
