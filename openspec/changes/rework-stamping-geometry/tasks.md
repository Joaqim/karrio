# Tasks

Work on `feat-document-stamping` in `.worktrees/feat-document-stamping`, with one commit per group below.
Each task is test-first: write the test, run it and see it fail against the current code, implement, and run it green.
Fixtures are synthetic and built at test time in `modules/sdk/tests/core/stamping_helpers.py`; no captured carrier document is vendored.
SDK tests run with `python -m unittest discover -v -f modules/sdk/tests`, and server tests with `karrio test karrio.server.documents.tests`, both in the nix dev shell with import paths under the worktree.

## 0. Decision record

- [x] 0.1 Record the units, fit, page selection, bounds, compression, resources, paper, `cn23` and REST decisions in `PRDs/DOCUMENT_STAMPING.md`, replacing the last-label ZPL limitation, as `docs(prd): record stamping units, fit, page selection, bounds and compression decisions`

## 1. Placement units

- [x] 1.1 Add tests in `modules/sdk/tests/core/test_stamping_units.py`: a `px` ZPL placement at 203 dpi emits `^FO40,60` and a 400 x 140-dot graphic; a `px` PDF placement at 150 dpi lands at the literal `cm` for 72 pt, 144 pt, 144 x 36 pt; a `pt` placement anchors 1 in from the top-left; an omitted unit is byte-identical to `mm`; `in` raises naming `StampPlacement.unit`; a `px` geometry-only keyword placement converts its offsets
- [x] 1.2 Add `StampPlacement.unit` and `_normalize_units`, applied in `stamp_document`, `stamp_pdf` and `stamp_zpl`, and export the accepted units; commit `feat(sdk): accept mm, pt and px stamp placement units`

## 2. Aspect-preserving fit

- [x] 2.1 Add tests in `modules/sdk/tests/core/test_stamping_fit.py` with images generated at test time: a 400 x 100 image in a 40 x 20 mm PDF box draws 40 x 10 mm centred vertically (literal `cm` scale factors equal on both axes); a square image in a 40 x 10 mm box draws 10 x 10 mm against the left edge; the ZPL raster keeps the box's dot size with ink confined to the fitted rows and columns; the fit applies inside the signature share with a date; a rotated placement carries the fit offset through the rotation
- [x] 2.2 Fit uniformly in `_merge_overlay` and `_build_zpl_raster`, recompute the literals of existing oracles whose image aspect differs from the box from the fit rule, and commit `feat(sdk): fit stamp images to their box preserving aspect ratio`

## 3. ZPL format selection

- [x] 3.1 Add `two_format_zpl` to `stamping_helpers.py`, building a stream with a nested header `^XA` in the second format and `^FX` text between the formats and after the last, plus variants without the final `^XZ` and with the formats swapped
- [x] 3.2 Add tests in `modules/sdk/tests/core/test_stamping_zpl_pages.py`: the default page splices before the first `^XZ`; page 2 splices before the second with every other byte unchanged; an unterminated second format is closed after the field; trailing `^FX` text is not a format, so page 2 of a one-format stream raises naming the count; page 3 raises; `stamp_document(page=2)` restricts a keyword search to the second format and applies a seed placement there; `page` with a fully anchored placement still raises
- [x] 3.3 Enumerate formats, retire `StampRequest.zpl_format` in favour of the resolved `page`, update the ZPL tests that assumed the last format, and commit `feat(sdk): select the zpl format a stamp lands in by page`

## 4. Page and label bounds

- [x] 4.1 Add tests in `modules/sdk/tests/core/test_stamping_bounds.py`: unrotated and rotated PDF rectangles past each mediabox edge raise naming the edge; a rectangle ending exactly on the edge passes; ZPL rectangles past `^LL` and past `^PW` raise before the raster is built; `^LL` and `^PW` set in an earlier format apply to a later one; a stream without `^PW` checks the length only and one without `^LL` the operand range only; a seed keyword geometry with negative offsets resolving inside the page passes
- [x] 4.2 Replace `_validate_pdf_extent`'s rotated-only use with a check of every final rectangle, add the ZPL label check, remove the permissive-extent test, and commit `feat(sdk): reject stamp placements outside the page or label`
- [x] 4.3 Add a server test that an out-of-page placement answers 400 naming the edge, in the same commit
- [x] 4.4 Add tests in `test_stamping_bounds.py` that `stamp_document` raises `ValueError` for a placement with only `x`, with only `y` (naming the missing field), and for a geometry-only placement without a keyword (naming the keyword), against PDF and ZPL and with a seed registered for the key, so no registry fallback stamps; then add the check beside the keyword-contradiction check and commit `feat(sdk): reject partial stamp placement geometry`
- [x] 4.5 Add tests that a keyword beside a placement offsets the located anchor by `x` only, by `x` and `y`, and by `px` offsets, restore `test_geometry_only_placement_offsets_add_to_the_located_origin`, limit the partial-geometry rejection to placements without a keyword, and commit `feat(sdk): accept consumer offsets alongside a stamp keyword`

## 5. Z64 compression

- [x] 5.1 Add tests in `modules/sdk/tests/core/test_stamping_z64.py`: without `compression` the output is byte-identical to a literal hex golden; with `z64` the header keeps the uncompressed totals, the inflated base64 equals the hex golden's bytes, and the CRC equals a CRC-16/XMODEM computed by an independent reference implementation in the test (check value `31C3` for `123456789`); `gzip` raises naming the accepted values; `z64` with `graphic_name` emits `~DY{name},A,G,{total},{bpr},:Z64:{data}:{crc}` whose inflated data equals the hex golden's bytes, with the `^XG` recall unchanged
- [x] 5.2 Add `compression` to `StampRequest`, `stamp_zpl` and `stamp_document`, and commit `feat(sdk): emit z64-compressed zpl stamp graphics on request`
- [ ] 5.3 Decode one inline `^GFA` Z64 output and one `~DY` Z64 download recalled with `^XG` on Labelary or a printer, and record both results in design.md

## 6. Per-page resources

- [x] 6.1 Add a shared-resources two-page PDF to `stamping_helpers.py`, built from `blank_pdf_b64`, and a test that stamping page 2 leaves page 1's resource keys equal to the input's while page 2 gains the image, plus an inherited-resources variant
- [x] 6.2 Give the stamped page a private resources copy in `stamp_pdf`, and commit `fix(sdk): keep a stamp on its page when pdf pages share resources`

## 7. Paper detection per page

- [x] 7.1 Add tests: a PDF whose page 1 is A4 and page 2 letter, under an `acme` plugin with seeds for both variants, resolves the letter seed with `page=2` and with a consumer keyword found only on page 2, and the A4 seed without either
- [x] 7.2 Measure the paper on the stamped page in `stamp_document`, and commit `fix(sdk): detect the stamp paper variant on the stamped page`

## 8. CN23 classification

- [x] 8.1 Add tests in `test_stamping_classification.py` with synthetic `acme` markers: a lone CN23 in ZPL and PDF classifies as `cn23`; a label with a CN23 on page 2 as `label_cn23`, page 2; both CN22 and CN23 markers raise naming both; every existing `cn22` case is unchanged
- [x] 8.2 Add the `cn23` declaration kind and its combined type, export them through `karrio.lib`, and commit `feat(sdk): classify cn23 customs declarations`
- [x] 8.3 Export `STAMP_COMPRESSIONS` through `karrio.lib` beside `STAMP_UNITS`, and commit `feat(sdk): export the accepted stamp compressions`

## 9. REST fields

- [x] 9.1 Add server tests in `modules/documents/karrio/server/documents/tests/test_stamping.py`: a keyword with a width/height-only placement stamps ZPL with 201; `unit="px"` with `compression="z64"` returns a Z64 graphic at the pixel extent; only one of `x`/`y` answers 400; a placement without `x`/`y` and no keyword answers 400 naming the keyword; `page=2` stamps the second ZPL format; an unknown unit or compression answers 400
- [x] 9.2 Add `unit`, optional `x`/`y`, `keyword` and `compression` to the serializers and the view, and commit `feat(documents): accept stamp units, keywords and compression over rest`

## 10. Integration

- [ ] 10.1 Run the SDK and documents suites in the nix dev shell with import paths under the worktree, and the SDK suite in `python:3.12-slim-bookworm`
- [x] 10.2 Update `apps/www/docs/reference/guides/document-stamping.mdx` for units, fit, ZPL pages, bounds, compression and `cn23`, as `docs(documents): document stamping units, fit and zpl pages`
- [ ] 10.3 Run `docs/notes/workflow/rebuild-develop.sh`; pushing stays the user's decision
