# Stamp render fidelity (ZPL date blur and oversize)

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-09-24 |
| Status | Implemented |
| Owner | Joaqim Planstedt |
| Type | Bug fix |
| Reference | openspec change [stamp-render-fidelity](../openspec/changes/stamp-render-fidelity/proposal.md) ([design](../openspec/changes/stamp-render-fidelity/design.md), [tasks](../openspec/changes/stamp-render-fidelity/tasks.md), [spec delta](../openspec/changes/stamp-render-fidelity/specs/documents/stamping/spec.md)) |

---

## Executive Summary

The rendered ZPL stamp carries two defects reported against the deployed preview and confirmed by pixel measurement: the composited date is blurry, and its glyphs render at the strip's full height (~3.4x the form's 18-dot body font).
The mechanisms live in the render pipeline: the date is drawn with the unsized bitmap default font, trimmed to its ink bounding box, and resized to fill the entire date sub-rectangle, so the glyphs stretch edge-to-edge and their upscaled gray edges become Floyd-Steinberg speckle (152 isolated speckle pixels in the date half of a CN22 strip); the signature's anti-aliased strokes fragment under the same dither.
The PDF backend scales the same trimmed image into its date sub-rectangle and carries the identical stretch defect on its seeded path.
This PRD fixes both by rendering the date at the target size with the scalable built-in font (glyph height 0.30 of the placement's short axis — 18 of 61 dots on the CN22 strip, the form's own body size), preserving natural aspect with shrink-to-fit, and binarizing the ZPL raster with a fixed ink threshold instead of dithering.
The owner selected this option (B) over native ZPL text (`^A0`) on 2026-09-24, accepting the LANCZOS-plus-threshold signature treatment; option A stays available as a follow-up if the printed result still disappoints.

### Key architecture decisions

1. **Date height is a fraction of the placement's short axis** (`DATE_FONT_HEIGHT_FRACTION = 0.30`): physically constant across printer densities, and on the CN22 strip at 203 dpi it equals the form's `^CF0,18,18` body font exactly — the direct answer to "quite a bit larger".
2. **The date renders onto an opaque white ground sized exactly to its sub-rectangle**: the PDF overlay path's alpha-bbox trim becomes a no-op, so the scale into the placement rectangle is uniform and the PDF's aspect distortion disappears with no PDF-side compositing change.
3. **One binarization step, fixed ink threshold** (`ZPL_INK_THRESHOLD = 200`): supersedes the `_build_zpl_raster` "shared halftone grid" decision — neither element is halftoned any more, and error diffusion was the speckle source.
4. **The emitted ZPL contract is unchanged**: still one `^GFA` graphic (or `~DY`/`^XG`) at the same `^FO` origin; only the raster pixels change, so the structural tests and the printer-cache payload-equality test survive as written.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| `_render_date_image`, `_build_zpl_raster`, `stamp_pdf`'s date branch | Native ZPL text dates (option A; deferred) |
| `DATE_FONT_HEIGHT_FRACTION`, `ZPL_INK_THRESHOLD` constants | `DATE_STRIP_FRACTION` partition and Q9 per-carrier typography |
| Red-first fidelity oracles in the SDK stamping suite | Anchors, seeds, keyword resolution, registry mechanics |
| Docstring rationale replacement (halftone grid -> threshold) | Server/API surfaces, database, dependencies |

---

## Open Questions & Decisions

### Pending Questions

None.
Q9 (per-carrier partition and typography) remains open with the prior change and is untouched here.

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | Fix direction | Option B: render at target size + threshold (owner choice) | Small blast radius, ZPL contract unchanged, fixes the PDF path too, fully verifiable locally; native text (A) needs unverifiable `^FW`/`^A0` anchor semantics | 2026-09-24 |
| D2 | Signature binarization | LANCZOS + ink threshold 200 (owner choice) | Solid connected strokes, no speckle; the fixture's semi-transparent strokes flatten to gray 75-102 and survive; tonality is not a goal for a legal signature mark | 2026-09-24 |
| D3 | Date height | 0.30 of the short axis | 18 of 61 dots on the CN22 = the form's body font | 2026-09-24 |
| D4 | Date ground | Opaque white at sub-rectangle size | Makes the PDF trim a no-op, enabling the uniform-scale fix; consistent with the existing white-flatten behavior | 2026-09-24 |
| D5 | Overflow strategy | Shrink-to-fit, preserving aspect | Caller-owned locale strings can overflow; distortion was the defect | 2026-09-24 |

### Edge Cases Requiring Input

None.

---

## Problem Statement

### Current State

```python
# stamping.py:177-197 -- unsized bitmap font
def _render_date_image(date: str) -> str:
    font = PIL.ImageFont.load_default()          # ~11 px bitmap font

# stamping.py:403-418 -- trim to ink bbox (no padding survives)
def _flatten_to_rgb(image_b64: str) -> "PIL.Image.Image":
    bounds = source.getchannel("A").getbbox()
    trimmed = source.crop(bounds) if bounds is not None else source

# stamping.py:437-448 -- stretch to fill, then one Floyd-Steinberg dither
if request.date:
    date_width = max(int(round(width * DATE_STRIP_FRACTION)), 1)
    date_image = _flatten_to_rgb(_render_date_image(request.date))
    canvas.paste(date_image.resize((date_width, height)), (0, 0))
    canvas.paste(signature.resize((max(width - date_width, 1), height)), (date_width, 0))
return canvas.convert("1", dither=PIL.Image.Dither.FLOYDSTEINBERG)
```

Measured on the CN22 reproduction (392 x 61 pre-rotation dots, `date="2026-09-22"`):

| Observable | Measured | Form reference |
|------------|----------|----------------|
| Date ink band height | rows 0-60 (61 dots, full strip) | body font 18 dots (`^CF0,18,18`) |
| Stretch ratios | ~3.3x horizontal, ~10x vertical | 1:1 required |
| Isolated speckle pixels, date half | 152 (of 3521 ink px) | 0 required |
| Signature strokes | fragmented dotted runs (analyzer: "thin, broken, fragmented") | connected ink |

### Desired State

```python
# stamping.py -- the corrected pipeline
DATE_FONT_HEIGHT_FRACTION: float = 0.30
ZPL_INK_THRESHOLD: int = 200

def _render_date_image(date: str, width: int, height: int) -> str:
    """Render the date onto an opaque white ground sized to the sub-rectangle,
    centered at natural aspect, glyph height 0.30 of the height, shrunk to fit
    the width when a long locale string would overflow."""

# _build_zpl_raster: paste the date image directly (no resize, no trim),
# LANCZOS for the signature, then:
gray.point(lambda v: 255 if v >= ZPL_INK_THRESHOLD else 0).convert(
    "1", dither=PIL.Image.Dither.NONE
)
```

### Problems

1. **Oversized, distorted date glyphs**: trim-to-ink plus resize-to-fill stretches the date to the full 61-dot strip height and distorts its aspect — "the font for the date is quite a bit larger than font used in other parts of the ZPL".
2. **Blur**: the upscaled bitmap font's gray edges and the downscaled signature's anti-aliased strokes become Floyd-Steinberg speckle — "quite a blurry date and signature".
3. **The PDF backend carries the same stretch**: it scales the same trimmed image into the date sub-rectangle, distorting aspect identically on the seeded PDF path.

---

## Goals & Success Criteria

### Goals

1. The ZPL date renders crisp (zero isolated speckle pixels in its region) at a glyph height in-family with the form's body text, natural aspect preserved, on any placement geometry and density.
2. The signature survives binarization as connected ink, including faint strokes.
3. The PDF date overlay scales uniformly into its rectangle.
4. The emitted ZPL contract is structurally unchanged.

### Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| New fidelity oracles verified red against the shipped pipeline | all six red before task 3.1 | Must-have |
| Date ink band height (CN22, 203 dpi) | <= 18 dots (cap height ~13) | Must-have |
| Isolated speckle pixels in the date region | 0 | Must-have |
| Date band aspect vs natural font aspect | within 0.7-1.4x | Must-have |
| PDF date overlay sx/sy | 1.0 within 0.1 | Must-have |
| Faint-stroke connected run | >= 90% of stroke length | Must-have |
| Both stamping suites + `./bin/run-sdk-tests`, black | exit 0, clean | Must-have |

### Launch Criteria

**Must-have (P0):**

- [x] openspec change + this PRD (task 1.1)
- [x] Red-first oracles landed red (task 2.1), reproduction re-measured (task 2.2)
- [x] Implementation green (task 3.1)
- [x] Gates + fresh-context review (task 4.1, 4.2), archive + spec sync (task 4.3)

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| B: render at target size + threshold (both backends) | Fixes size, aspect, and blur everywhere; contract unchanged; locally verifiable | Typeface is Pillow's bundled font, not the form's font 0 | **Selected** |
| A: native ZPL text (`^FWR`-scoped `^A0,h,w` + `^FD`) | Printer-native vector text, exact font 0 match | Rotation-aware anchor semantics unverifiable locally (no renderer); escaping; rewrites emitted contract and tests; PDF path unfixed | Deferred; revisit if prints disappoint |
| Keep dither, only fix size | Smallest change | Keeps the speckle (the reported blur) on both date and signature | Rejected |
| Per-carrier date typography now | Exact per-form match | Requires measured per-carrier data that does not exist yet (Q9 open) | Deferred with Q9 |

### Trade-off Analysis

The threshold discards tonality: a deliberately light-gray signature prints solid black.
For a legal signature mark on a thermal printer that is the intended rendering — the gray tones were rendering as speckle, not as tone.
The 200 bound is ink-biased to preserve faint strokes; if a real scanned signature with paper noise proves too aggressive, it is a one-constant revision.

---

## Technical Design

### Render pipeline, before and after

```
                         BEFORE (defects measured 2026-09-24)

   date string ──load_default()──> ~11px bitmap PNG ──trim to ink bbox──> tiny ink image
                                                                        │
   signature PNG ──trim+flatten──> RGB ─────────────────────────────────┤
                                                                        v
                                            resize to FILL both sub-rects (stretch: 3.3x/10x)
                                                                        │
                                                                        v
                                        convert("1", FLOYDSTEINBERG) ──> 152 speckles,
                                                                          fragmented strokes


                         AFTER (this change)

   date string ──load_default(size=0.30*height)──> FreeTypeFont at final px size
                          │                                (shrink-to-fit if wider than sub-rect)
                          v
                 white-ground RGB canvas, exactly date_width x height, centered
                          │
   signature PNG ──trim+flatten──> RGB ──LANCZOS──> signature sub-rect
                          │
                          v
        paste both into one RGB canvas (placement's dot extent)
                          │
                          v
        L.point(v < 200 -> ink).convert("1", NONE) ──> 0 speckles, connected strokes

   PDF: same date canvas at (points * 300/72) px -> alpha-bbox trim is a no-op
        (opaque ground) -> scale into the rect is uniform (sx == sy)
```

### Oracle design (non-circular)

Each oracle reads the pipeline's output pixels or the PDF's merged `cm` matrix and derives its expected bound from the spec'd contract and independent font metrics — never from the production code path under test:

| Spec scenario | Oracle | Expected literal derivation |
|---------------|--------|-----------------------------|
| Proportional glyph height | date-half ink band height <= `round(0.30 * height)` and touches neither edge | The fraction constant (the spec'd contract); today measures the full height, so it is red first |
| Natural aspect | band w/h within 0.7-1.4x of `textbbox` w/h at the same font size | Pillow font metrics rendered independently in the test |
| Shrink-to-fit | long-string band height also <= the bound (today the full height) and width within the sub-rect | Geometry literals of `_zpl_placement()` (480 x 160 dots at 203 dpi) |
| No isolated speckles | count of 8-neighbor-isolated black pixels in the date half == 0 | Pixel scan of the raster |
| Uniform PDF scale | date overlay `cm` sx/sy within 0.9-1.1 | `_overlay_cms` on the sentinel PDF; today ~0.22 |
| Faint-stroke connectivity | longest connected black run in the stroke's row >= 90% of the image width | Synthetic gray-stroke PNG (flattens to gray ~115, below the 200 threshold) |

### Edge Cases

| Scenario | Expected Behavior | Handling |
|----------|-------------------|----------|
| Empty date string | Treated as absent (unchanged) | Existing `if request.date:` guard and test |
| Date longer than the sub-rect at 0.30 height | Shrink to fit, aspect preserved | Single proportional size reduction (D5) |
| Sub-rect resolves to 1 px | Font size floors at 1 px; textbbox guarded with `max(..., 1)` | Same guard style as today |
| Dirty scanned signature (paper noise ~200+) | Near-white noise stays white; strokes become ink | Ink-biased threshold; constant revisable |
| Non-integer font size | `round` to int px | Pillow takes int sizes |
| 300 dpi placement | Height in dots grows; physical glyph height constant | Fraction-of-short-axis is density-independent |

### Failure Modes

| What Can Go Wrong | Impact | Mitigation |
|-------------------|--------|------------|
| Threshold too aggressive for real scans | Paper noise becomes ink | One-constant revision; documented tradeoff |
| `load_default(size=...)` typeface changes across Pillow versions | Date typeface shifts | Size/crispness are the contract, not the typeface; pinned requirements file |
| Byte-pinned consumer expectations break | Corrected pixels differ | Vendored tests pin structure, not hex; CHANGELOG entry at release |

---

## Implementation Plan

| Task | Files | Commit | Verification |
|------|-------|--------|--------------|
| 1. openspec change + this PRD | `openspec/changes/stamp-render-fidelity/*`, `PRDs/STAMP_RENDER_FIDELITY.md` | `docs(openspec): propose stamp render fidelity change` | `openspec validate` |
| 2. Red-first oracles + rename | `modules/sdk/tests/core/test_document_stamping.py` | `test(documents): pin render fidelity oracles red` | New tests fail against the shipped pipeline; run recorded |
| 3. Implementation | `modules/sdk/karrio/core/utils/stamping.py` | `fix(documents): render date at target size and threshold zpl raster` | New tests green; CN22 reproduction re-measured (band ~13 dots, 0 speckles); crops saved |
| 4. Gates, review, archive | suites + `openspec/specs/documents/stamping/spec.md` | `chore(openspec): sync stamping spec and archive render fidelity change` | Both stamping suites + `./bin/run-sdk-tests` exit 0; black clean; fresh-context review approved |

**Dependency order:** 1 -> 2 (red) -> 3 (green) -> 4.

---

## Testing Strategy

`unittest` only (never pytest), run from the repository root with the repo venv.

```bash
# red first (after task 2), green after (task 3), then the full gate
.venv/karrio/bin/python -m unittest discover -v -f modules/sdk/tests -p "test_document_stamping*"
./bin/run-sdk-tests
```

The CN22 reproduction script measures the same observables as the diagnosis (ink band rows, isolated-speckle count) before and after, so the fix's effect is demonstrated on the identical geometry the defects were measured on.

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Fidelity oracles pass vacuously | Defects survive | Low | Red-first run against the shipped pipeline is recorded before implementation |
| PDF uniform-scale oracle reads the wrong overlay | False green | Low | Date overlay identified by paint order and translation-x, established helpers |
| Cross-module regression | Unrelated suites break | Low | Full SDK gate before any commit |
| Review finds the threshold choice wrong for production signatures | Rework | Low-Medium | Constant-level change; alternatives documented |

---

## Migration and Rollback

Pure render-pipeline change with no stored state; rollback is reverting the commits.
Consumers see corrected pixels on the next stamp call; no data cleanup applies.

---

## Appendices

### Appendix A: Diagnosis Evidence (2026-09-24)

- Reproduction: `lib.stamp_document` on the vendored CN22 ZPL fixture with `signature_test.png` and `date="2026-09-22"`, resolved through the seed keyword path (`^FO7,303`, bpr 8, total 3136).
- Date ink band rows 0-60 (all 61 dots) vs the form's `^CF0,18,18` body font; stretch ~3.3x horizontal / ~10x vertical from the bitmap font's natural metrics.
- 152 isolated Floyd-Steinberg speckle pixels in the date half (of 3521 ink pixels); signature strokes fragmented after ~3x downscale under the same dither.
- Vision passes on the strip and on the user's preview crop independently reported: "porous, speckled" glyph interiors, "several times taller than the form text", "thin, broken, fragmented" signature strokes.
- Option B prototype (at-size `load_default(size=21)`, threshold): glyph band 15 dots, zero isolated speckles — the approach was demonstrated before selection.
