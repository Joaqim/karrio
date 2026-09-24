## 1. Proposal

- [ ] 1.1 This openspec change and the PRD `PRDs/STAMP_RENDER_FIDELITY.md` land first (repo PRD-first rule).

## 2. Oracles

- [ ] 2.1 Red-first oracles in `modules/sdk/tests/core/test_document_stamping.py`, verified red against the shipped pipeline: date glyph band height within the fraction bound (today the full strip), date band aspect within tolerance of the natural font aspect (today stretched), zero isolated speckle pixels in the date region (today 152 on the CN22 geometry), long-date shrink-to-fit (today full-height regardless of length), uniform PDF date overlay scale (today ~0.22 sx/sy), faint-stroke connectivity (today fragmented). Rename `TestZplDitherContinuity` to `TestZplRasterContinuity` with wording matching the threshold pipeline; it stays green throughout.
- [ ] 2.2 Confirm the CN22 ZPL fixture reproduction improves: glyph band height ~13 dots (cap height at font size 18), zero isolated speckles, saved comparison crops.

## 3. Implementation

- [ ] 3.1 `modules/sdk/karrio/core/utils/stamping.py`: `_render_date_image` renders at the target sub-rectangle size on an opaque white ground with shrink-to-fit; `_build_zpl_raster` pastes the date directly, resamples the signature with LANCZOS, and binarizes with the fixed ink threshold; `stamp_pdf`'s date branch renders at the sub-rectangle's point aspect; `DATE_FONT_HEIGHT_FRACTION` and `ZPL_INK_THRESHOLD` constants; superseded docstring rationales replaced. Oracles from 2.1 turn green.

## 4. Verification and archive

- [ ] 4.1 Both stamping suites plus `./bin/run-sdk-tests` exit 0; `black` clean; no cross-module regressions.
- [ ] 4.2 Fresh-context review gate against this change, the PRD, and `.claude/rules/prd-and-review.md`.
- [ ] 4.3 Archive this change and sync `openspec/specs/documents/stamping/spec.md`.
