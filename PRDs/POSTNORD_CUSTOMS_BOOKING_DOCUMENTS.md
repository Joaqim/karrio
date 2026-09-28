# PostNord customs booking documents

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-09-28 |
| Status | In Progress |
| Owner | Joaqim Planstedt |
| Type | Enhancement (breaking for export letter consumers) |
| Reference | [AGENTS.md](../AGENTS.md); [PRD_POSTNORD_INTEGRATION.md](./PRD_POSTNORD_INTEGRATION.md); [POSTNORD_CN22_STAMPING.md](./POSTNORD_CN22_STAMPING.md); [DOCUMENT_STAMPING.md](./DOCUMENT_STAMPING.md); fork readers: the openspec change `stamp-embedded-customs-forms` on the `docs-openspec` branch |

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Open Questions & Decisions](#open-questions--decisions)
3. [Problem Statement](#problem-statement)
4. [Goals & Success Criteria](#goals--success-criteria)
5. [Alternatives Considered](#alternatives-considered)
6. [Technical Design](#technical-design)
7. [Edge Cases & Failure Modes](#edge-cases--failure-modes)
8. [Implementation Plan](#implementation-plan)
9. [Testing Strategy](#testing-strategy)
10. [Risk Assessment](#risk-assessment)
11. [Migration & Rollback](#migration--rollback)

---

## Executive Summary

PostNord's booking endpoint composes the international letter label and the CN22 into one printout in both PDF and ZPL, and the connector returns that printout unchanged as `docs.label`.
This PRD covers the booking side of the customs documents: verifying the returned label's composition with the SDK classifier, and making the standalone customs document an opt-in for every CN22-bearing service in both formats.
The connector-side section markers and stamp seeds are covered by [POSTNORD_CN22_STAMPING.md](./POSTNORD_CN22_STAMPING.md), the classifier by [DOCUMENT_STAMPING.md](./DOCUMENT_STAMPING.md).

### Key Architecture Decisions

1. **Verification is a warning, never a failure**: a label that does not classify as a label composed with a CN22 is returned unchanged with a `postnord_unexpected_label_composition` warning, because the label remains valid and post-booking customs verification is the consumer's responsibility.
2. **Verification runs in the parser**: the ctx already carries `customs_declared` and `basic_service_code`, and the parser holds the decoded label, so no extra call or proxy state is needed.
3. **One classifier**: the parser calls `lib.classify_customs_composition` with PostNord's `DOCUMENT_SECTIONS` rather than re-deriving the rules.
4. **Standalone customs documents are opt-in**: `postnord_standalone_customs_documents` (bool, default false) is read from shipment `options`, falling back to the connection config entry of the same name, and is never an `additionalServiceCode`.
5. **The booking call is unchanged**: it keeps PostNord's default `definePrintout`, so PDF and ZPL bookings yield the same document set.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| Booking-time label composition verification for CN22-structured services, both formats | Requesting another `definePrintout` on the booking call |
| Opt-in standalone CN22 (`onlyCustomsDeclarations` by id) for every CN22-structured service, including 91 | Customs-invoice parcel products (their standalone fetch is unchanged) |
| README documentation of the composed label, the warning, and the opt-in | `declarationOnly` post-booking calls; CN23 for service 91 |

---

## Open Questions & Decisions

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | Where verification runs | Shipment response parser | The parser sees the decoded label and the ctx; the proxy stays a transport | 2026-09-28 |
| D2 | Warning code | Constant `POSTNORD_UNEXPECTED_LABEL_COMPOSITION`, value `postnord_unexpected_label_composition` | Mirrors `CUSTOMS_OMITTED_INTRA_EU` (upper-case constant, lower-case value) | 2026-09-28 |
| D3 | Opt-in placement | Shipment `options` key, connection config fallback, not a `ShippingOption` | Every truthy `ShippingOption` member is sent as an `additionalServiceCode` | 2026-09-28 |
| D4 | Opt-in gate | Every service whose `customs_structure` is `cn22` | UX, the other CN22 letters, and 91 follow one flow | 2026-09-28 |
| D5 | Unclassifiable label format | Warning naming the classifier's error | A classifier `ValueError` must not fail a booking that PostNord accepted | 2026-09-28 |

---

## Problem Statement

### Current State

The export letter (UX) fetches a standalone CN22 by default, while service 91 and the other CN22 letters never do, and nothing checks that the returned label actually carries the CN22 PostNord reports composing.
The earlier convention that PDF labels and declarations are separate while ZPL combines them was karrio's, not PostNord's.

### Desired State

| Booking | `docs.label` | `extra_documents` | Messages |
|---------|--------------|-------------------|----------|
| CN22 service, customs, default | composed label + CN22 | none | composition warning only on mismatch |
| CN22 service, customs, opted in | composed label + CN22 | standalone `cn22` in the label's format | composition warning on mismatch; retrieval failures |
| Customs-invoice parcel product | composed printout | standalone `customsInvoice` (unchanged) | retrieval failures (unchanged) |
| No customs, or within the EU VAT area | plain label | none | unchanged |

### Problems

| Problem | Impact |
|---------|--------|
| PDF and ZPL flows differ by service | Formats are not interchangeable |
| UX receives a duplicate CN22 by default | Double printing; 91 gets none |
| No composition check | A label missing its CN22 goes unnoticed until the consumer stamps it |

---

## Goals & Success Criteria

| Metric | Target |
|--------|--------|
| Combined label (PDF or ZPL) | No composition warning |
| Plain label, lone CN22 as label, PDF without CN22 text | One `postnord_unexpected_label_composition` warning, label unchanged, booking successful |
| No customs or EU VAT area | Messages identical to the pre-change output |
| Opt-in off | One HTTP call, no standalone document |
| Opt-in on | By-id `onlyCustomsDeclarations` fetch in the label's format, document kind `cn22` |
| Same CN22 letter booked in PDF and ZPL | Equal composition, document kinds, and messages |

---

## Alternatives Considered

| Alternative | Pros | Cons | Decision |
|-------------|------|------|----------|
| Fail the booking on a composition mismatch | Loud | The booking is already made and not cancellable; the label is valid | Rejected |
| `definePrintout=onlyLabels` for PDF bookings | Separate documents | Formats become non-interchangeable; rests on the removed convention | Rejected |
| Opt-in as a `ShippingOption` member | Typed option | Sent to PostNord as an `additionalServiceCode` | Rejected |
| Keep the UX default fetch | Not breaking | Duplicate CN22; UX and 91 diverge | Rejected |

---

## Technical Design

### Existing Code Analysis

| Component | Location | Reuse |
|-----------|----------|-------|
| Booking request ctx | `karrio/providers/postnord/shipment/create.py` (`shipment_request`) | Adds the resolved opt-in beside `customs_declared` and `basic_service_code` |
| Connector-local option precedent | `entry_code` read from `payload.options` | Same reading path for the opt-in |
| Connection defaults | `units.ConnectionConfig` (`offer_export_letter`) | Adds the opt-in fallback |
| Standalone fetch gate | `karrio/mappers/postnord/proxy.py` (`create_shipment`, `_get_customs_printouts`) | Gate widened to CN22 structure plus opt-in; fetch unchanged |
| Customs branch selection | `units.customs_structure`, `CustomsStructure.cn22` | Identifies the CN22 services, 91 included |
| Warning precedent | `_customs_omitted_message`, `CUSTOMS_OMITTED_INTRA_EU` | Same message shape |
| Classifier and sections | `lib.classify_customs_composition`, `providers/postnord/stamping.py` (`DOCUMENT_SECTIONS`) | Called with the sections injected |

### Architecture Overview

```
Caller        create.py (request)          Proxy                      PostNord
  | ShipmentRequest |                        |                            |
  +---------------->| customs_declared,      |                            |
  |                 | basic_service_code,    |                            |
  |                 | standalone_customs_    |                            |
  |                 | documents (options ->  |                            |
  |                 | connection config)     |                            |
  |                 +----------------------->| POST /v3/edi/labels/{fmt} ->|
  |                 |                        |<-- label + CN22 printout ---+
  |                 |                        | customs_declared and       |
  |                 |                        |  (cn22 and opted in        |
  |                 |                        |   or customs invoice)?     |
  |                 |                        +- POST /v3/labels/ids/{fmt} >|
  |                 |                        |  onlyCustomsDeclarations   |
  |                 |                        |<-- labelPrintout[] --------+
  |                 |   create.py (parser)   |                            |
  |                 |<-----------------------+ ctx + customs results      |
  |                 | customs_declared and cn22?                          |
  |                 |   classify docs.label with DOCUMENT_SECTIONS        |
  |                 |   not label_with_declaration -> warning             |
  | ShipmentDetails (label unchanged, extra_documents) + messages         |
  |<----------------+                        |                            |
```

---

## Edge Cases & Failure Modes

| Scenario | Behavior |
|----------|----------|
| Label classifies as `none` or `declaration` | Warning naming expected and classified composition; label unchanged |
| Classifier raises for an unsupported format | Warning naming the error; booking unaffected |
| Booking allocated no ids | No shipment, no verification, no fetch |
| Opt-in on, by-id fetch fails (error body, per-id failure, transport) | Booking successful; failure reported as messages |
| Opt-in given as the string `"false"` | Treated as false |
| Service 91 label wording differs from the letter label | Classifies as lone `cn22` and warns; revisited after live captures |

---

## Implementation Plan

| Task | Commit | Files |
|------|--------|-------|
| 3.1 | `feat(postnord): add unexpected label composition warning code` | `karrio/providers/postnord/units.py`, `tests/postnord/test_shipment.py` |
| 3.2, 3.3 | `feat(postnord): verify booking label customs composition` | `karrio/providers/postnord/shipment/create.py`, `tests/postnord/test_shipment.py` |
| 3.4 | `docs(postnord): document the composed booking label` | `README.md` |
| 4.1 | `feat(postnord): resolve the standalone customs documents opt-in` | `units.py`, `shipment/create.py`, test file |
| 4.2 | `feat(postnord): make standalone cn22 documents opt-in` | `karrio/mappers/postnord/proxy.py`, `README.md`, test file |
| 4.4, 4.5 | `test(postnord): ...` | test file |

Paths are relative to `modules/connectors/postnord/`.

---

## Testing Strategy

`modules/connectors/postnord/tests/postnord/test_shipment.py`, unittest, mocked `lib.request`.
Combined labels are the live fixtures `postnord_label_cn22_printid.pdf` and `postnord_label_cn22_booking.zpl`; the lone CN22 is `postnord_cn22.zpl`.

| Area | Covers |
|------|--------|
| Verification | ZPL combined, ZPL plain, ZPL lone CN22, PDF combined, PDF without CN22 text; label unchanged in every case |
| No verification | No customs and EU VAT area, both formats, messages equal to the pre-change output |
| Opt-in resolution | Options key, connection fallback, options overriding the connection, never an `additionalServiceCode` |
| Opt-in fetch | PDF and ZPL for UX and 91 opted in; no fetch when not opted in |
| Interchangeability | The same CN22 letter in PDF and ZPL, with and without opt-in |
| Retrieval failure | Opted-in PDF and ZPL fetch failures leave the booking successful |

```bash
python -m unittest discover -v -f modules/connectors/postnord/tests
python -m unittest discover -v -f modules/sdk/tests
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| UX consumers relied on the default standalone CN22 | Medium | Medium | Breaking-change note; set the opt-in on the connection |
| Booking-call printouts differ from the by-id captures | Low | Low | Warning only; live booking captures per change task 5.1 |
| PostNord renames markers | Low | Low | Warnings surface it; one constant to update |

---

## Migration & Rollback

Consumers that need the standalone CN22 set `postnord_standalone_customs_documents` in the connection config or per shipment in `options`.
Rollback is reverting the commits, which restores the default UX fetch and removes the warning.
