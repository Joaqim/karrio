## Context

A live `POST /v1/documents/stamp` request with placement `(0, 0, 70, 20, rotation=90, dpi=203)` on a PostNord CN22 ZPL form emitted `^FO200,-200` with a 160x559-dot raster: the graphic sat 25 mm right of the anchor and half-clipped above the label.
Both backends rotated about the placement rectangle's centre and re-anchored to preserve that centre, so the intuitive reading — the anchor is where the rotated image's top-left lands — was inexpressible, and the resulting negative `^FO` operand was emitted silently as out-of-spec ZPL.
The full incident record, alternatives table, and risk assessment live in `PRDs/DOCUMENTS_STAMPING_CORNER_ANCHOR.md`; this design records the technical decisions behind the shipped behavior.

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Corner-anchored rotated extents in both backends | The anchor means the same thing rotated or upright and stays format-independent; a rotated strip can start at the page corner |
| D2 | Rotation stays clockwise | The vendored CN22 ZPL form's `^FWR` field stream reads with glyph-up = page +x, matching the shipped clockwise convention; the earlier counter-clockwise reading is retracted (closes design Q10) |
| D3 | Guard scope: anchor validation is universal; containment is scoped | Negative anchors and non-positive dimensions are invalid in every backend; PDF mediabox containment applies to rotated placements only, so `rotation=0` keeps its shipped permissive behavior and bytes |
| D4 | Seed re-expression by algebra, `StampSeed.revision = 2` | The CN22 seed's physical strip is unchanged; only its parameterization converts from centre-pivot to corner coordinates |

## Anchor semantics

```
  placement (x=0, y=0, w=70, h=20, rotation=90, dpi=203)

  BEFORE — centre-pivot               AFTER — corner-anchored

  y 0 ─────────────────────────       y 0 ─────────────────────────
       │            ┌────────┐            ┌────────┐
       │  off-label │ rotated│            │ rotated│
       │  (clipped) │ raster │            │ raster │
       │            │ 160x559│            │ 160x559│
       │            └────────┘            └────────┘
       │            x=200   x=360         x=0     x=160
       │            ^FO200,-200           ^FO0,0
```

Under centre-pivot the rotated extent's left edge sits at `x + (w-h)/2` — at least 25 mm right of the requested corner for w=70, h=20 and any non-negative x.
Under corner-anchoring the rotate happens first and the rotated extent's top-left lands on `(x, y)` directly.

## PDF transform

For rotation r (degrees, visual clockwise; pypdf `rotate(-r)` as shipped), the scaled rect's corners `(X, Y)` map under rotation about the origin to `(X cos r + Y sin r, -X sin r + Y cos r)`.
With `min_x` and `max_y` the extrema of the mapped corners, the translation placing the rotated bounding box's top-left at the anchor is `translate(pt(x) - min_x, H - pt(y) - max_y)`, which for r=90 reduces to `(pt(x), H - pt(y))` exactly.
The date split tiles under the same rule: the date sub-rect anchors at the full anchor and the signature sub-rect at the anchor offset by `(d cos r, -d sin r)` where d is the date strip's unrotated width, so the date still leads along the strip.

## ZPL anchoring

The raster is rotated first (`rotate(-rotation, expand=True)`), then `^FO` is `mm_to_dots(x), mm_to_dots(y)` directly — the placement anchor is the field origin, with no re-derived centre.
Because `^FO` and graphic operands are valid only from 0 to 32000 dots, the origin and extent operands are checked after the rotation and a violation raises naming the operand.
The `graphic_name` cache path shares the same `^FO`, computed before that branch.

## Seed conversion (revision 2)

The shipped centre-pivot seed `(53.3, 91.4, 7.6, 49.1, 90)` composites the extent `x in [32.55, 81.65]`, `y in [70.65, 119.75]` mm; the corner-anchored placement producing the identical extent is `(32.55, 70.65, 7.6, 49.1, 90)`, shipped as revision 2.
For 90 degrees generally, a consumer re-expresses an old anchor as `x_new = x_old + (w-h)/2`, `y_new = y_old - (w-h)/2`.

## Migration

Breaking for rotated placements only; unrotated placements are byte-identical.
No persisted data carries placements — anchors live in requests and `_SEED_REGISTRY` — so migration is a one-time consumer re-expression, and no compatibility shim ships, per the change-management preference.
The server already maps backend `ValueError` to a 400 response, so no serializer change is needed.
