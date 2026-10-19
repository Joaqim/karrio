## Why

The shipped PostNord CN22 PDF seed (`_CN22_PLACEMENT`, revision 2) renders a horizontal 49.1 x 7.6 mm strip starting ~20 mm off the label's left edge — an axis-swapped fossil of the revision-1 centre-pivot seed that revision 2's algebraic conversion preserved in centre but not in rendered orientation (measured 2026-09-24, documented in `PRDs/KEYWORD_ANCHORED_STAMPING.md` appendix B). The registry-seeded PDF path is not live in production, so the correction carries no deployment urgency, but the seed is wrong and the band oracles that should have caught it were circular against the same anchor.

## What Changes

- Re-measure `_CN22_PLACEMENT` to the archived probe strip: `x=53.34, y=91.44, width=49.11, height=7.62, rotation=90` — a vertical 7.62 x 49.11 mm strip at page x [53.34, 60.96], y [91.44, 140.55] mm, matching the form's sideways-reading signature column and the measured ZPL keyword seed's geometry. Revision bumps to 3 (a genuine re-measurement).
- Correct the follow-up note in `PRDs/KEYWORD_ANCHORED_STAMPING.md` appendix B, which encodes the target as "rotation 0": a vertical strip carrying sideways-reading content requires `rotation=90` with a pre-rotation 49.11 x 7.62 extent under the shipped `StampPlacement` semantics (width/height are pre-rotation; the rotated extent anchors at `(x, y)`); rotation 0 with a 7.62 x 49.11 extent would render the signature upright against the form's `^FWR` reading.
- Rewrite `TestDefaultRegistry.test_cn22_seed_resolves_to_the_documented_anchor`, `TestCn22Seed.test_seed_composites_at_the_measured_anchor`, and the fixtures suite's `_CN22_BAND_PT` band oracle with non-circular oracles whose literals derive from the probe measurement (53.34 / 91.44 / 49.11 / 7.62 / A4 297 mm), not from the seed object.
- Decouple `test_real_signature_preserves_the_text_layer` from the seed (it currently pins the revision-2 anchor for "consistency"; any valid placement exercises the text layer the same way).
- Add a spec requirement under `documents/stamping`: a registry seed's placement composites within the carrier form's measured target region — the invariant whose absence let a broken seed pass review with circular oracles.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `documents/stamping`: ADDED requirement — seeded placements land on the carrier form's measured target region, with oracles that derive from the measurement rather than from the seed under test.

## Impact

- `modules/sdk/karrio/core/utils/stamping.py` — `_CN22_PLACEMENT` values, provenance comments, `_CN22_SEED.revision` 2 -> 3; no code-path changes (the PDF leg already resolves `seed.placement`).
- `modules/sdk/tests/core/test_document_stamping.py`, `modules/sdk/tests/core/test_document_stamping_fixtures.py` — oracle rewrites.
- `PRDs/KEYWORD_ANCHORED_STAMPING.md` — appendix B follow-up note corrected; new PRD `PRDs/CN22_PDF_SEED_REMEASURE.md` per the repo PRD-first rule.
- No API, database, dependency, or server-surface changes; the ZPL keyword seed and keyword-anchored resolution are untouched.
