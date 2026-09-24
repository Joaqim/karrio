## Why

The rendered ZPL stamp carries two defects reported against the deployed preview (2026-09-24) and confirmed by pixel measurement on the reproduction: the composited date is blurry, and its glyphs render several times larger than the form's own text.
The date half of a PostNord CN22 strip measures 152 isolated Floyd-Steinberg speckle pixels (of 3521 ink pixels), its glyph ink spans all 61 dots of the strip's short axis against the form's 18-dot body font, and the signature's anti-aliased strokes fragment under the same dither.
The mechanisms live in the render pipeline, not the anchors: `_render_date_image` draws the date with the unsized bitmap default font, `_flatten_to_rgb` trims the result to its ink bounding box, and `_build_zpl_raster` resizes that trimmed image to fill the whole date sub-rectangle — stretching the glyphs to the strip's full height and feeding gray upscaled edges to a single Floyd-Steinberg dither.
The PDF backend scales the same trimmed image into the date sub-rectangle and therefore carries the identical stretch defect on its seeded path.

## What Changes

- `_render_date_image` renders the date at the target sub-rectangle size with Pillow's scalable built-in font (`load_default(size=...)`, a `FreeTypeFont` on Pillow >= 10.1), centered on an opaque white ground at its natural glyph aspect, reducing the font size when the text would overflow the sub-rectangle's length.
- The date's glyph height becomes proportional to the placement's short axis (`DATE_FONT_HEIGHT_FRACTION = 0.30` of the pre-rotation height; 18 of 61 dots on the CN22 strip at 203 dpi — the form's own body font size) instead of stretched to fill the strip.
- The ZPL backend binarizes the composited raster with a fixed ink threshold (`ZPL_INK_THRESHOLD = 200` of 255) instead of Floyd-Steinberg dithering, and resamples the signature with LANCZOS instead of bicubic — solid glyph interiors, no scattered speckle, connected signature strokes.
- The PDF backend renders its date overlay at the sub-rectangle's aspect (points at the overlay save's 300 dpi), so the scale into the placement rectangle is uniform and the aspect distortion disappears.
- New red-first oracles in the SDK stamping suite: date glyph band height and aspect, zero isolated speckles in the date region, long-date shrink-to-fit, uniform PDF date scale, faint-stroke connectivity.
- The `_build_zpl_raster` docstring's "shared halftone grid" rationale — the decision the threshold supersedes — is replaced by the threshold rationale.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `documents/stamping`: MODIFIED requirement — the consumer-supplied date stamp renders at a proportional glyph height with natural aspect and shrinks to fit, on both backends. ADDED requirement — the ZPL raster binarizes by fixed ink threshold, not error diffusion.

## Impact

- `modules/sdk/karrio/core/utils/stamping.py` — `_render_date_image` (target-size rendering, white ground, shrink-to-fit), `_build_zpl_raster` (direct paste, LANCZOS, threshold binarization), `stamp_pdf`'s date branch (sub-rectangle-aspect rendering), two new constants, superseded docstring rationales replaced.
- `modules/sdk/tests/core/test_document_stamping.py` — new `TestZplDateRenderFidelity` and binarization oracles; `TestZplDitherContinuity` renamed to `TestZplRasterContinuity` with wording updated.
- The emitted ZPL contract is unchanged: still one inline `^GFA` graphic (or `~DY`/`^XG` when `graphic_name` is set) at the same `^FO` origin; only the raster pixels change.
- No API, database, dependency, or server-surface changes; native-ZPL-text dates (option A) were considered and deferred — see the PRD's alternatives table.
