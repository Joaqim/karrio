# DHL Freight (SE API Farm) Phase 0 — code review

Branch: dhl-sweden-connection. Scope: modules/connectors/dhl_freight/. Read-only; no files modified. Tests: 14/14 pass.

## Phase 0 deliverables

- One-click label purchase via book->print: YES. proxy.py:26 books POST {transport_instruction_url}/transportinstruction/sendtransportinstruction; proxy.py:39 prints POST {print_url}/print/printdocuments from the booking-echoed shipment (proxy.py:44). Single shipment/create call.
- base64 label in the shipment response: YES. create.py:66 docs=Documents(label=report.content); label_type inferred from contentType (create.py:45-58).
- tracking number + tracking URL in the shipment response: YES. create.py:44,63 tracking_number = instruction.id; create.py:68 meta.carrier_tracking_link = settings.tracking_url.format(tracking_number).

## Item verdicts

- #2 transport_instruction.id path: CORRECT. Reads nested transportInstruction.id (create.py:24,37-44 -> TransportInstructionType.id, transport_instruction_response.py:50,69), not top-level booking["id"].
- #3 totalNumberOfPieces/totalWeight trim: BENIGN. print-api-2.10.0.json PrintOptions and Shipment schemas both have required=[]; neither dropped field is required by /print/printdocuments. The stderr "unknown arguments {...}" is a jstruct warning from trimming to print.ShipmentType (proxy.py:44), cosmetic.
- #4 productCode/postalCode string-cast: CORRECT on booking request (create.py:123 str(service), create.py:209 str(postal_code), create.py:70 str(productCode)). One gap on the print echo path (see Low finding).
- #5 client_key secret handling: DEFECT (Medium). Held as credential, never in a body, but NOT redacted from stored traces/telemetry.
- #7 cancel stub + shipping-only capability: CORRECT. cancel.py:24-31 returns code="not_supported", never fake success; Proxy exposes only create_shipment, so cancel/tracking/rating capabilities absent (plugin/__init__.py:17-33).
- #8 account_number: str = None typing: MATCHES house style (ups/utils.py:13 identical). Not an issue.
- #9 entrypoint-load ERROR origin: PRE-EXISTING / ENV-WIDE, not dhl_freight. "Failed to load entrypoint plugin" reproduces identically for ./bin/cli plugins show seko; dhl_freight loads cleanly with full metadata.

## Severity-ranked findings (no Critical or High)

### MEDIUM - client-key secret not redacted in stored traces/telemetry
Live check: _is_sensitive_header('client-key') returns False (redaction.py:21-49,75-80). helpers.py:189-195 records request_headers into the trace; tracing.py:414-415 redacts via that function, so the key is persisted in plaintext in TracingRecord. The OTel/Sentry span set (helpers.py:369-384) lists client-secret/client_secret but omits client-key. Every shipment call passes trace=self.trace_as("json") with the client-key header.
Failure scenario: anyone with org-scoped trace access or telemetry-backend access reads a reusable API secret, defeating a control built to prevent secret-at-rest exposure.
Fix (shared SDK, hand-editable, not generated): add "client-key"/"client_key" to SENSITIVE_HEADER_NAMES (redaction.py:21) and to the hardcoded set in helpers.py:369; add a test_redaction case.

### LOW-MEDIUM - print op deviates from PRD default without recorded rationale
PRD decision 1 (PRDs/PRD_DHL_FREIGHT_INTEGRATION.md:89) names printdocumentsbyid {shipmentIds:[id]} as default; proxy implements full-payload fallback (proxy.py:39-53), justified as "no by-id request type in the generated schemas" (proxy.py:16-19). That is a generation-scope choice, not an API limit: the vendored spec defines PrintOptionsById { shipmentIds }. Chosen approach may be safer (no reliance on server-side id persistence) but is undocumented and untested live.
Fix: regenerate PrintOptionsById and use by-id, OR amend the PRD decision to record full-payload was deliberately chosen and why.

### LOW - print-path productCode/postalCode not string-cast
proxy.py:44 echoes the booking dict through print.ShipmentType, whose productCode (print_request.py:61) and AddressType.postalCode (print_request.py:34) are Optional[int] though the spec types them string. No str() guard on this path (unlike booking). Low risk since values are DHL's own echoed data; untestable without sandbox.

### LOW - partial-failure edge: booking success + print failure yields details with empty label
Guard is instruction.get("id") (create.py:26), so ShipmentDetails is built with docs.label="" (create.py:66, report is None) plus the print error message. A caller checking docs.label truthiness could treat a billed-but-unlabelled shipment as success. Acceptable for Phase 0 happy path; consider surfacing this state explicitly.

## Verdict: APPROVED
Phase 0 is functionally complete and spec-compliant. Conventions clean (no legacy DP/SF/NF, no bare except, no hardcoded codes in create/proxy, generated schemas/mapper untouched). Only the Medium client-key trace-redaction gap warrants a fix before handling real credentials; the rest are Low follow-ups.
