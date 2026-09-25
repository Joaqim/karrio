# Tasks

## 1. Branches and sandbox gate

- [ ] 1.1 Create worktrees `.worktrees/feat-postnord-customs-invoice` (branching from `feat-postnord-connector`) and `.worktrees/feat-dhl-freight-se-customs` (branching from `feat-dhl-freight-se-connector`) with `git -c submodule.recurse=false worktree add`, and verify both appear in `git worktree list` with the expected base commits
- [ ] 1.2 Add `verify_live.py` to this change directory, modelled on the archived `2026-09-21-postnord-customs-declaration/verify_live.py`, that books a parcel product (`postnord_parcel`) in the PostNord test environment with a hand-built `customsInvoice` (fields per the design table, credentials and EORI read from `POSTNORD_APIKEY` / `POSTNORD_EORI` by name only), and verify the script runs and prints PostNord's validation verdict without printing any secret
- [ ] 1.3 Gate: run the script and record the result in `docs/notes/postnord/customs-invoice-live-verification.md`; if PostNord rejects `customsInvoice` on a parcel booking, stop and revise the specs before any implementation task, otherwise verify the note records the accepted booking and whether a customs invoice without registration numbers is accepted

## 2. PostNord product groups and customs invoice builder

- [ ] 2.1 Add `LETTER_SERVICES` (tracked, tracked letter, export letter, varubrev, expressbrev, RR, RK, RL, RE, RQ, VV, AF) and the International Parcel code beside `CUSTOMS_DECLARATION_MAX_LINES` in `units.py`, and verify a unit test asserting every `ShippingService` member classifies as letter, International Parcel, or parcel product, with the letter set pinned
- [ ] 2.2 Implement `_customs_invoice` in `shipment/create.py` per the design field table (type from `commercial_invoice`, `invoiceExportDeclaration`, seller with `vatNo`, `partyIdentification`, `eoriNo`, buyer, `voec`/`ioss`, `invoiceNo` with reference fallback, `shippingDate`, procedure code 1000, detailed description, totals), selected for parcel products instead of CN22, and verify a unit test asserting the full booking request body for a parcel product with customs against a new `RequestData` fixture
- [ ] 2.3 Add the fail-fast checks for a parcel customs invoice without shipper `tax_id` and without both `customs.invoice` and `payload.reference`, and verify unit tests asserting the field errors name the missing field and `lib.request` is never called, plus a test asserting the reference fallback populates `invoiceNo`
- [ ] 2.4 Verify `commercial_invoice` typing with unit tests asserting COMMERCIAL for true and PROFORMA for false and omitted, including a `content_type="merchandise"` payload with the flag false still yielding PROFORMA
- [ ] 2.5 Migrate the existing tests that book `postnord_parcel` with customs (`test_create_shipment_customs_request`, the category, registration-number, line-limit, and rounding tests at `tests/postnord/test_shipment.py:227-508`) to a letter service where they exercise CN22 behaviour, and verify the connector suite passes with no CN22 assertion left on a parcel product

## 3. PostNord CN22 registration rule

- [ ] 3.1 Add the fail-fast check that a CN22 carries at least one of EORI, VOEC, or IOSS, raised as `lib.exceptions.FieldError` beside the existing guards, and verify unit tests asserting the field error and no HTTP call when all three are absent, and an unchanged request when any one is present
- [ ] 3.2 Add an EORI to `ExportLetterCustomsPayload` and any other CN22 fixture lacking registration numbers, remove or rewrite `test_create_shipment_customs_registration_numbers_empty_send_nothing` to assert the new failure, and verify the export-letter fetch tests (`test_shipment.py:891-1285`) pass unchanged in behaviour
- [ ] 3.3 Keep the customs invoice path free of the registration check unless task 1.3 established that PostNord rejects it, and verify a unit test asserting a parcel customs invoice without registration numbers is sent as-is (or, if 1.3 found rejection, update the spec delta first and test the fail-fast instead)

## 4. PostNord composed customs invoice retrieval

- [ ] 4.1 Widen the proxy trigger in `karrio/mappers/postnord/proxy.py` from "Export Letter with customs" to "Export Letter or parcel product with customs", keeping `onlyCustomsDeclarations`, printId-then-item-id keying, and fail-open, and verify unit tests with two mocked `lib.request` calls asserting the by-id request for a parcel booking and an `extra_documents` entry categorized `customsInvoice` in PDF and ZPL
- [ ] 4.2 Verify a unit test asserting a failing by-id call on a parcel booking keeps the shipment successful and reports the failure as messages
- [ ] 4.3 Update the consumer note on customs (`docs/notes/postnord/` alongside the existing customs declaration note) with the product-group rule, invoice field sources, fail-fast errors, and the composed invoice document, and verify the note's example payload matches a passing unit-test fixture

## 5. DHL Freight Sweden customs

- [ ] 5.1 Add `customsHandlingStandard`, `customsHandlingFullService`, `customsCustomersOwnDeclaration{customsId, customsClearanceInstruction}`, `customsJointDeclaration{sfid}`, and `voecSupplyVAT{vatId}` from the vendored `AdditionalServicesDTO` to `schemas/transport_instruction_request.json`, and verify `./bin/run-generate-on modules/connectors/dhl_freight_sweden` regenerates `AdditionalServicesType` with those members and the existing tests still pass
- [ ] 5.2 Map `customs.options.eori_number` to `CustomsDocument.eori`, apply `commercial_invoice` literally, and derive `transportMovement` from shipper versus recipient country, and verify updated unit tests including one asserting an invoice number with the flag false yields ProformaInvoice
- [ ] 5.3 Add the customs service options to `units.py` following the `doorstepDelivery{accessCode}` pattern and build them into additional services only when set, with `voecSupplyVAT` fed from `customs.options.voec_number`, and verify unit tests asserting no customs service without an option and each service's request shape when set
- [ ] 5.4 Add fail-fast checks for standard handling without EORI, own declaration without customs identifier, and joint declaration without SFID using the connector's `SHIPPING_SDK_FIELD_ERROR` error type, and verify unit tests asserting each field error and no HTTP call
- [ ] 5.5 Run `python -m unittest discover -v -f modules/connectors/dhl_freight_sweden/tests` and verify all tests pass

## 6. Integration verification

- [ ] 6.1 Run `python -m unittest discover -v -f modules/connectors/postnord/tests` and `./bin/run-sdk-tests`, and verify both pass
- [ ] 6.2 With explicit user approval immediately before running, book one PostNord production parcel with customs via a `verify_prod_probe.py` in this change directory, fetch the composed documents by printId, then cancel the booking, and verify the findings note records composition including `customsInvoice`, the retrieved document size and format, whether registration numbers were required, and the cancellation, with no key or EORI value recorded
- [ ] 6.3 Write `changelog.md` in this change directory listing the features and the three breaking changes from the proposal, and verify each breaking change names its migration
- [ ] 6.4 Run the fresh-context review gate against the specs, design, and repository checklists (karrio.lib usage, enums over hardcoded strings, no generated-file edits, test coverage), address findings, and verify the reviewer reports no blocking issue
- [ ] 6.5 Register both branches in the develop assembly script and regenerate `develop`, and verify the assembled `develop` passes both connector suites
