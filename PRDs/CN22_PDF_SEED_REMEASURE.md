# CN22 PDF seed re-measurement

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-09-24 |
| Status | In Progress |
| Owner | Joaqim Planstedt |
| Type | Enhancement |
| Reference | openspec change [cn22-pdf-seed-remeasure](../openspec/changes/cn22-pdf-seed-remeasure/proposal.md) ([design](../openspec/changes/cn22-pdf-seed-remeasure/design.md), [tasks](../openspec/changes/cn22-pdf-seed-remeasure/tasks.md), [spec delta](../openspec/changes/cn22-pdf-seed-remeasure/specs/documents/stamping/spec.md)); [AGENTS.md](../AGENTS.md) |

---

## Executive Summary

The shipped PostNord CN22 PDF seed (`_CN22_PLACEMENT`, revision 2) renders a horizontal 49.1 x 7.6 mm strip that starts ~19.96 mm off the label's left edge — an axis-swapped fossil of the revision-1 centre-pivot seed, produced when revision 2's centre-preserving algebraic conversion survived the corner-anchor semantics change that altered what a given `(width, height, rotation)` tuple renders as.
This PRD executes the appendix B decision in [KEYWORD_ANCHORED_STAMPING.md](KEYWORD_ANCHORED_STAMPING.md) (owner decision 2026-09-24, option A): re-measure the seed to the archived probe strip, bump the revision to 3, and replace the circular band oracles that let the defect ship with oracles that derive from the measurement.
The spec source of truth is the openspec change `openspec/changes/cn22-pdf-seed-remeasure/`; this PRD elaborates the design's decisions with the evidence, per the repo PRD-first rule.
The registry-seeded PDF path is not live in production (owner decision 2026-09-24), so the correction carries no deployment urgency; landing it now closes the loop while the measurement is fresh.

### Key architecture decisions

1. **Corrected encoding is `rotation=90` with a pre-rotation 49.11 x 7.62 extent**: `StampPlacement(x=53.34, y=91.44, width=49.11, height=7.62, rotation=90)` renders the vertical 7.62 x 49.11 mm strip at page x [53.34, 60.96], y [91.44, 140.55] mm. This corrects the appendix B follow-up note's loose "rotation 0" wording, which described the rendered rectangle's upright shape rather than the placement encoding; rotation 0 with a 7.62 x 49.11 extent would render the signature upright against the form's `^FWR` sideways reading.
2. **Non-circular oracles derive from the probe, never from the seed**: `TestDefaultRegistry` asserts the probe literals with the rendered-extent arithmetic spelled out independently, and `TestCn22Seed` plus the fixtures test assert merged-overlay `cm` translations hand-computed from the probe numbers and the A4 page height. A seed change without a re-measurement breaks the oracles — which is the property whose absence let the defect ship.
3. **Revision bumps 2 to 3**: `revision` marks anchor supersession and nothing consumes it as a gate; the PDF placement is genuinely re-measured, so the revision bumps. The ZPL keyword fields ride the same `StampSeed` object unchanged.
4. **Values and tests only; no runtime code change**: the defect was inside the A4 mediabox, and tightening `_validate_pdf_extent` to know each form's target region is seed-authoring data, not backend logic. The on-form invariant lives in the new spec requirement and the oracles.
5. **The text-layer fixture test decouples from the seed**: it pins the revision-2 anchor only "for consistency"; any valid placement exercises the text layer the same way, so future seed revisions do not touch it.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| `_CN22_PLACEMENT` values, provenance comment, `_CN22_SEED.revision` 2 -> 3 | The ZPL keyword seed (`_CN22_KEYWORD_PLACEMENT` is the verified reference, not the patient) |
| Oracle rewrites: `TestDefaultRegistry.test_cn22_seed_resolves_to_the_documented_anchor`, `TestCn22Seed.test_seed_composites_at_the_measured_anchor`, the fixtures `_CN22_BAND_PT` band test | Keyword-anchored resolution, locators, registry mechanics |
| Decoupling `test_real_signature_preserves_the_text_layer` onto a neutral valid placement | Compositing backends, rotation semantics, `_validate_pdf_extent` / bounds validation |
| Appendix B follow-up-note correction in `PRDs/KEYWORD_ANCHORED_STAMPING.md` | The Q9 date/signature partition (stays open with the prior change) |
| The openspec `documents/stamping` delta (authored on this branch) | Any other seed, any server/API surface |

---

## Open Questions & Decisions

### Pending Questions

None.
Q9 (per-carrier date/signature partition) remains open with the prior change and is out of scope here.

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | Seed encoding for the vertical strip | `rotation=90`, pre-rotation extent 49.11 x 7.62, anchor (53.34, 91.44) | `StampPlacement.width`/`height` are pre-rotation and a nonzero rotation anchors the rotated extent's top-left at `(x, y)` (`stamping.py:59-77`); rotation 0 with a 7.62 x 49.11 extent renders the glyphs upright against the form's `^FWR` reading. Same geometry shape as the verified ZPL seed (`width=49.1, height=7.6, rotation=90`) — two coordinate systems, one strip | 2026-09-24 |
| D2 | Oracle basis | Probe literals and hand-computed points, never the seed object | The revision-2 band oracles read their expected band from the same anchor under test; measurement-derived literals would have caught the axis swap red | 2026-09-24 |
| D3 | Revision | Bump 2 -> 3 | `revision` marks anchor supersession; this is a genuine re-measurement. Additive keyword data did not bump it before (keyword PRD D11), and the keyword geometry is not re-measured now | 2026-09-24 |
| D4 | Runtime bounds validation | Unchanged | The defective strip was inside the mediabox; per-form target regions are seed-authoring data, so the invariant goes into the spec and oracles, not `_validate_pdf_extent` | 2026-09-24 |
| D5 | Text-layer fixture test | Neutral valid placement instead of the seed anchor | Any valid placement exercises the text layer identically; the current pin exists only "for consistency" and would churn on every seed revision | 2026-09-24 |
| D6 | Timing | Land now, no deployment urgency | The registry-seeded PDF path is not live in production (owner decision 2026-09-24, appendix B option A); landing while the measurement is fresh avoids re-deriving it later | 2026-09-24 |

### Edge Cases Requiring Input

None.

---

## Problem Statement

### Current State

```python
# stamping.py:722-724 -- the shipped revision-2 seed
_CN22_PLACEMENT: StampPlacement = StampPlacement(
    x=32.55, y=112.15, width=7.6, height=49.1, rotation=90
)
# Under corner-anchor semantics the pre-rotation 7.6 x 49.1 rect rotates
# clockwise to a HORIZONTAL 49.1 x 7.6 extent anchored at (32.55, 112.15):
# page x [32.55, 81.65], y [112.15, 119.75] mm -> label x [-159.5, 232.9]
# dots, ~19.96 mm off the label's left edge.
```

```python
# test_document_stamping.py:1046-1057 -- the circular oracle
placement = stamping._default_registry("postnord/cn22/PDF/A4")
self.assertAlmostEqual(placement.x, 32.55, places=2)   # the seed's own values
self.assertAlmostEqual(placement.y, 112.15, places=2)  # asserted back at it
# ...and the fixtures' _CN22_BAND_PT = (515.0, 530.0) derives from the same
# extent: band arithmetic computed FROM the anchor under test, so a seed
# change (correct or broken) only ever requires copying new numbers in.
```

### Desired State

```python
# stamping.py -- the re-measured revision-3 seed (probe2b, cross-validated
# against the ZPL form at sub-dot precision; arithmetic in appendix A)
_CN22_PLACEMENT: StampPlacement = StampPlacement(
    x=53.34, y=91.44, width=49.11, height=7.62, rotation=90
)
_CN22_SEED: StampSeed = StampSeed(
    placement=_CN22_PLACEMENT,
    revision=3,
    keyword="Date and Sender's signature",
    keyword_placement=_CN22_KEYWORD_PLACEMENT,  # unchanged
)
```

```python
# the rewritten oracles -- expected literals from the probe measurement,
# computed in the test from 53.34 / 91.44 / 49.11 / 7.62 / A4 297 mm
self.assertAlmostEqual(placement.x, 53.34, places=2)      # probe literal
self.assertAlmostEqual(placement.x + placement.height, 60.96)  # extent math
```

### Problems

1. **The shipped seed renders the wrong strip**: revision 2 renders a horizontal 49.1 x 7.6 mm strip mapping to label x [-159.5, 232.9] dots — its left edge starts 19.96 mm off the label frame's left edge, and it is unexpressible as a keyword-anchored placement (`_validate_anchor` rejects the derived x of -19.961 mm).
2. **The band oracles were circular**: `TestDefaultRegistry` asserted the seed's own values back at it, and the fixtures' `_CN22_BAND_PT` band was computed from the same extent, so the approving review's oracles could not fail on the defect they were meant to guard.
3. **Page-level validation cannot catch this class of defect**: the defective extent stayed inside the A4 mediabox, so `_validate_pdf_extent` passed; the missing invariant — a seed lands on the carrier form's measured target region — had no spec home.

---

## Goals & Success Criteria

### Goals

1. `_CN22_PLACEMENT` renders the measured vertical signature strip: page x [53.34, 60.96] mm, y [91.44, 140.55] mm, bottom edge on the form box's bottom rule, glyphs reading sideways — the same physical strip the ZPL keyword seed pins.
2. Every oracle asserting the seed derives its expected values from the probe measurement, so a seed change without a re-measurement fails a test.
3. No runtime code path, API, database, or dependency surface changes; the ZPL keyword seed and keyword-anchored resolution are byte-identical.

### Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Rewritten oracles fail red against the shipped revision-2 seed | tasks 1.2-1.4 verified red before the seed change | Must-have |
| Rewritten oracles pass green after task 2.1 | exact probe literals and hand-computed translations | Must-have |
| Rendered extent lands on the form | label-relative left edge 0.83 mm >= 0; strip bottom = form box bottom rule (label y ~695 dots) | Must-have |
| Both stamping suites + full SDK gate | exit 0, black clean, no cross-module regressions | Must-have |

### Launch Criteria

**Must-have (P0):**

- [ ] This PRD (task 1.1)
- [ ] Non-circular oracles landed red against revision 2 (tasks 1.2-1.4)
- [ ] Appendix B follow-up note corrected to the `rotation=90` encoding (task 1.5)
- [ ] Seed corrected, revision 3, oracles green (task 2.1)
- [ ] Both stamping suites + `./bin/run-sdk-tests` exit 0, black clean, fresh-context review gate passed (task 3.1)

**Nice-to-have (P1):**

- [ ] None identified; the change is deliberately bounded to one seed and its oracles

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Re-measure to the probe strip, encode `rotation=90` with pre-rotation 49.11 x 7.62 | Renders the measured strip at the form's own orientation; same geometry shape as the verified ZPL seed; no runtime change | None identified; the encoding subtlety demands the oracle spell the extent arithmetic out | **Selected** |
| Follow appendix B's follow-up note literally: `rotation=0` with a 7.62 x 49.11 extent | Same rendered rectangle, simpler to read | Renders the signature upright, contradicting the `^FWR` sideways reading the whole design aligns with; diverges from the ZPL seed's geometry shape | Rejected |
| Tighten `_validate_pdf_extent` to know per-form target regions | Runtime enforcement | Seed-authoring data inside backend logic; every new seed would need backend changes; the spec requirement plus oracles enforce the same invariant | Rejected |
| Adjust the oracles to the shipped values (treat revision 2 as the truth) | No seed change | Re-enshrines the circularity; the strip is measurably off the form and unexpressible as a keyword placement | Rejected |
| Defer until the registry-seeded PDF path goes live | Nothing to ship now | The measurement and its cross-validation are fresh today; re-deriving them later repeats the work at higher risk | Rejected |

### Trade-off Analysis

The change is values and tests only, so the trade surface is the oracle design rather than architecture.
Measurement-derived literals are the single property that converts this class of defect from visually-noticed to mechanically-caught, at the cost that a re-vendored carrier form invalidates the literals — which the existing rule already treats as a re-measurement with a revision bump.
Encoding the strip as `rotation=90` keeps the PDF seed in the same geometry shape as the ZPL keyword seed, so future readers see one strip in two coordinate systems rather than two apparently different conventions.

---

## Technical Design

### Existing Code Analysis

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| `StampPlacement` docstring | `stamping.py:59-77` | The encoding rule the corrected seed obeys: `width`/`height` pre-rotation, nonzero rotation anchors the rotated extent's top-left at `(x, y)` |
| `_CN22_PLACEMENT` + known-defect comment | `stamping.py:706-724` | Values replaced; defect comment replaced with probe provenance and revision history |
| `_CN22_KEYWORD_PLACEMENT` | `stamping.py:726-738` | Untouched reference: its shape (`width=49.1, height=7.6, rotation=90`) is the cross-check the corrected encoding matches |
| `_CN22_SEED` / `_SEED_REGISTRY` | `stamping.py:740-758` | `revision` 2 -> 3; registry entries unchanged |
| `_rotated_corner_extents` / `_merge_overlay` | `stamping.py:224-243` / `246-279` | Oracle arithmetic source: at rotation 90, `(min_x, max_y) = (0, 0)`, so each overlay's `cm` translation equals its anchor |
| `_validate_pdf_extent` | `stamping.py:282-327` | Explains why the defect shipped (mediabox-only check); unchanged |
| `_validate_anchor` | `stamping.py:200-207` | Defect evidence (rejects derived x -19.961 mm); unchanged |
| `DATE_STRIP_FRACTION` | `stamping.py:43` | The signature sub-anchor offset under the date split: `(0, -mm_to_points(49.11)/2)` |
| `TestDefaultRegistry` / `TestCn22Seed` | `test_document_stamping.py:1042` / `:1080` | The circular oracles rewritten (tasks 1.2, 1.3) |
| `_CN22_BAND_PT` + the two fixture tests | `test_document_stamping_fixtures.py:104`, `:228-271` | Band oracle replaced by a probe-derived translation; text-layer test decoupled (task 1.4) |
| `_overlay_cms` / `_cms_in_y_band` | `test_document_stamping.py:250`, `:275`; fixtures `:67` | Reused `cm` extraction helpers; the fixture's own image transform still requires band isolation rather than a first-cm-per-stream read |
| Appendix B measurement record | `PRDs/KEYWORD_ANCHORED_STAMPING.md` | Primary record of the cross-check and the option-A decision; its follow-up note is corrected (task 1.5) |
| openspec change | `openspec/changes/cn22-pdf-seed-remeasure/` | Spec source of truth: the ADDED requirement and its two scenarios |

### Architecture Overview: One Physical Strip, Two Coordinate Systems

The A4 CN22 PDF carries the label form as a `/Form1` XObject whose label frame maps onto the page by pure translation (appendix A).
The measured strip sits in the signature column at the form box's left edge, running from y 91.44 mm down to the form box's bottom rule.

```
        the A4 page (210 x 297 mm), millimetres from the page top-left
  x/mm   0          52.5    60.96                        157.5       210
   y 0   +-------------------------------------------------------------+
         |                       page margin                          |
  53.5 --|--------+-------------------------------------+--------------|--
         |        |  label frame /Form1                 |              |
         |        |  BBox 839 x 1518 dots @ 203 dpi     |              |
         |        |  = 105.0 x 189.9 mm, origin at      |              |
         |        |  page (52.51, 53.53) mm              |              |
         |        | +-- form box: ^FO10,15 ^GB820,680 --+|              |
         |        | |    label x 10..830, y 15..695 dots||              |
  91.4 --|--------|-|X  strip top-left = page (53.34,   ||              |--
         |        | |X    91.44) mm                      ||              |
         |        | |X   the measured strip:             ||              |
         |        | |X   7.62 wide x 49.11 tall,         ||              |
         |        | |X   glyphs read sideways (^FWR)     ||              |
         |        | |X   PDF extent x [53.34, 60.96] mm  ||              |
 140.6 --|--------|-|X  strip bottom = the form box's    ||              |--
         |        | |   bottom rule (label y 695 dots)   ||              |
         |        | +------------------------------------+|              |
 243.5 --|--------+-------------------------------------+--------------|--
         |                       page margin                          |
   297   +-------------------------------------------------------------+
                  ^ the label frame's left rule at page x 52.51; the
                    strip's left edge sits 0.83 mm inside it (label
                    x 6.63 dots)
```

The two seeds converge on that one strip from their own coordinate systems.

```
   PDF seed, revision 3 (this change)        ZPL keyword seed (shipped, verified)
   StampPlacement(                           keyword "Date and Sender's signature"
     x=53.34, y=91.44,      mm from the      located field origin ^FO20,35 dots
     width=49.11, height=7.62,  pre-rotation + seed offset (-1.673, +33.529) mm
     rotation=90)            extent          = (0.829, 37.908) mm -> ^FO7,303
        |                                    StampPlacement(width=49.1,
        |  rotated extent:                     height=7.6, rotation=90,
        |  page x [53.34, 60.96] mm            dpi=203)
        |  page y [91.44, 140.55] mm        |  rotated extent:
        |                                   |  label x 7..68, y 303..695 dots
        +-----------------+-----------------+
                          v
           one physical strip on the CN22: the sideways-reading
           signature column, bottom edge on the form box's bottom
           rule -- the two views agree within dot rounding (the PDF
           probe maps to label x [6.63, 67.53], y [302.97, 695.44])
```

For contrast, the shipped revision-2 extent is the same strip rotated 90 degrees about its centre, half of it off the label entirely.

```
        the shipped revision-2 extent on the same page (the defect)
  x/mm   0      32.55                             81.65      157.5   210
   y 0   +----------------------------------------------+----------+
         |                                             |          |
112.2 --|---+=========================================+---       |--
         |   |   horizontal 49.1 x 7.6 mm extent:      |          |
         |   |   page x [32.55, 81.65], y [112.15,     |          |
119.8 --|---+-----------------------------------------+---       |--
         |   ^   119.75] mm; left edge 19.96 mm LEFT of the       |
         |       label frame (label x -159.5 dots), yet inside    |
         |       the A4 mediabox, so _validate_pdf_extent passed  |
   297   +----------------------------------------------+----------+
```

### Defect Mechanics: Centre Preserved, Orientation Not

Revision 1 seeded the strip under centre-pivot semantics as the tuple `(53.3, 91.4, 7.6, 49.1, 90)`.
The corner-anchor change re-expressed that anchor algebraically as `(x + (w-h)/2, y + (h-w)/2)` = `(53.3 - 20.75, 91.4 + 20.75)` = `(32.55, 112.15)`, carrying `(w, h, rotation)` across unchanged.
The conversion preserved the strip's centre — both extents centre at ~(57.1, 116.0) page mm — but the semantics change also changed what a given `(w, h, rotation)` renders as, so the unchanged tuple rotated the rendered orientation: the archived vertical strip became the shipped horizontal extent.

A provenance note for the record: `PRDs/DOCUMENTS_STAMPING_CORNER_ANCHOR.md` (2026-09-22, line 235) documented this conversion as re-expressing "revision 1's identical physical strip".
The appendix B measurement (2026-09-24) superseded that account: the conversion preserved the centre only, and the shipped extent is the archived probe strip rotated 90 degrees about that centre.
The shipped comment block already carries the defect annotation (`stamping.py:716-721`); task 2.1 replaces it with the probe provenance and the revision history.

### The Corrected Encoding

```python
_CN22_PLACEMENT: StampPlacement = StampPlacement(
    x=53.34, y=91.44, width=49.11, height=7.62, rotation=90
)
```

`width=49.11` and `height=7.62` are the image's dimensions before rotation; the clockwise 90-degree rotation turns the landscape rect into the vertical 7.62 x 49.11 extent whose top-left anchors at (53.34, 91.44), spanning page x [53.34, 60.96], y [91.44, 140.55] mm.
The rendered-extent arithmetic is therefore: extent width = `height` (7.62), extent height = `width` (49.11).
`rotation=0` with `width=7.62, height=49.11` would occupy the identical rectangle but render the signature upright — the glyphs must read along the form's sideways line, matching the ZPL form's `^FWR` rotated field stream, which is exactly the geometry shape of `_CN22_KEYWORD_PLACEMENT` (`width=49.1, height=7.6, rotation=90`).

### Non-circular Oracle Arithmetic

The PDF backend composites each overlay through `_merge_overlay`, which translates by `(anchor[0] - min_x, anchor[1] - max_y)` from `_rotated_corner_extents`.
At rotation 90 the rotated corners of a width x height rect give `(min_x, max_y) = (0, 0)`, so each overlay's merged `cm` translation equals its anchor in bottom-left PDF points.
The anchors are hand-computed from the probe and the A4 page, never read from the seed:

| Quantity | Derivation | Value |
|----------|-----------|-------|
| mm to points factor | `72 / 25.4` | 2.8346 pt/mm |
| A4 page height | 297 mm | 841.9 pt |
| Strip anchor translation-x | `mm_to_points(53.34)` | 151.2 pt |
| Strip anchor translation-y | `841.89 - mm_to_points(91.44)` = `841.89 - 259.20` | 582.7 pt |
| Date-split sub-anchor offset | `(0, -mm_to_points(49.11) * DATE_STRIP_FRACTION)` = `(0, -139.21 / 2)` | (0, -69.61) pt |
| Signature sub-anchor translation | `(151.2, 582.7 - 69.61)` | (151.2, 513.1) pt |

With a date supplied, the two overlays read downward from the strip's top-left anchor: the date leads with the strictly greater translation-y (582.7), the signature follows at 513.1.
Both overlays' linear parts encode the clockwise 90-degree rotation as a zero diagonal with `b < 0 < c` — the assertion that fails if the seed ever regresses to an upright encoding.
The fixture draws its own image, so the overlays are still isolated through the strip's band rather than a first-`cm`-per-stream read (the carrier's own transform would shadow it).
Expected literals are computed in the test from the probe numbers and A4's 297 mm height; the only values ever read from a seed object are none.

### Edge Cases

| Scenario | Expected Behavior | Handling |
|----------|-------------------|----------|
| Seed values change without a re-measurement | `TestDefaultRegistry` fails against the probe literals | By design: the oracle pins the measurement, not the seed |
| Upright-encoding regression (`rotation=0`, 7.62 x 49.11) | Linear-part assertions fail (diagonal nonzero) and the extent arithmetic no longer matches the probe | Oracle set pins both the rectangle and the orientation |
| Carrier re-vendors the CN22 form | Probe literals rot with the form | Comments name the probe; a re-vendor is a re-measurement with a revision bump by the existing rule |
| Future seed revision touches the fixtures suite | Text-layer test unaffected | Decoupled onto a neutral valid placement (task 1.4) |
| Fixture's own `cm` shadowing the overlays | Band isolation still required | Reuse of `_cms_in_y_band` scoped to the strip's translation region |

### Failure Modes

| What Can Go Wrong | Impact | Mitigation |
|-------------------|--------|------------|
| The probe strip itself is wrong | The seed lands on the wrong region again | It cross-checks the ZPL form at sub-dot precision (eight separator columns, rule spans, decoded landmarks) and the independently measured keyword seed agrees within dot rounding — two coordinate systems converging on one strip |
| Hand-computed oracle arithmetic contains an error | Oracles pin wrong translations | Values are derived in-test from the probe numbers with the arithmetic spelled out; the red-first run demonstrates the oracles catch revision 2, and the green run confirms exact agreement |
| Oracle literals mistaken for seed-derived values in future edits | Circularity re-enters | Comments in each oracle name the probe measurement as the literal source |
| Cross-module regression from the value change | Unrelated suites break | Both stamping suites plus `./bin/run-sdk-tests` gate the merge (task 3.1) |

---

## Implementation Plan

### Phase 1: PRD and failing tests

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| 1.1 This PRD | `PRDs/CN22_PDF_SEED_REMEASURE.md` | This document | M |
| 1.2 Rewrite `TestDefaultRegistry.test_cn22_seed_resolves_to_the_documented_anchor`: probe literals, spelled-out extent arithmetic, revision-3 pin; verify red against revision 2 | `modules/sdk/tests/core/test_document_stamping.py` | Pending | M |
| 1.3 Rewrite `TestCn22Seed.test_seed_composites_at_the_measured_anchor`: both overlays' `cm` translations hand-computed from the probe and A4 297 mm; keep paint-order and clockwise-linear-part assertions; verify red | `modules/sdk/tests/core/test_document_stamping.py` | Pending | M |
| 1.4 Replace the fixtures `_CN22_BAND_PT` band test with the probe-derived single-overlay translation; decouple `test_real_signature_preserves_the_text_layer` onto a neutral valid placement; verify the band test red | `modules/sdk/tests/core/test_document_stamping_fixtures.py` | Pending | M |
| 1.5 Correct the appendix B follow-up note to the `rotation=90` pre-rotation 49.11 x 7.62 encoding, pointing at this PRD | `PRDs/KEYWORD_ANCHORED_STAMPING.md` | Pending | S |

### Phase 2: seed correction

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| 2.1 Set `_CN22_PLACEMENT` to the probe values, bump `_CN22_SEED.revision` to 3, replace the known-defect comment block with the probe provenance and revision history; tasks 1.2-1.4 turn green, other stamping suites unchanged | `modules/sdk/karrio/core/utils/stamping.py` | Pending | S |

### Phase 3: verification

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| 3.1 Both stamping suites + `./bin/run-sdk-tests` with black clean, exit 0, no cross-module regressions; fresh-context review gate against the spec delta, this PRD, and `.claude/rules/prd-and-review.md` | — | Pending | S |

**Dependencies:** Phase 1 lands red, Phase 2 turns it green, Phase 3 gates the merge.
The openspec change `openspec/changes/cn22-pdf-seed-remeasure/` is authored on this branch; its delta archives in Phase 3.

---

## Testing Strategy

All tests use `unittest` (never pytest), run from the repository root with the repo venv.
Tasks 1.2-1.4 land red against the shipped revision-2 seed before task 2.1 turns them green — the red run is itself the verification that the oracles are no longer circular.

### Oracle Table

| Spec scenario | Test (file, task) | Asserted observable |
|---------------|-------------------|---------------------|
| ADDED: the CN22 PDF seed composites on the signature strip — registry resolution | `test_document_stamping.py`, `TestDefaultRegistry`, 1.2 | Registry-resolved placement equals the probe literals (x 53.34, y 91.44, width 49.11, height 7.62, rotation 90) with the rendered-extent arithmetic spelled out independently: extent x [x, x + height] = [53.34, 60.96] mm, y [y, y + width] = [91.44, 140.55] mm, label-relative left edge `x - 52.51` = 0.83 mm >= 0; the seed entry carries `revision == 3` as a pinned literal |
| ADDED: the CN22 PDF seed composites on the signature strip — compositing with a date | `test_document_stamping.py`, `TestCn22Seed`, 1.3 | Date overlay `cm` translation (151.2, 582.7) pt and signature overlay (151.2, 513.1) pt, computed in-test from the probe and A4's 297 mm height (never read from the seed); date translation-y strictly greater (paint order); both linear parts clockwise 90 (zero diagonal, b < 0 < c) — the sideways-reading AND clause |
| ADDED: the CN22 PDF seed composites on the signature strip — real fixture, image only | `test_document_stamping_fixtures.py`, band test rewrite, 1.4 | Single overlay's `cm` translation equals the probe-derived anchor (151.2, 582.7) pt; clockwise linear part assertions retained |
| ADDED: an extent leaving the form's target region is a defect — mechanically caught | tasks 1.2-1.4 red runs | The rewritten oracles fail against the shipped revision-2 seed (horizontal extent, label-relative left edge -19.96 mm) although page-level `_validate_pdf_extent` passes it — the demonstration that measurement-derived oracles catch what circular ones cannot |
| ADDED: an extent leaving the form's target region is a defect — future regressions | `test_document_stamping.py`, `TestDefaultRegistry`, 1.2 | The label-frame containment arithmetic (extent within [52.51, 157.50] x [53.53, 243.38] mm) is asserted in the oracle, so any future seed outside the form's region fails without runtime changes; correction path is re-measurement with a bumped revision, per the scenario |
| Revision supersession (AND clause of scenario 1) | `test_document_stamping.py`, `TestDefaultRegistry`, 1.2 | `_SEED_REGISTRY["postnord/cn22/PDF/A4"].revision == 3`, asserted as a literal |
| Unchanged behavior guards | both suites, 3.1 | The keyword registry tests, keyword-resolution tests, and the decoupled text-layer test stay green throughout Phase 2 |

### Running Tests

```bash
# rewritten oracles red against the shipped seed (after Phase 1)
.venv/karrio/bin/python -m unittest discover -v -f modules/sdk/tests -p "test_document_stamping*"

# green after task 2.1, plus the full gate (task 3.1)
.venv/karrio/bin/python -m unittest discover -v -f modules/sdk/tests -p "test_document_stamping*"
./bin/run-sdk-tests
```

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| The probe measurement is wrong | High | Low | Sub-dot cross-validation against the ZPL form plus the independently measured keyword seed agreeing within dot rounding |
| The corrected encoding renders upright instead of sideways | Medium | Low | The linear-part oracles (zero diagonal, b < 0 < c) and the extent arithmetic both fail an upright regression |
| Oracle literals rot on a re-vendored fixture | Medium | Low | Literal-bearing comments name the probe; a re-vendor is a re-measurement with a revision bump by the existing rule |
| Circularity re-enters through a later "consistency" edit | Medium | Low | The oracle table and the spec requirement state the derivation rule; the review gate checks it |
| Full-suite regression | Medium | Low | `./bin/run-sdk-tests` before any commit; the change touches no runtime code path |

---

## Migration and Rollback

### Backward Compatibility

- **API compatibility**: no API surface changes; `stamp_document` and the seed registry keep their shapes, and the PDF leg already resolves `seed.placement` unchanged.
- **Data compatibility**: no persisted data carries placements; `_SEED_REGISTRY` converts in-tree.
- **Consumers of the registry seed**: a consumer relying on the defective strip coordinates sees the stamp move to the measured strip; the registry-seeded PDF path is not live in production (owner decision 2026-09-24), and `revision=3` records the supersession for anyone tracking it.

### Rollback Procedure

1. Revert the commits; the seed values, revision, and oracles revert with them.
2. No data cleanup is required.
3. The openspec change archive and this PRD retain the measurement record for forensics.

---

## Appendices

### Appendix A: Mapping Validation Facts (Summary)

The primary record is appendix B of [KEYWORD_ANCHORED_STAMPING.md](KEYWORD_ANCHORED_STAMPING.md) (measurement run 2026-09-24); this appendix summarizes the facts the corrected seed rests on.

- The CN22 PDF carries the label form as a `/Form1` XObject with `BBox` 839.0 x 1518.0 dots at 203 dpi (105.0 x 189.9 mm), placed on the page by a pure translation with the label origin at page (52.51, 53.53) mm.
- Fonts use a `/Differences` cipher, so text positions decode through `extract_text`'s visitor.
- The PDF's vector separator columns (eight of them) land against the ZPL separators' integer dots, and the rule y-span [15.2, 694.9] against the `^FO10,15 ^GB820,680` form box — sub-dot agreement throughout.
- Decoded landmarks: the keyword field at label (25.00, 35.00) against `^FO20,35`, "Sweden Post" at (670.00, 35.00) against `^FO665,35`, the certification block at (130.00, 35.00) against `^FO25,35`.
- `^FO` semantics on this form: y is the line's reading start exactly; x anchors the descender-side bottom (baseline + descender, 5 dots at font size 20).
- The ZPL keyword seed resolves `^FO20,35` plus offset (-1.673, +33.529) mm to `^FO7,303`, with the pre-rotation 49.1 x 7.6 mm extent at 203 dpi rotating to the 61 x 392-dot strip (label x 7..68, y 303..695).
- The probe strip (page x [53.34, 60.96], y [91.44, 140.55] mm) maps to label x [6.63, 67.53], y [302.97, 695.44] — the same physical strip, within dot rounding, with its bottom edge on the form box's bottom rule.

### Appendix B: PDF Anchor Revision History

| Revision | Placement | Rendered extent | Provenance |
|----------|-----------|-----------------|------------|
| 1 | `(53.3, 91.4, 7.6, 49.1, 90)` under centre-pivot semantics | The archived probe strip's coordinates; superseded by the semantics change | Original hand measurement |
| 2 | `(32.55, 112.15, 7.6, 49.1, 90)` under corner-anchor semantics | Horizontal 49.1 x 7.6 mm at page x [32.55, 81.65], y [112.15, 119.75] — axis-swapped, ~19.96 mm off the label's left edge | Centre-preserving algebraic conversion of revision 1; defect measured 2026-09-24 (appendix B of the keyword PRD) |
| 3 | `(53.34, 91.44, 49.11, 7.62, 90)` under corner-anchor semantics | Vertical 7.62 x 49.11 mm at page x [53.34, 60.96], y [91.44, 140.55] — the measured signature strip | probe2b, cross-validated against the ZPL form at sub-dot precision; this change |
