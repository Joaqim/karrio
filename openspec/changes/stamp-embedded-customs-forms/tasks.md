# Tasks

Branch placement follows design.md Migration Plan: group 1 on `feat-document-stamping`, group 2 on `feat-postnord-cn22-stamping`, groups 3-4 on `feat-postnord-customs-invoice`, which is stacked on `feat-postnord-cn22-stamping`.
Tests run in the nix dev shell per `docs/notes/workflow/nix-dev-shell-worktrees.md`, from each branch's worktree.

## 0. Branch readiness

- [x] 0.1 Base `feat-postnord-customs-invoice` on `feat-postnord-cn22-stamping` (which contains `feat-document-stamping`) so the booking check can import the SDK classifier and PostNord section markers; `BRANCHES` already orders cn22-stamping before customs-invoice. Done 2026-09-28: rebased 10 commits onto `f33ddaec5` with identical patches per `git range-diff`; pre-rebase tip kept as `backup/feat-postnord-customs-invoice-pre-cn22-rebase` (`22a0b936d`)
- [x] 0.2 (SDK part done in `feat-document-stamping`'s `PRDs/DOCUMENT_STAMPING.md`; PostNord stamping part goes in a new `PRDs/POSTNORD_CN22_STAMPING.md` on `feat-postnord-cn22-stamping`; booking part on `feat-postnord-customs-invoice`) Add or amend the upstream PRD as the first commit on each affected feature branch, covering classification, the combined seeds, and the opt-in standalone documents; verify each PRD has the ASCII flow diagram and file-path plan required by `PRDs/TEMPLATE.md`

## 1. SDK customs composition classification (`feat-document-stamping`)

- [x] 1.1 Add the `PluginMetadata.document_sections` field (per format: ZPL field-comment markers, PDF page-text markers, keyed by composed kind) and a lookup helper modelled on `_carrier_seeds`; verify a unit test resolves declared sections for a test carrier and an empty result for an undeclaring carrier
- [x] 1.2 Implement the pure classifier returning composition, composed kinds, stamp `doc_type` (`cn22` / `label_cn22` / none) and PDF page index, with ZPL marker matching; verify unit tests for lone, combined, and no-customs ZPL using synthetic markers, and that the input bytes are unchanged
- [x] 1.3 Add PDF classification by per-page text extraction with pypdf; verify unit tests for combined, lone, and no-marker-text PDFs built in-test, including a multi-page PDF naming the correct page index
- [x] 1.4 Reject unsupported formats with an explicit error naming the detected format; verify a test with a PNG input
- [x] 1.5 Export the classifier and result type through `karrio.lib` and document classify-then-stamp usage in the stamping module docstring; verify `python -m unittest discover -v -f modules/sdk/tests` passes
- [x] 1.6 Add an optional page override to the stamp entry point so a seeded placement is applied on the page named by classification (combined PDF CN22 page); verify a test stamping a multi-page PDF on page 2 under a page-1 seed, and that omitting the override keeps the seed's page

## 2. PostNord sections, fixtures, and combined seeds (`feat-postnord-cn22-stamping`)

- [x] 2.1 Add the live captures as fixtures: `~/Documents/postnord_cn22_and_shipment_label.zpl` and `probe2c_printid_zpl.zpl` (combined ZPL), `probe1b_printid_unrestricted.pdf` (combined PDF), `probe2b_printid_onlyCustomsDeclarations.pdf` (lone PDF); verify each fixture's structure (single `^XZ` and markers for ZPL, single A4 page and extractable text for PDF) in a fixture-integrity test mirroring `test_cn22_zpl_fixture_is_the_pristine_rotated_form`
- [x] 2.2 Declare PostNord's `document_sections` in `providers/postnord/stamping.py` (`^FX CUSTOMS_CN22_ROTATED^FS`, `^FX SE_INTERNATIONAL_LETTER_LABEL^FS`, PDF `CUSTOMS DECLARATION`/`CN22` and letter-label text) and wire them in `plugins/postnord/__init__.py`; verify the classifier returns the spec's expected results for every fixture in 2.1 and the existing lone ZPL CN22 fixture
- [x] 2.3 Register `label_cn22/ZPL/*` reusing the CN22 keyword and offset; verify stamping the combined ZPL fixtures yields the same placement as the lone CN22 and the label section (from `^FX SE_INTERNATIONAL_LETTER_LABEL^FS` to `^XZ`) is byte-identical
- [x] 2.4 Measure the CN22 signature strip on the combined `probe1b` page and register `label_cn22/PDF/A4` with that placement; verify with an oracle derived from the measurement (not the seed) that the stamp lands within the measured region on page 1 and the page count is unchanged
- [x] 2.5 Verify the existing `cn22/ZPL/*` and `cn22/PDF/A4` seeds are unchanged in revision and resolution; `python -m unittest discover -v -f modules/connectors/postnord/tests` passes with the pre-existing CN22 stamping tests untouched

## 3. Booking-time verification (`feat-postnord-customs-invoice`)

- [x] 3.1 Add the `POSTNORD_UNEXPECTED_LABEL_COMPOSITION` warning code in `units.py` beside `CUSTOMS_OMITTED_INTRA_EU`; verify it is importable and unique among PostNord message codes
- [x] 3.2 In the shipment response parser, classify the decoded label when customs was declared and `customs_structure(service) == cn22`, appending a warning naming expected and classified compositions on mismatch; verify tests for ZPL combined (no warning), ZPL plain label (warning), ZPL lone CN22 as label (warning), PDF combined (no warning), PDF without CN22 text (warning), each returning the shipment with the label unchanged
- [x] 3.3 Verify no classification or warning runs for bookings without customs or within the EU VAT area, in both formats, by tests asserting identical messages to the pre-change output
- [x] 3.4 Update the PostNord connector README/docstring section on customs documents to state that `docs.label` is the composed printout in both formats and describe the warning; verify the documented composition matches `meta.printout_composition` in the tests

## 4. Opt-in standalone customs documents (`feat-postnord-customs-invoice`)

- [x] 4.1 Read `postnord_standalone_customs_documents` from `payload.options` with a `ConnectionConfig` fallback of the same name (default False), without adding it to `ShippingOption`; verify a request-building test that the option never appears in `additionalServiceCode`
- [x] 4.2 Gate the proxy's by-id `onlyCustomsDeclarations` fetch on the resolved opt-in and widen it to every service with `customs_structure(service) == cn22` (UX, other CN22 letters, 91), in the label's format; verify proxy tests for opted-in PDF and ZPL (fetch made, `cn22` document attached) and not-opted-in (no fetch, no standalone document)
- [x] 4.3 Keep customs-invoice parcel products on their current fetch path; verify the existing customs-invoice tests pass unchanged
- [x] 4.4 Verify format interchangeability with a paired test booking the same CN22 letter in PDF and ZPL (with and without opt-in) and asserting equal composition, document kinds, and messages
- [x] 4.5 Verify a retrieval failure with opt-in set leaves the booking successful and reports messages, for both formats
- [x] 4.6 No changelog entry: per user decision 2026-09-28 the feature has never been merged upstream or promoted, so the fork is the only consumer and no breaking-change note is required

## 6. Live-verification follow-up: PDF keyword anchoring and alternative markers (design D7)

- [x] 6.1 SDK (`feat-document-stamping`): allow a section kind to declare alternative marker sets (any fully matching set marks the kind present); verify unit tests where only the second set matches, and that existing single-set declarations classify unchanged
- [x] 6.2 SDK (`feat-document-stamping`): keyword-anchored placement for PDF using page-text positions (origin and text direction) on the requested page or the first page containing the keyword, from caller geometry or seed PDF keyword geometry; keep coordinate-only PDF seeds unchanged; verify tests for a rotated and an upright keyword, no-match and no-text errors, and page override interplay
- [x] 6.3 PostNord (`feat-postnord-cn22-stamping`): add the two-page booking PDF fixture, declare the tracked letter label marker set as an alternative, and switch `label_cn22/PDF/A4` to PDF keyword geometry measured against both the single-page and two-page captures; verify classification (page 2 for the two-page PDF) and in-region stamps for both captures with oracles derived from measurement
- [x] 6.4 PostNord (`feat-postnord-customs-invoice`): verify a PDF booking returning the two-page fixture passes verification without a warning; update the PRDs touched by D7
- [x] 6.5 Restack, rebuild and push `develop` for redeploy (develop `8f6d9af93`, 2026-09-28); the UX PDF re-run is tracked under 5.1.2

## 5. Live verification and integration

- [ ] 5.1 Capture live booking-call printouts (not by-id) for export letter UX and service 91 in PDF and ZPL, with and without opt-in, saving to `$XDG_STATE_HOME/agent-logs/karrio/`; verify each classifies as combined and no composition warning is emitted (bookings are not cancellable; unshipped test bookings are not billed)
  - [x] 5.1.1 2026-09-28: `postnord_export_letter` (UX), ZPL, no opt-in, on develop `4e08591d6`: live booking returned a single ZPL document containing CN22 and label, and `printoutComposition` reported `cn22` + `label` (user-confirmed)
  - [ ] 5.1.2 UX, PDF, no opt-in. 2026-09-28 sandbox (not live): booking returned one PDF with two pages (CN22 and label on separate pages) and `printoutComposition` `cn22` + `label`; contradicts the single-page assumption from the by-id `probe1b`; pending fixture capture, classification/stamp verification, and spec/design amendment
  - [ ] 5.1.3 UX, PDF and ZPL, opted in (`postnord_standalone_customs_documents`)
  - [ ] 5.1.4 Service 91, PDF and ZPL
- [ ] 5.2 Record the capture results and any marker or layout differences in `docs/notes/postnord/` on `docs-openspec`; if 91 differs from UX, return to the specs before archiving
- [x] 5.3 Regenerate `develop` with `assemble-develop.sh` and run the SDK, PostNord, and documents stamping test suites on it; verify all pass and `develop-status.sh --fetch` is clean
- [x] 5.4 Run a fresh-context review against the specs and `.claude/rules/prd-and-review.md`; verify findings are resolved or recorded
