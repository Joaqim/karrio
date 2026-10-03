## Context

The ZPL stamp pipeline renders the date text with `PIL.ImageFont.load_default()` (no size — a ~11 px bitmap font), trims the rendered PNG to its ink bounding box (`_flatten_to_rgb`), and resizes the trimmed image to fill the entire date sub-rectangle (`_build_zpl_raster`).
Two defects follow, both measured on the PostNord CN22 reproduction (392 x 61 pre-rotation dots at 203 dpi):

- Size: the resize stretches the glyphs to the sub-rectangle's full 61-dot height — measured ink band rows 0-60 — against the form's `^CF0,18,18` body font, and the stretch is non-uniform (~3.3x horizontal, ~10x vertical from the bitmap font's metrics), so the digits are oversized and distorted.
- Blur: the upscaled bitmap font carries gray anti-aliased edges into the single `convert("1", dither=FLOYDSTEINBERG)`, which converts every gray edge into scattered black/white speckle — 152 isolated speckle pixels in the date half alone — and fragments the downscaled signature's anti-aliased strokes.

The PDF backend scales the same trimmed date image into the date sub-rectangle in points, so it carries the identical stretch and low-resolution defects on its seeded path (not live in production).

## Goals / Non-Goals

Goals:

- The date renders crisp, at a glyph height in-family with the carrier form's body text, preserving its natural aspect, on both backends.
- The composited ZPL raster carries no dither speckle; faint signature strokes survive as connected ink.
- The emitted ZPL contract (field structure, `^FO` origins, cache paths) is byte-shape identical; only the raster pixels change.

Non-Goals:

- Emitting native ZPL text fields for the date (option A): deferred — it needs rotation-aware `^FW`/`^A0` anchor semantics that cannot be verified locally without a renderer, plus `^FH` escaping, and it would rewrite the emitted-stream contract. Revisit if the printed threshold result still disappoints.
- Per-carrier date typography (font family, exact dot height per form): the fraction constant is the carrier-agnostic default, refinement stays open with the Q9 per-carrier partition.
- Changing the date/signature partition (`DATE_STRIP_FRACTION`), anchors, seeds, or any resolution behavior.

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Date glyph height = `DATE_FONT_HEIGHT_FRACTION = 0.30` of the placement's pre-rotation short axis | 0.30 x 61 dots = 18 dots on the CN22 strip at 203 dpi — exactly the form's `^CF0,18,18` body font, which is the direct answer to "quite a bit larger than the form's font". A fraction (not a fixed dot count) stays physically constant across printer densities. |
| D2 | Render with `load_default(size=...)` | On the venv's Pillow 12.3.0 this returns a scalable `FreeTypeFont` (verified by run), so the text renders at final pixel size with no upscaling. No bundled font asset is added (preserves the Q8 no-asset decision). |
| D3 | Render onto an opaque white ground sized exactly to the sub-rectangle, centered | The PDF overlay path trims by the alpha bounding box; an opaque ground makes the trim a no-op so the image keeps the sub-rectangle's aspect and the scale into the rectangle is uniform. The ZPL path pastes it directly. The existing PDF flatten already paints overlays on opaque white (no soft mask is emitted), so no visual contract changes. |
| D4 | Shrink-to-fit: reduce the font size when the natural text width exceeds the sub-rectangle | A caller-owned locale string ("22 september 2026") can overflow the strip; shrinking preserves aspect where the old stretch distorted. Single proportional step: `size = max(int(size * target_w / natural_w), 1)`. |
| D5 | Binarize with fixed ink threshold `ZPL_INK_THRESHOLD = 200` (luminance < 200 is ink) | Anti-aliased text edges and faint signature strokes (the fixture's semi-transparent strokes flatten to gray 75-102) land below 200 and survive as solid ink; error diffusion turns exactly these pixels into speckle. Accepted tradeoff: paper-noise pixels above ~200 in dirty scans stay white, near-200 noise becomes ink — a one-constant revision if a real scan proves the bound wrong. Supersedes the `_build_zpl_raster` "shared halftone grid" decision (its rationale — keeping date and signature on one halftone grid — is void when neither is halftoned). |
| D6 | LANCZOS resampling for the signature | Strictly better stroke preservation than bicubic on downscale; free of contract consequences. |
| D7 | PDF date rendered at points x 300/72 pixels | `_build_overlay_page` saves its image PDF at 300 dpi; sizing the render in that pixel space makes the subsequent scale-to-rect exactly 1:1, giving uniform `cm` scale factors the oracle can read. |
| D8 | Threshold applies to the whole composited canvas (date and signature) | One binarization step keeps the pipeline shape (build RGB canvas, one conversion to 1-bpp); the date is rendered at target size so its grays are edge anti-aliasing only, and the threshold absorbs them. |

## Risks / Trade-offs

- Threshold binarization discards tonality: a deliberately light-gray signature renders solid black. For a legal signature mark on a thermal printer, solid ink is the intended rendering; tonal rendering was the defect, not a feature.
- `load_default(size=...)`'s typeface varies across Pillow versions (it is a bundled font): the date's typeface is not pinned to the carrier form's font 0. Acceptable — family resemblance, size, and crispness are the requirements; exact typeface matching belongs to option A.
- The fixtures suite's byte-stability tests compare two runs of the same request; the pipeline stays deterministic under threshold and LANCZOS, so they hold (verified green in the gates).
- The raster bytes of every stamped label change; any consumer pinning exact GRF hex breaks. The vendored tests pin structure (origins, byte counts, payload equality across runs), not literal hex payloads.

## Migration Plan

Pure render-pipeline change; no stored state, no schema, no API shape. Consumers see different (corrected) pixels immediately on the next stamp call.

## Open Questions

- Q9 (per-carrier date/signature partition and typography) remains open with the prior change; nothing here resolves or constrains it.
