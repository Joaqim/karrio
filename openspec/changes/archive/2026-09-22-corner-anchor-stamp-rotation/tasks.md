## 1. Failing tests first

- [x] 1.1 Add the incident regression to the fixture suite — `(0, 0, 70, 20, rotation=90)` at 203 dpi against the vendored CN22 ZPL form must emit `^FO0,0` with a 160x559-dot raster — and verify it fails red against the shipped centre-pivot code
- [x] 1.2 Add corner-anchor and bounds oracles to `modules/sdk/tests/core/test_document_stamping.py` (ZPL `^FO` stays the placement anchor, PDF `cm` translation lands the rotated corner, negative anchors and out-of-range operands raise), and verify they fail red before the backend change

## 2. Backends

- [x] 2.1 Re-anchor `stamp_zpl` rotation as rotate-then-anchor with the `^FO` operand-range guard (0–32000), and verify the rotation and incident tests turn green
- [x] 2.2 Re-anchor `_merge_overlay`/`stamp_pdf` rotation on the rotated bounding box with mediabox containment for rotated placements and the date-split tiling offset, and verify the PDF rotation, seed-band, and bounds tests turn green
- [x] 2.3 Add the shared `_validate_anchor` (negative anchors, positive dimensions) to both backends and update the `StampPlacement`/backend docstrings, and verify the negative-anchor tests name the offending field
- [x] 2.4 Re-express `_CN22_PLACEMENT` as `(32.55, 112.15, 7.6, 49.1, 90)` under `StampSeed` revision 2 and close the Q10 rotation-direction comment with the vendored-form evidence, and verify `TestDefaultRegistry` and `TestCn22Seed` pass on the converted literals

## 3. Fixtures

- [x] 3.1 Vendor the real signature (`signature_test.png`, 450x180 RGBA) and the real PostNord CN22 ZPL form (`postnord_cn22.zpl`) into `modules/sdk/tests/core/fixtures/`, and verify the fixture suite `test_document_stamping_fixtures.py` runs green in the default discovery path

## 4. Specification and verification

- [x] 4.1 Write `PRDs/DOCUMENTS_STAMPING_CORNER_ANCHOR.md` (decisions D1–D4, transform math, oracle table, migration) and this openspec change (proposal, design, tasks, spec delta)
- [x] 4.2 Run the stamping suites (100 tests) and the full `./bin/run-sdk-tests` gate, and verify exit 0 with no cross-module regressions
