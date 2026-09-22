# Corner-anchored stamp rotation

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-09-22 |
| Status | In Progress |
| Owner | Joaqim Planstedt |
| Type | Enhancement |
| Reference | [AGENTS.md](../AGENTS.md) |

---

## Executive Summary

Rotated stamp placements anchor by rotating about the placement rectangle's centre and re-anchoring to preserve that centre, in both the PDF and ZPL backends.
The intuitive reading — "x, y is where the rotated image's top-left corner lands" — is inexpressible under this model, and a valid-looking request emits out-of-spec negative `^FO` operands silently.
This PRD switches both backends to corner-anchored rotated extents, adds a bounds guard, and re-expresses the measured PostNord CN22 seed under the new semantics as `StampSeed` revision 2.

### Key architecture decisions

1. **Corner-anchored rotated extents, both backends**: rotate the image, then anchor the rotated extent's top-left at the placement's `x, y`.
   The anchor means the same thing in PDF points and ZPL dots, and a rotated strip can start at the page corner.
2. **Bounds guard on rotated placements**: reject placements whose anchor is negative or whose rotated extent leaves the printable area, instead of emitting invalid output.
   Unrotated placements keep their exact shipped behavior and bytes.
3. **Seed re-expression by algebra, revision 2**: the CN22 seed's physical strip is unchanged; only its parameterization converts from centre-pivot to corner coordinates.
4. **No compatibility shims**: per the change-management preference, no dual-mode flag or fallback; consumers re-express rotated anchors once.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| `stamp_zpl` rotation anchoring | Rotation direction (clockwise is confirmed correct; unchanged) |
| `stamp_pdf` rotation anchoring and date-split tiling | New registry seeds for other carriers |
| Bounds guard (anchor + rotated extent) | Guard for unrotated placements beyond operand limits (legacy behavior retained) |
| `_CN22_PLACEMENT` re-expression, revision 2 | Server serializer changes (`ValueError` already maps to 400) |
| openspec delta for `documents/stamping` | |
| Test oracle updates + incident regression test | |

---

## Open Questions & Decisions

### Resolved decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | Rotated-anchor semantics | Corner-anchored rotated extent in both backends | Centre-pivot cannot express a rotated strip at the page corner at all (requires negative x); selected by user | 2026-09-22 |
| D2 | Rotation direction (openspec Q10) | Clockwise, as shipped | Fixture geometry: the CN22 ZPL form's `^FWR` stream has glyph-up = page +x; a clockwise rotation matches that axis. An earlier "counter-clockwise/270" reading was a render misread and is retracted | 2026-09-22 |
| D3 | Guard scope | Anchor non-negativity and extent containment apply to rotated placements; `rotation=0` keeps shipped behavior and bytes | The shipped compat invariant is "no rotation changes nothing"; containment for unrotated stamps would newly reject legacy-valid requests | 2026-09-22 |
| D4 | Seed update method | Algebraic re-expression, `StampSeed.revision = 2` | The physical strip is identical; the parameterization converts exactly (see Technical Design) | 2026-09-22 |

### Edge cases requiring input

None remaining.

---

## Problem Statement

### Current state

```python
# stamping.py, stamp_zpl — centre-pivot re-anchoring
if rotation:
    width, height = raster.size
    center_x = x_dots + width / 2.0
    center_y = y_dots + height / 2.0
    raster = raster.rotate(-rotation, expand=True, fillcolor=1)
    rotated_width, rotated_height = raster.size
    x_dots = int(round(center_x - rotated_width / 2.0))
    y_dots = int(round(center_y - rotated_height / 2.0))
```

```python
# stamping.py, _merge_overlay — the same model in PDF transform space
if rotation:
    transformation = (
        transformation.translate(-width / 2.0, -height / 2.0)
        .rotate(-rotation)
        .translate(x + width / 2.0, y + height / 2.0)
    )
```

A live request against `POST /v1/documents/stamp` with placement `(0, 0, 70, 20, rotation=90, dpi=203)` on a PostNord CN22 ZPL form emitted `^FO200,-200` with a 160x559-dot raster.
The graphic occupied x 25–45 mm, y −25–+45 mm: shifted 25 mm right of the anchor and half clipped above the label.

### Desired state

```python
# stamp_zpl — rotate, then anchor the rotated extent at the placement
if rotation:
    raster = raster.rotate(-rotation, expand=True, fillcolor=1)

x_dots = mm_to_dots(placement.x, placement.dpi)
y_dots = mm_to_dots(placement.y, placement.dpi)
```

The same request then emits `^FO0,0` with the identical 160x559-dot raster: a 20x70 mm strip whose top-left sits exactly at the anchor.

### Problems

1. **Corner-anchoring is inexpressible**: for a w×h placement rotated 90 degrees, the rotated extent's left edge sits at `x + (w−h)/2`; with w=70, h=20 that is at least 25 mm right of the requested corner for any non-negative x.
2. **Silent out-of-spec output**: negative `^FO` operands (ZPL valid range is 0–32000) are emitted without complaint; Labelary clips forgivingly and physical printers behave inconsistently.
3. **The two backends must change together**: the placement vocabulary is documented as format-independent, so divergent anchor semantics between PDF and ZPL would multiply consumer branches rather than remove them.

---

## Goals & Success Criteria

### Goals

1. A rotated placement's `x, y` lands the rotated extent's top-left corner at that point, in both backends.
2. Any placement that would produce invalid or fully off-page output is rejected with a `ValueError` naming the violated bound (the server maps this to 400).
3. `rotation=0` output remains byte-identical to the shipped output.
4. The PostNord CN22 seed composites at the same physical strip as before, under revision 2.

### Success criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Incident placement `(0,0,70,20,90)` | emits `^FO0,0`, raster 160x559 dots | Must-have |
| Zero-rotation byte identity | shipped test stays green unchanged | Must-have |
| Negative-anchor or off-extent rotated placements | `ValueError` naming the bound | Must-have |
| Full SDK suite | exit 0 | Must-have |

### Launch criteria

**Must-have (P0):**

- [ ] ZPL corner anchoring + operand-range guard
- [ ] PDF corner anchoring (arbitrary angles via rotated bounding box) + mediabox containment for rotated placements
- [ ] Seed revision 2 with algebraically converted anchor
- [ ] openspec `documents/stamping` delta archived
- [ ] Failing-test-first incident regression in the fixture suite

**Nice-to-have (P1):**

- [ ] `^PW`/`^LL` parsing to extent-check ZPL against the declared label stock when present

---

## Alternatives considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Corner-anchored rotated extent, both backends + guard | Intuitive and expressible everywhere; `^FO` is always the anchor; spec stays format-independent | Breaking change for rotated placements; seed and test oracles must convert | **Selected** |
| Keep centre-pivot, add guard only | No shipped-behavior change; no seed re-measure | The user's goal stays inexpressible without counterintuitive coordinates (x=25 to land at visual 0); the surprise remains | Rejected |
| Corner anchoring in ZPL only | Smallest diff for the incident | Placement semantics diverge across formats, multiplying consumer branches | Rejected |
| Defer (fixtures only) | Zero risk now | Defect stays live on the deployed endpoint | Rejected |

### Trade-off analysis

The breaking surface is one rotation feature on a recently shipped utility with a single known deployment (the user's own API host) and one internal seed consumer.
There is no persisted data keyed on placement semantics — anchors live in requests and in `_SEED_REGISTRY` — so migration is a one-time re-expression rather than a data migration.
The change-management preference against compatibility shims applies cleanly: a dual-mode flag would cost more than the break it avoids.

---

## Technical Design

### Existing code analysis

| Component | Location | Reuse strategy |
|-----------|----------|----------------|
| Rotation branch (ZPL) | `modules/sdk/karrio/core/utils/stamping.py:366-373` | Replace centre math with rotate-then-anchor; `mm_to_dots` unchanged |
| Rotation transform (PDF) | `stamping.py:194-201` (`_merge_overlay`) | Replace centre-pivot translate/rotate/translate with rotate + corner translate |
| Date split | `stamping.py:228-244` (PDF), `_build_zpl_raster` (ZPL) | ZPL unaffected (date composited pre-rotation); PDF sub-rect tiling rule below |
| Registry seed | `stamping.py:481-498` (`_CN22_PLACEMENT`, `StampSeed`) | Re-express anchor, bump revision to 2, close the Q10 comment |
| Guard precedent | `stamp_zpl`'s underlay rejection, `stamp_document`'s backend rejection | Same `ValueError` style; server already maps to 400 |
| Tests | `modules/sdk/tests/core/test_document_stamping.py`, `..._fixtures.py` | Oracles updated per the testing strategy; band/seed literals recomputed |

### Anchor semantics, before and after

```
  placement (x=0, y=0, w=70, h=20, rotation=90, dpi=203)

  BEFORE — centre-pivot (shipped)      AFTER — corner-anchored (proposed)

  y 0 ───────────────────────────      y 0 ───────────────────────────
       │            ┌────────┐              ┌────────┐
       │            │        │              │        │
       │  off-label │ rotated│              │ rotated│
       │  (clipped) │ raster │              │ raster │
       │            │ 160x559│              │ 160x559│
       │            └────────┘              └────────┘
       │            x=200   x=360           x=0     x=160
       │            ^FO200,-200             ^FO0,0
       ▼                                        ▼

  rotated extent left edge = x+(w−h)/2       rotated extent top-left = (x, y)
  ≥ 25 mm for any x ≥ 0                      expressible at any corner
```

### Placement flow through the backends

```
            StampPlacement (x, y, w, h, rotation, dpi, page)
                          │
                          ▼
            stamp_document ── sniff format ── dispatch
                          │
            ┌─────────────┴──────────────────┐
            ▼ ZPL                            ▼ PDF
   validate anchor ≥ 0 mm             validate anchor ≥ 0 mm
   raster = dither(w×h dots)          rect = mm→pt, y-flip vs mediabox
   raster.rotate(-rotation)           R = rotate(-rotation) about origin
   ^FO = mm_to_dots(x, y)             translate = anchor − rotated-bbox min
   validate 0 ≤ ^FO, extent ≤ 32000   validate rotated bbox ⊆ mediabox
            │                                  │
            ▼                                  ▼
   ^FO..^GFA splice before ^XZ         merge_transformed_page
```

### PDF transformation math

For rotation r (degrees, visual clockwise; pypdf `rotate(-r)` as shipped), the scaled rect corners `(X,Y) ∈ {(0,0),(w,0),(0,h),(w,h)}` map under the rotation about the origin to `(X cos r + Y sin r, −X sin r + Y cos r)`.
With `min_x` and `max_y` the extrema of those mapped corners, the translation placing the rotated bounding box's top-left at the anchor is:

```python
translate(
    mm_to_points(placement.x) - min_x,
    page_height_pt - mm_to_points(placement.y) - max_y,
)
```

For r = 90 this reduces to `min_x = 0`, `max_y = 0`, giving translate `(pt(x), H − pt(y))` exactly.

The date split tiles under the same rule: both sub-rects share the full rect's `h`, so each sub-merge anchors its rotated extent at `(X₀, Y₀ + d)` where `(X₀, Y₀)` is the full rect's rotated top-left (visual coordinates) and `d` is the sub-rect's unrotated x-offset.
The date leads along the strip exactly as before; only the parameterization of the anchor changes.

### Seed conversion (revision 2)

The shipped centre-pivot seed `(53.3, 91.4, 7.6, 49.1, 90)` composites a rotated extent of `x ∈ [53.3−20.75, 53.3+7.6/2+20.75]`, `y ∈ [91.4−20.75, 91.4+49.1/2+20.75]` = `x ∈ [32.55, 81.65]`, `y ∈ [70.65, 119.75]` mm.
The corner-anchored placement producing the identical extent is:

```python
_CN22_PLACEMENT = StampPlacement(
    x=32.55, y=70.65, width=7.6, height=49.1, rotation=90
)
_SEED_REGISTRY = {
    "postnord/cn22/PDF/A4": StampSeed(placement=_CN22_PLACEMENT, revision=2),
}
```

The Q10 comment block is replaced by the confirmed finding: the CN22 ZPL form's `^FWR` stream reads with glyph-up = page +x, matching the clockwise convention, so the direction is closed and the revision bump documents the anchor re-expression only.

### Edge cases

| Scenario | Expected behavior | Handling |
|----------|-------------------|----------|
| `rotation=0` | Byte-identical shipped output | Rotation branch and guard skip the rotated path |
| Negative `x` or `y` | `ValueError` naming the field | Shared validation before dispatch |
| Rotated extent crosses the mediabox edge (PDF) | `ValueError` naming the bound | Rotated bbox containment check |
| Rotated extent operand exceeds 32000 (ZPL) | `ValueError` naming the operand | Post-rotation operand check |
| `^PW`/`^LL` absent from the ZPL stream | Skip stock containment (operand check still applies) | Regex probe returns `None` |
| Arbitrary angle (not a 90 multiple) | Rotated bounding box anchors at `(x, y)` | Trig-based bbox in the PDF math; PIL `rotate(expand=True)` in ZPL |
| `graphic_name` cache path | Same `^FO` anchoring on the `^XG` field | `^FO` computed once before the branch |
| Date + rotation (PDF) | Date leads the signature along the strip, both clockwise | Sub-rect tiling rule above |

### Failure modes

| What can go wrong | Impact | Mitigation |
|-------------------|--------|------------|
| A consumer's rotated anchor silently moves | Signature lands off-target | Breaking change is documented; seed revision 2 covers the known consumer |
| Guard too strict for a legit bleed-off-edge stamp | Request rejected | Containment applies to rotated placements only; D3 records the scope |
| Transform composition order bug (PDF) | Image lands mirrored or offset | Cm-matrix oracles assert linear part and translation independently |

---

## Implementation plan

### Phase 1: failing tests

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Incident regression: `(0,0,70,20,90)` must emit `^FO0,0` | `tests/core/test_document_stamping_fixtures.py` | Pending | S |
| Corner-anchor + guard unit tests (ZPL `^FO`, PDF cm translation, rejections) | `tests/core/test_document_stamping.py` | Pending | M |

### Phase 2: backends

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| ZPL rotate-then-anchor + operand guard | `stamping.py` (`stamp_zpl`) | Pending | S |
| PDF corner transform + containment guard + date tiling | `stamping.py` (`_merge_overlay`, `stamp_pdf`) | Pending | M |
| Shared anchor validation, docstring updates | `stamping.py` (`stamp_document`, `StampPlacement`) | Pending | S |
| Seed revision 2 + Q10 comment closure | `stamping.py` (`_CN22_PLACEMENT`) | Pending | S |

### Phase 3: specification

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| openspec change `2026-09-22-corner-anchor-stamp-rotation` (proposal, design, tasks, spec delta) | `openspec/changes/` | Pending | S |
| Rotation requirement rewording + bounds requirement | spec delta, later synced to `openspec/specs/` | Pending | S |

**Dependencies:** Phase 1 lands red, Phase 2 turns it green, Phase 3 documents the shipped behavior.

---

## Testing strategy

All tests use `unittest` (never pytest), run from the repository root with the repo venv.

### Oracle updates (existing tests)

| Test | Current oracle | New oracle |
|------|----------------|------------|
| `TestZplRotation.test_rotation_swaps_dimensions_and_preserves_center` | `^FO(320, 80)` centre-preserving | `^FO(160, 240)` = the placement anchor; raster 160 wide × 480 tall |
| `TestDefaultRegistry.test_cn22_seed_resolves_to_the_documented_anchor` | `(53.3, 91.4, ...)` | `(32.55, 70.65, 7.6, 49.1, 90)` |
| `TestCn22Seed.test_seed_composites_at_the_measured_anchor` | band y 443.0–583.0 pt | band y 502.0–642.0 pt (extent y 70.65–119.75 mm) |
| `TestPlacementRotation` | linear part only | linear part unchanged; translation asserts the corner |
| `test_zero_rotation_is_byte_identical_to_no_rotation` | byte identity | unchanged, must stay green |

### New tests

```python
def test_incident_placement_anchors_the_rotated_corner(self):
    # (0, 0, 70, 20, rotation=90) @203 dpi: ^FO is the anchor itself and the
    # raster is 160 wide x 559 tall -- the strip starts at the page corner.
    ...

def test_negative_anchor_is_rejected_naming_the_field(self):
    with self.assertRaises(ValueError) as ctx:
        stamping.stamp_zpl(_zpl_doc_b64(), stamping.StampRequest(
            image=..., placement=stamping.StampPlacement(x=-1.0, y=0.0, ...)
        ))
    self.assertIn("x", str(ctx.exception))
```

### Running tests

```bash
.venv/karrio/bin/python -m unittest discover -v -f modules/sdk/tests -p "test_document_stamping*"
./bin/run-sdk-tests
```

---

## Risk assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Breaking rotated placements for existing consumers | Medium | Low | Single known deployment; seed revision 2; PR documents the one-line re-expression |
| PDF transform regression (mirrored/offset image) | High | Medium | Cm-matrix oracles assert direction and translation independently |
| Guard rejects a legitimate placement | Low | Medium | Containment scoped to rotated placements (D3); error names the bound for easy diagnosis |
| Full-suite regression | Medium | Low | `./bin/run-sdk-tests` before any commit |

---

## Migration and rollback

### Backward compatibility

- **API compatibility**: unrotated placements are byte-identical; rotated placements must re-express `x, y` as the rotated extent's top-left (for 90 degrees: `x_new = x_old + (w−h)/2`, `y_new = y_old − (w−h)/2`).
- **Data compatibility**: no persisted data carries placements; `_SEED_REGISTRY` converts in-tree.
- **Feature flags**: none, per the change-management preference.

### Rollback procedure

1. Revert the backend commit; the seed re-expression reverts with it.
2. The openspec change archive records both semantics for forensics.
3. No data cleanup is required.

---

## Appendices

### Appendix A: incident record

`POST /v1/documents/stamp` (2026-09-22), document = PostNord CN22 ZPL, image = `Signature_test.png` (450x180 RGBA), placement `{"page":1,"x":0,"y":0,"width":70,"height":20,"rotation":90,"dpi":203}`, layer `overlay`.
Output graphic occupied x 25–45 mm, y −25–+45 mm on the rendered label (`^FO200,-200`, raster 160x559).
Vendored as `modules/sdk/tests/core/fixtures/{signature_test.png, postnord_cn22.zpl}` with the fixture suite `test_document_stamping_fixtures.py`.

### Appendix B: Q10 closure evidence

The real form (`fixtures/postnord_cn22.zpl`) runs its whole field stream under `^FWR`.
The header (`CUSTOMS DECLARATION`, `^FO740,35`) and the signature label (`Date and Sender's signature`, `^FO20,35`) are consistent with the known CN22 layout only when glyph-up = page +x — the form reads with the head tilted right, text running top-to-bottom in label coordinates.
The shipped clockwise rotation produces glyph-up = +x, so `rotation=90` aligns with the form; the earlier counter-clockwise reading is retracted.
