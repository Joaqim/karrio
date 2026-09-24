## Context

See `proposal.md` for motivation. The shipped `_CN22_PLACEMENT` (revision 2: x=32.55, y=112.15, 7.6 x 49.1, rotation=90) renders a horizontal 49.1 x 7.6 mm strip mapping to label x [-159.5, 232.9] — about 19.96 mm off the label's left edge. The archived probe (probe2b: page x [53.34, 60.96], y [91.44, 140.55] mm — a vertical 7.62 x 49.11 mm strip) is correct and shares a centre with the shipped extent: revision 2's centre-preserving conversion `(x + (w-h)/2, y + (h-w)/2)` rotated the rendered extent 90 degrees about the revision-1 centre because the corner-anchor semantics change also changed what a given `(w, h, rotation)` renders as. The mapping is validated in `PRDs/KEYWORD_ANCHORED_STAMPING.md` appendix B (the CN22 PDF's `/Form1` XObject, eight separator columns, and rule spans agree with the ZPL form at sub-dot precision), and the ZPL keyword seed already pins the same physical strip on the label frame.

## Goals / Non-Goals

**Goals:**

- Correct the PDF seed to the measured vertical strip at page (53.34, 91.44), encoding it as `rotation=90` with a pre-rotation 49.11 x 7.62 extent, revision 3.
- Replace the circular band and seed-literal oracles with measurement-derived ones that would have caught the defect.
- Record the corrected encoding in the keyword PRD's appendix B follow-up note.

**Non-Goals:**

- No change to the ZPL keyword seed, keyword-anchored resolution, backends, bounds validation, or the date split (Q9 stays open).
- No page-level bounds validation change: the defective strip was inside the A4 mediabox, and tightening `_validate_pdf_extent` to know each form's target region is seed-authoring data, not backend logic — the on-form invariant lives in the spec and the oracles, not in runtime code.
- No re-measurement of any other seed.

## Decisions

### Encoding: rotation=90 with pre-rotation extent 49.11 x 7.62

`StampPlacement.width`/`height` are the image's dimensions before rotation and a nonzero rotation anchors the rotated extent's top-left at `(x, y)`. A vertical strip carrying sideways-reading content therefore encodes as `width=49.11, height=7.62, rotation=90` — the pre-rotation landscape rect rotates clockwise to the 7.62 x 49.11 vertical extent anchored at (53.34, 91.44), spanning page x [53.34, 60.96], y [91.44, 140.55] mm. This is exactly the geometry shape of `_CN22_KEYWORD_PLACEMENT` (width=49.1, height=7.6, rotation=90): both seeds pin the same physical strip in two coordinate systems. The appendix B follow-up note's "rotation 0" wording described the rendered rectangle's upright shape, not the placement encoding; rotation 0 with a 7.62 x 49.11 extent would render the signature upright, contradicting the `^FWR` reading the whole design aligns with. The rewritten oracle set pins the rotation through the overlay's linear part (zero diagonal, b < 0 < c), so an upright-encoding regression fails a test.

### Non-circular oracles derive from the probe, not the seed

`TestDefaultRegistry` asserts the registry-resolved placement against the probe literals (53.34, 91.44, 49.11, 7.62, rotation 90) with the rendered-extent arithmetic spelled out in the assertion, so a seed change without a re-measurement breaks it. `TestCn22Seed` and the fixtures band test assert the merged overlay's `cm` translation against hand-computed points from the probe: for rotation 90, `_rotated_corner_extents` yields (min_x, max_y) = (0, 0), so each overlay's translation equals its anchor — `(mm_to_points(53.34), 297 mm page height - mm_to_points(91.44))` for the strip's top, and the signature sub-anchor offset by `(0, -date_width)` under the date split. Expected literals (151.2 pt, 582.7 pt, and the split offset) are computed in the test from the probe numbers and A4's 297 mm height, never read from the seed object. The fixtures' text-layer test takes a neutral valid placement instead of pinning the seed "for consistency", so future seed revisions do not touch it.

### Revision 3

`revision` marks anchor supersession and nothing consumes it as a gate; the PDF placement is genuinely re-measured, so the revision bumps 2 -> 3. The ZPL keyword fields ride the same `StampSeed` object unchanged — additive data did not bump the revision before, and the keyword geometry is not being re-measured now.

## Risks / Trade-offs

- [The probe strip itself is wrong] → it cross-checks against the ZPL form at sub-dot precision (eight separator columns, rule spans, decoded text landmarks) and against the independently measured keyword seed; two coordinate systems agreeing on one strip is strong evidence.
- [Oracle literals rot if the fixture is re-vendored] → the pinned literals name the probe measurement in comments; a re-vendored form is a re-measurement (revision bump) by the existing rule.
- [Registry-seeded PDF path is not live in production] → the correction carries no deployment urgency; landing it now closes the loop while the measurement is fresh.

## Migration Plan

Value and test changes only; no code path, API, database, or dependency surface changes. Every keyword-anchored behavior is untouched. Rollback is revert of the commits; no data cleanup is required.
