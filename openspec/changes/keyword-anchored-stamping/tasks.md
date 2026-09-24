## 1. PRD and failing tests

- [x] 1.1 Write `PRDs/KEYWORD_ANCHORED_STAMPING.md` per the repo PRD-first rule — ASCII diagram of the placement/keyword/seed resolution chain, the locator scan, decisions from `design.md`, and the oracle table mapping spec scenarios to tests — referencing this openspec change
- [ ] 1.2 Add locator oracles to `modules/sdk/tests/core/test_document_stamping.py` (synthetic ZPL streams in inline and newline-separated command styles: a keyword match returns the nearest preceding `^FO` origin with float operands parsed, multiple matches take the first, and a miss raises naming the keyword), and verify they fail red against the shipped code
- [ ] 1.3 Add resolution-chain oracles (a keyword with a fully anchored placement raises; a keyword with a geometry-only placement resolves position from the form and extent/rotation from the placement; a keyword with no placement and no seed geometry raises naming the missing source; a keyword against a PDF document is rejected explicitly), and verify they fail red before the resolution change
- [ ] 1.4 Add registry oracles (a seeded ZPL document resolves implicitly via the seed's keyword; a consumer keyword outranks the seed's; a ZPL document with neither consumer input against a keyword-less seed keeps the registry-miss error naming the key; a keyword-absent call keeps today's behavior), and verify they fail red before the seed change
- [ ] 1.5 Add the PostNord fixture regression to `test_document_stamping_fixtures.py` — the CN22 ZPL form with keyword "Date and Sender's signature" resolves a deterministic placement with pinned `^FO` literals, and the single call with image and date composites one `^GFA` strip at the derived origin with the standing raster assertions — and verify it fails red against the shipped seed

## 2. Locator and resolution chain

- [ ] 2.1 Implement the `_locate_zpl_field` command-token scan (`^FD`/`^FS` blocks, nearest preceding `^FO`, float operands, first match wins, explicit miss error), and verify task 1.2 turns green
- [ ] 2.2 Thread `keyword` through `stamp_document`, `StampRequest`, and the `lib` re-export with the resolution chain and PDF rejection after format sniff, and verify tasks 1.3 and the PDF case turn green
- [ ] 2.3 Extend `StampSeed` with `keyword` and `keyword_placement` (extent, rotation, `dpi`, offset in `x`/`y`) and let `_default_registry` resolve ZPL seeds implicitly, and verify task 1.4 turns green with the keyword-absent suite unchanged

## 3. PostNord CN22 seed

- [ ] 3.1 Measure the CN22 keyword geometry and offset against the vendored form — cross-checked against the PDF seed's strip on the same CN22 layout — set the postnord seed's keyword and `keyword_placement`, and verify task 1.5 plus `TestDefaultRegistry`/`TestCn22Seed` pass on the pinned literals

## 4. Verification

- [ ] 4.1 Run both stamping suites and the full `./bin/run-sdk-tests` gate with black formatting clean, and verify exit 0 with no cross-module regressions; then pass the fresh-context review gate against the spec delta, PRD, and checklist in `.claude/rules/prd-and-review.md`
