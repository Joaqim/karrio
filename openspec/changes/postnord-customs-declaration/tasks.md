## 1. Schema generation

- [x] 1.1 Extend `modules/connectors/postnord/schemas/shipment_request.json` with the customs branches (`customsDeclarationCN22`, `customsDeclarationCN23`, `customsInvoice` and their nested definitions, lifted from `vendor/booking.swagger.json` SW:5176+, 5320+, 5411+, 5461+, 5942-6036) on the shipment entries, and verify `./bin/run-generate-on modules/connectors/postnord` regenerates with the customs types present on the shipment request model
- [x] 1.2 Add `schemas/customs_declaration_request.json` (declaration envelope: `ids[]` with `idType`, one-of CN22/CN23/customsInvoice branches, `updateIndicator`) and `schemas/customs_declaration_response.json` (`bookingResponseCN` with per-id `OK|FAIL` status, `labelPrintout`), plus the `ids_label` request fragment for `/v3/labels/ids/{pdf,zpl}`, and verify the regenerated modules import cleanly and round-trip a sample declaration payload via `lib.to_dict`

## 2. Booking-time customs carriage (design D1, D5)

- [ ] 2.1 Implement the unified-customs → `customsDeclarationCN22` mapping (field table in design.md) in the shipment request builder, and verify a new unit test asserting the full booking request body for a payload with customs matches an expected `RequestData` fixture
- [ ] 2.2 Verify bookings without customs keep the exact pre-change request shape by leaving all existing `test_shipment.py` request assertions unmodified and green
- [ ] 2.3 Add the `CUSTOMS_DECLARATION_MAX_LINES = 13` pre-submission guard to the booking path, and verify a unit test asserting a 14-line payload fails with a field error naming the limit and `lib.request` is never called

## 3. Implicit standalone customs document for UX (design D2)

- [ ] 3.1 Parse `printoutComposition` in `_extract_details` and carry the non-zero document kinds into the parsed result, and verify a unit test against the existing response fixture asserts the composed kinds (cn22 etc.) are extracted
- [ ] 3.2 Add the post-booking by-id fetch to `create_shipment` in `karrio/mappers/postnord/proxy.py`: when the booked service is `postnord_export_letter` and customs data was present, call `POST /v3/labels/ids/pdf` with the first assigned item id and `definePrintout=onlyCustomsDeclarations`, and attach returned printouts as `docs.extra_documents` entries with category from `printoutComposition` and format PDF, and verify a unit test with two mocked `lib.request` calls asserts the second call's URL/query and the populated `extra_documents`
- [ ] 3.3 Reuse `_printout_base64` raw-UTF-8 re-encoding for the ZPL variant and verify a unit test booking with `label_type=ZPL` asserts the `/v3/labels/ids/zpl` path and a ZPL-format `ShippingDocument`
- [ ] 3.4 Make the by-id fetch fail-open: booking stays successful and the retrieval failure is reported as messages, and verify a unit test with a failing second mocked call asserts the shipment result plus error messages and no exception

## 4. Post-booking declaration proxy (design D3)

- [ ] 4.1 Create `karrio/providers/postnord/customs.py` with the declaration request builder (enforcing `ids[]` maxItems 1, exactly one branch, and the 13-line guard) and parsers for the digital and PDF-variant responses (`bookingResponseCN` statuses; PDF variant additionally maps `labelPrintout` → `ShippingDocument` list with caller-supplied `paperSize`/`rotate`/`multiPDF` params), and verify unit tests for request building and both response parsings
- [ ] 4.2 Add proxy methods `create_customs_declaration` and `create_customs_declaration_pdf` following the `find_service_points` precedent, and verify unit tests (patched `lib.request`) assert endpoint URLs, methods, bodies, and parsed results, including an upstream rejection surfaced as unified error messages
- [ ] 4.3 Verify the 13-line guard applies to the proxy path with a unit test asserting the field error and no HTTP call for an over-limit declaration
- [ ] 4.4 Document consumer usage (invocation via `gateway.proxy.create_customs_declaration(...)`, branch choice, consumer-owned correctness) in `docs/notes/` following the service-points PRD pattern, including the string-passing convention for digit-coerced schema fields (never `int()`-coerce; leading-zero and alphanumeric values must pass through) and the `BuyerType`-union caveat for party construction, and verify the note exists with a runnable example

## 5. Verification and release prep

- [ ] 5.1 Run the full connector suite `python -m unittest discover -v -f modules/connectors/postnord/tests` and verify all tests pass, then `./bin/run-sdk-tests` to confirm no cross-connector regressions
- [ ] 5.2 Live-verify in the PostNord test environment: book `UX` with customs and confirm the CN22 appears in `printoutComposition`, the by-id `onlyCustomsDeclarations` fetch returns a real PDF and ZPL printout, and a 14-line declaration is rejected; record findings in `docs/notes/`
- [ ] 5.3 Add the changelog entry (Features) noting that customs data is no longer dropped at booking and that `UX` bookings now return a standalone customs document
- [ ] 5.4 Run the fresh-context review gate against the spec, design, and repo checklists (PRD compliance, test coverage, karrio.lib usage, tenant isolation, no hardcoded strings) and address findings
