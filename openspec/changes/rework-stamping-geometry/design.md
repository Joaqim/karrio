# Design

## Context

See proposal.md for motivation and the spec delta for required behaviour.
The code lives in `modules/sdk/karrio/core/utils/stamping.py` on `feat-document-stamping`, and the endpoint in `modules/documents/karrio/server/documents/`.
`stamp_document` resolves an anchor (placement, then keyword, then seed) into a `StampRequest` and dispatches to `stamp_pdf` or `stamp_zpl`.
`_splice_zpl_field` splits the stream on `^XZ` alone, so a header `^XA` inside a format, and `^FX` text between formats or after the last one, survive byte-identically; `StampRequest.zpl_format` carries the zero-based format a keyword matched, and `None` means the last format.
`_merge_overlay` scales the image PDF to the box with independent x and y factors, and `_build_zpl_raster` resizes the signature to the box, so both stretch.
`_detect_paper_variant` reads `pages[0]`, and `DECLARATION_KIND` is the single constant `cn22`.

## Goals / Non-Goals

Goals: let consumers state placements in the units they measured in, never distort the image, make ZPL page selection mean what it means for PDF, fail loudly on placements outside the page or label, shrink large ZPL graphics on request, and close the shared-resources and paper-detection defects.

Non-goals: a size cap, `^LH`/`^FT`/`^CC` handling, mediabox origins other than `(0, 0)` (the code already measures from the mediabox's width and height only), and carrier seeds for `cn23`.

## Decisions

### Units are normalized to millimetres at each entry point

`StampPlacement.unit` takes `mm` (default), `pt` or `px`.
`_normalize_units(placement)` converts `x`, `y`, `width` and `height` to millimetres (`pt`: `v * 25.4 / 72`; `px`: `v * 25.4 / dpi`), leaves `None` offsets, `page`, `rotation` and `dpi` untouched, and returns the placement with `unit="mm"`, so it is idempotent.
It runs at the top of `stamp_document`, `stamp_pdf` and `stamp_zpl`, so direct backend callers also honour the unit, and on a consumer geometry-only placement before keyword resolution, so keyword offsets may be given in any unit.
Seeds and injected registry results are normalized too, which is a no-op for the millimetre values they carry today.
An unknown unit raises `ValueError` naming `StampPlacement.unit`.

`px` uses one formula for both backends, so `dpi` now matters to the PDF backend when `unit="px"`: a consumer measuring on a 150 dpi page render passes `dpi=150`.
For ZPL, `px` at the placement's own `dpi` round-trips exactly through `mm_to_dots` (`round(v * 25.4 / dpi / 25.4 * dpi) == v` for integer `v`), so the user's 400 x 140 placement becomes a 400 x 140-dot box.
A string enum (`StampUnit`) was rejected in favour of plain strings validated against a tuple, matching how `layer` is handled.

### The image fits its box; the box keeps its size

```
 box (pre-rotation frame, w x h)          with a date strip
 +-------------------------------+        +-----------+-------------------+
 |                               |        |           |                   |
 |#########                      |        |  date     |#######            |
 |#########  fitted image        |        |  (D5/D6)  |#######  signature |
 |#########  s = min(w/iw, h/ih) |        |           |#######  share     |
 |                               |        |           |                   |
 +-------------------------------+        +-----------+-------------------+
 left-aligned, centred on the short axis   fit applies inside the share
```

The scale is `s = min(bw / iw, bh / ih)` for the trimmed image `(iw, ih)` and the signature box `(bw, bh)`, which is the whole box, or the signature's share when a date is supplied.
The fitted image sits at offset `(0, (bh - ih * s) / 2)` from the share's top-left, in the box's own pre-rotation frame, so the rotation carries the offset with it.
On PDF, `_merge_overlay` uses one scale factor for both axes and composes the offset before the rotation; the drawn rectangle for the bounds check stays the whole box.
On ZPL, the canvas stays box-sized, the signature is resized with LANCZOS to `(max(round(iw * s), 1), max(round(ih * s), 1))`, clamped to the share, and pasted at the rounded offset, so the `^GFA` dimensions are unchanged.
Left alignment was chosen over centring because a signature reads from the start of its line and a date strip already precedes it.

### ZPL page selects a format

The formats of a stream are the segments ending at each `^XZ`, in order, plus a trailing segment after the last `^XZ` only when it contains `^XA` (an unterminated format); a trailing segment of `^FX` text or whitespace is not a format.
`placement.page` is the one-based index into that list, default 1, so a coordinate placement now stamps the first format.
An out-of-range page raises `ValueError` naming `StampPlacement.page` and the format count.
Splicing is unchanged otherwise: the field goes before the selected format's `^XZ`, and an unterminated format is closed after the appended field.

`StampRequest.zpl_format` is retired; the resolved placement's `page` carries the format for both backends.
A ZPL keyword sets the resolved page to the matched field's format.
`stamp_document(page=)` against ZPL no longer raises: like PDF, it restricts the keyword search to that format and applies a registry-resolved placement to it, and combined with a fully anchored placement it still raises.

### Bounds apply to the final rectangle only

After resolution, rotation and unit normalization, the drawn box `(x, y)` to `(x + w|cos r| + h|sin r|, y + w|sin r| + h|cos r|)` must lie within the target.
For PDF, the target is the page mediabox, for every rotation, with a tolerance of 1e-6 pt for floating-point rounding, replacing the rotated-only check.
For ZPL, the target is the label in dots: the length is the latest `^LL` operand at or before the selected format's end, and the width the latest `^PW` operand there, since both persist on the printer across formats; without `^PW` only the length is checked, and without `^LL` only the 0-32000 operand range applies.
Each failure raises `ValueError` naming the crossed edge, the rectangle and the bounds, before the raster is built.
Keyword geometries are offsets relative to a located field or run and are negative by design in consumer seeds, so only the mapped page or label rectangle is checked, never the geometry itself.

### Z64 is opt-in through `compression="z64"`

`stamp_document`, `StampRequest` and the endpoint take `compression: Optional[str] = None`; `None` emits today's uppercase hex byte-identically, `"z64"` emits `^GFA,{total},{total},{bpr},:Z64:{b64}:{crc}^FS`.
`{b64}` is the standard-alphabet, padded base64 of `zlib.compress` over the packed 1-bpp rows, `{total}` and `{bpr}` keep their uncompressed values, and `{crc}` is the CRC-16/XMODEM (polynomial 0x1021, initial value 0) of the base64 text as four uppercase hex digits.
A string rather than a boolean leaves room for `:B64:` or ACS run-length encoding without a second flag, and the unprefixed name matches `layer` and `graphic_name`, which are equally backend-specific; the PDF backend ignores it.
Any value other than `None` or `"z64"` raises `ValueError` naming the accepted values.
With `graphic_name`, the `~DY` download carries the same Z64 data, `~DY{name},A,G,{total},{bpr},:Z64:{b64}:{crc}`, where format `A` covers ASCII-encoded data, Z64 included, and `{total}` and `{bpr}` keep their uncompressed values; the `^XG` recall is unchanged.
Both Z64 paths are checked once on Labelary or a printer (task 5.3).

### The stamped page owns its resources

Before merging, `stamp_pdf` replaces the stamped page's `/Resources` with a direct copy of its effective resources (its own entry, or the one inherited from the page tree), copying the top-level dictionary and each subdictionary the merge writes into (`/XObject`, `/Font`, `/ExtGState`, `/ProcSet`); streams stay shared, since the merge never mutates them.
Copying whenever the entry is indirect or inherited, rather than detecting sharing across pages, keeps the rule local to one page.

### Paper is detected on the stamped page

The paper variant is measured on the page the stamp will land on, when that is known before the registry key is composed: the `page` argument when given, else, for a consumer PDF keyword, the first page containing the keyword, located before the key is composed.
A seed lookup without a `page` argument still measures page 1, because the seed that names its page is found only through the key; an unparseable or out-of-range page yields `*`, and the later page validation raises.
Re-detecting the paper on the seed's own page after the seed resolves, and re-resolving when it differs, is a follow-up outside this change.

### `cn23` is a second declaration kind

The classifier's declaration kinds become `("cn22", "cn23")`; `DECLARATION_KIND` stays `cn22` for compatibility and `COMBINED_DOC_TYPE` stays `label_cn22`.
A document carrying exactly one declaration kind classifies as before with that kind: `cn23` alone, or `label_cn23` with the label kind, with `page` the first page carrying it.
A document carrying both declaration kinds raises `ValueError` naming both, rather than preferring one, because the stamp anchor would otherwise depend on which form the carrier printed first.
Carriers declare `cn23` markers in `PluginMetadata.document_sections` as for `cn22`; the SDK ships no `cn23` seed.

### Partial placement geometry raises

`stamp_document` raises `ValueError` for a placement carrying exactly one of `x` and `y`, and for a placement without `x` and `y` when no keyword is supplied, naming the missing field or the missing keyword.
Today the first falls through to the registry with the half anchor ignored, and the second ignores the geometry and consults the registry, so both stamp somewhere the caller did not ask for.
The check runs before resolution, beside the existing anchor-and-keyword contradiction check, and is delivered with the bounds work (task group 4), since both reject placements that would otherwise stamp in the wrong place.

### REST mirrors the SDK fields

`StampPlacementData` gains `unit` (`mm`, `pt`, `px`, default `mm`) and makes `x` and `y` optional, while `width` and `height` stay required; `StampData` gains `keyword` and `compression` (`z64`).
The serializer rejects with 400 a placement with exactly one of `x`/`y`, and a placement without `x`/`y` when no `keyword` is given, matching the SDK rule above, so the request fails validation before reaching the SDK.
The view passes `keyword` and `compression` through to `lib.stamp_document`; `page` is no longer documented as PDF-only.

## Risks

- Existing ZPL callers relying on the last-format default move to the first format; streams with a single format are unaffected, and keyword-resolved stamps already chose their format.
- Oracles that assert a stretched image change; the affected SDK tests are updated in the aspect-fit commit, with literals recomputed from the fit rule.
- New bounds errors surface placements that previously stamped off the page; that is the intended outcome, but consumers see 400s where they saw 201s.

## Open questions

- Size guard: should the SDK or the endpoint cap the emitted graphic or request size (PRD Q3)? No byte cap is decided.

## Follow-ups

- Re-detect the paper variant on the page a seed resolves to, after the seed lookup, and re-resolve when it differs from page 1.
