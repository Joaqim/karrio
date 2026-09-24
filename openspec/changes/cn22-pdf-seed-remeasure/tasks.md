## 1. PRD and failing tests

- [ ] 1.1 Write `PRDs/CN22_PDF_SEED_REMEASURE.md` per the repo PRD-first rule — ASCII diagram of the A4 page, label frame, and measured strip showing both seeds' coordinate systems converging on one physical strip, the defect mechanics (centre preserved, orientation not), the corrected `rotation=90` encoding with the appendix B "rotation 0" correction, and the oracle table mapping spec scenarios to tests — referencing this openspec change
- [ ] 1.2 Rewrite `TestDefaultRegistry.test_cn22_seed_resolves_to_the_documented_anchor` to assert the probe literals (53.34, 91.44, 49.11, 7.62, rotation 90) with the rendered-extent arithmetic spelled out independently of the seed object, and verify it fails red against the shipped revision-2 seed
- [ ] 1.3 Rewrite `TestCn22Seed.test_seed_composites_at_the_measured_anchor` to assert both overlays' `cm` translations against values hand-computed from the probe numbers and the A4 page height (never read from the seed), keeping the paint-order and clockwise-linear-part assertions, and verify it fails red
- [ ] 1.4 Rewrite the fixtures suite's `_CN22_BAND_PT` band test to assert the single overlay's translation against the probe-derived anchor, and decouple `test_real_signature_preserves_the_text_layer` onto a neutral valid placement; verify the band test fails red
- [ ] 1.5 Correct the appendix B follow-up note in `PRDs/KEYWORD_ANCHORED_STAMPING.md` to the `rotation=90` pre-rotation 49.11 x 7.62 encoding, pointing at the new PRD

## 2. Seed correction

- [ ] 2.1 Set `_CN22_PLACEMENT` to `StampPlacement(x=53.34, y=91.44, width=49.11, height=7.62, rotation=90)`, bump `_CN22_SEED.revision` to 3, replace the known-defect comment block with the probe provenance and the revision history, and verify tasks 1.2-1.4 turn green with the rest of the stamping suites unchanged

## 3. Verification

- [ ] 3.1 Run both stamping suites and the full `./bin/run-sdk-tests` gate with black formatting clean, and verify exit 0 with no cross-module regressions; then pass the fresh-context review gate against the spec delta, the PRD, and the checklist in `.claude/rules/prd-and-review.md`
