# PRD: DHL Freight integration

| Field | Value |
|-------|-------|
| Project | DHL Freight carrier connector (`dhl_freight`) |
| Version | 1.1 |
| Date | 2026-08-11 |
| Status | Planning |
| Owner | Joaqim Planstedt |
| Type | Integration |
| Reference | [AGENTS.md](../AGENTS.md), [CARRIER_INTEGRATION_GUIDE.md](../CARRIER_INTEGRATION_GUIDE.md) |

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
11. [Appendices](#appendices)

---

## Executive Summary

Add a `dhl_freight` connector targeting the DHL Freight Sweden API Farm, covering shipment booking (with label) and a tracking link.
The connector composes two API Farm services — the Transport Instruction API (booking) and the Print API (label) — into Karrio's single `shipment/create` contract, and surfaces a URL-only tracking link.
It is used for domestic Swedish freight in our deployment and also supports international products to and from Sweden; DHL's own API validation remains authoritative, so no geographic gate is imposed.

The two DHL front doors are the same underlying DHL Freight API.
The DHL Group Developer Portal (`api.dhl.com`, OAuth2 bearer tokens, a Unified Shipment Tracking API) is one path; the DHL Freight Sweden API Farm (`freight-logistics.dhl.com`, a single `client-key` header, no token exchange) is the other.
Phase 0 targets the API Farm exclusively, as documented by the vendored OpenAPI 2.10.0 specs.

### Key architecture decisions

1. **`shipment/create` chains book then print (approach A).**
One proxy method books via `POST /transportinstruction/sendtransportinstruction`, captures the assigned `transportInstruction.id`, then calls the Print API and returns a merged `{ booking, print }` payload.
This preserves Karrio's expectation that create returns a label in one step.
The exact print operation (`POST /print/printdocumentsbyid` with `{ shipmentIds: [id] }`, or full-payload `POST /print/printdocuments`) is TBD, resolved during schema analysis.
2. **Authentication is a single `client-key` HTTP header.**
Every request to every API Farm service sends `client-key: <api-key>`.
There is no token exchange, no `authenticate` step, and no token cache; the vendored specs declare an `apiKey` security scheme named `client-key`, `in: header`, on each API.
This removes the OAuth2 client-credentials flow, the Basic-to-Bearer exchange, and the ~30-minute JWT cache that the DHL Group Portal path would require.
3. **Booking is shipment creation in one call.**
`POST /transportinstruction/sendtransportinstruction` creates the shipment and returns its `transportInstruction.id`; no prior Product API call is required to book.
4. **Tracking is URL-only, no network call.**
The shipment-create response returns a tracking number (`transportInstruction.id`), and `shipment/create` stamps `meta.tracking_url` built from a DHL Freight Sweden portal template.
The API Farm has no tracking endpoint, so no `TrackingRequest` to `TrackingDetails` round-trip is possible against it.
A full Karrio tracking feature is deferred to a later phase (it would use the DHL Unified Shipment Tracking API on the DHL Group gateway, a different front door and credential); `tracking.py` is not wired in Phase 0.
5. **No rating in Phase 0.**
The API Farm exposes a Price Quote API, but rating is out of scope for Phase 0 and is deferred; omitting `get_rates` from the proxy leaves the `rating` capability absent automatically.
6. **No cancel or returns in Phase 0.**
Shipment cancellation and returns are out of scope; `cancel.py` remains a documented stub and no `cancel_shipment` is wired.
7. **Label layout is selectable; raster format (PDF/ZPL) is not an API parameter.**
The Print API models label page layout via `ReportOptions.pageOptions.pageType` (`Label`, `Label2xPortraitA4`, `Label3xLandscapeA4`, `LabelCompact`, `LabelCompact2x2PortraitA4`); default `Label`.
The Print API 2.10.0 exposes no raster-format field, so PDF-versus-ZPL is governed by DHL account configuration, not by a request parameter.
A per-connection `label_type` setting (default `PDF`) tags and interprets the returned label bytes so they align with the account's configured output; it is account-aligned metadata, not an API request parameter.
This raster-format treatment is provisional pending user confirmation of any out-of-band DHL mechanism.
8. **API host is per-connection overridable.**
The default host is the API Farm — test `https://test-api.freight-logistics.dhl.com`, production `https://api.freight-logistics.dhl.com` — selected by `test_mode`, with a `connection_config.server_url` override.
Each API's base path (`/transportinstructionapi/v1`, `/printapi/v1`, `/productapi/v1`, ...) is appended to the resolved host.
9. **Phase 0 verification is Karrio's mocked four-method unittest pattern.**
No live sandbox credentials are required; all Phase 0 tests are hermetic.

### Scope

| In scope | Out of scope |
|----------|--------------|
| Shipment booking (`POST /transportinstruction/sendtransportinstruction`) | Rating / price quotes (Price Quote API deferred) |
| Label retrieval (Print API, op TBD) | Live tracking events (`TrackingRequest` to `TrackingDetails`) |
| `client-key` header authentication | Shipment cancellation / returns |
| Tracking link + tracking id (URL-only, via shipment meta) | Pickup, manifest, service-point / home-delivery locator lookups |
| `productCode` services + `payerCode` / label-layout options | Dangerous goods, temperature-controlled, ADR (later phase) |
| Domestic and international products (no geo gate) | PDF-vs-ZPL request-time selection (account-governed) |

---

## Open Questions & Decisions

### Pending questions

| # | Question | Context | Options | Status |
|---|----------|---------|---------|--------|
| 1 | Which print operation to use | Booking returns an id; the Print API offers by-id and full-payload variants. | (a) `printdocumentsbyid` with `{ shipmentIds: [id] }` — default; (b) `printdocuments` full payload | Default (a); confirm exact op during schema analysis |
| 2 | Correct public tracking-URL template for DHL Freight Sweden | Tracking is URL-only; the template lives in `utils.py`. | (a) a DHL Freight Sweden portal template; (b) an `activetracing.dhl.com` variant | Confirm with DHL Freight Sweden docs |
| 3 | Locator reference for service-point / home-delivery products | 103 / 401 / 109 may require an `AccessPoint` / `Delivery` party with a `subType` (`Servicepoint`) and a locator id. | (a) caller supplies the reference; (b) drop 103/401/109 from the fixture set | If it cannot be caller-supplied, drop the three; 102/232/202 still cover the pipeline |

### Resolved decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| 1 | Target gateway | DHL Freight Sweden API Farm | Phase 0 target; vendored 2.10.0 specs | 2026-08-11 |
| 2 | Auth model | Single `client-key` header, no token exchange | API Farm specs declare `apiKey` `client-key` in header on every service | 2026-08-11 |
| 3 | Create flow | Approach A: book then print, chained in `create_shipment` | Preserves one-step "create returns label" | 2026-08-11 |
| 4 | Tracking scope | URL-only via shipment meta; full tracking deferred | API Farm has no tracking endpoint; full feature uses a different gateway | 2026-08-11 |
| 5 | Rating | Not implemented in Phase 0 | Price Quote API deferred beyond Phase 0 | 2026-08-11 |
| 6 | Cancel / returns | Not implemented in Phase 0; `cancel.py` a documented stub | Out of scope for Phase 0 | 2026-08-11 |
| 7 | Label layout | Expose `pageType` layout; default `Label` | Print API models page layout, not raster format | 2026-08-11 |
| 8 | Raster format (PDF/ZPL) | Not a request parameter; account-governed; `label_type` setting tags returned bytes | Print API 2.10.0 has no raster-format field | 2026-08-11 |
| 9 | Geographic gating | None | DHL API validation is authoritative; international implicitly allowed | 2026-08-11 |
| 10 | API host resolution | API Farm default (by `test_mode`) + `connection_config.server_url` override | Per-connection override supported | 2026-08-11 |
| 11 | Phase 0 verification | Mocked four-method unittest pattern; no live creds | Karrio hermetic-suite norm | 2026-08-11 |

### Edge cases requiring input

| # | Edge case | Needs |
|---|-----------|-------|
| 1 | Print report `content` encoding | Confirm base64 against a sample response before shipping |
| 2 | Freight-payer party id source | Confirm whether `account_number` is a connection setting or per-request; default: connection setting used as the payer party's `id` |
| 3 | Service-point / home-delivery locator reference | Confirm whether 103 / 401 / 109 need a locator id and whether it can be caller-supplied (see Pending question #3) |

---

## Problem Statement

### Current state

```
Karrio has DHL connectors (dhl_express, dhl_parcel_de, dhl_poland,
dhl_universal, mydhl) but none for DHL Freight (Swedish road freight).
There is no way to book a DHL Freight transport instruction, retrieve its
label, or surface a DHL Freight tracking link through the Karrio unified API.
```

### Desired state

```
A dhl_freight connector books a transport instruction, returns a printable
label in one shipment/create call, and exposes a tracking id + tracking URL —
authenticating with a single client-key header against the SE API Farm.
```

### Problems

1. DHL Freight bookings cannot be created programmatically through Karrio today.
2. Freight labels (the Print API) are not integrated, so no label artifact is produced.
3. No DHL Freight tracking link is surfaced to dashboard or API consumers.

---

## Goals & Success Criteria

### Goals

1. Book a DHL Freight transport instruction from a unified `ShipmentRequest` and return the assigned tracking id.
2. Retrieve the label bytes for that booking and return them as `ShipmentDetails.docs.label`.
3. Authenticate every call with a single `client-key` header.
4. Return a tracking id + constructed tracking URL via the shipment `meta`.
5. Map `productCode` services and `payerCode` / label-layout options through `units.py` enums (no hardcoded strings).

### Success criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Connector discovered as a plugin | `./bin/cli plugins show dhl_freight` succeeds | P0 |
| Shipment create builds a valid booking + print request | `test_create_shipment_request` passes | P0 |
| Shipment parse returns tracking id + label + tracking_url | `test_parse_shipment_response` passes | P0 |
| Proxy issues booking + print to the correct API Farm URLs | `test_create_shipment` passes | P0 |
| Error responses parsed for booking/print | `test_parse_error_response` passes | P0 |
| Capabilities = shipping only | no `rating` / `tracking` / `pickup` reported in Phase 0 | P1 |

### Launch criteria

- [ ] P0: all four shipment test methods pass (mocked, hermetic).
- [ ] P0: `./bin/run-sdk-tests` green (hermetic suite; no live calls).
- [ ] P0: the shipment parse asserts a tracking number, a label, and `meta.tracking_url`.
- [ ] P1: capabilities report `shipping` only.

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **A. Book then print, chained in `create_shipment`** | One-step create returns label; honors Karrio's contract | Two sequential API calls; must merge two responses | **Chosen** |
| B. Book only; print deferred to a separate document call | Simpler create | Breaks "order label" in one step; consumers get no label at create time | Rejected |
| C. Print via full-payload `/print/printdocuments` | No id round-trip dependency | Re-sends the shipment; by-id is the leaner path | Kept open as the op-TBD alternative |

### Trade-off analysis

Approach A accepts a two-call create in exchange for honoring Karrio's contract that shipment creation yields a label.
If the print call fails after a successful booking, the booking still exists at DHL; the connector surfaces the print error while the booking id is recoverable via `meta` (see [Failure Modes](#failure-modes)).

---

## Technical Design

> Existing patterns were studied before proposing new code; reuse is favored over novel constructs.

### Existing code analysis

| Component | Location | Reuse strategy |
|-----------|----------|----------------|
| Static-header proxy (no token exchange) | `modules/connectors/seko/karrio/mappers/seko/proxy.py` | Mirror a fixed auth header set on every `lib.request` call — here `client-key` |
| Tracking-URL template property | `modules/connectors/dhl_express/karrio/providers/dhl_express/utils.py` | Same `tracking_url` `@property` returning a `.format()` template |
| Empty-label fallback | `modules/connectors/gls/karrio/providers/gls/shipment/create.py` | `docs=Documents(label=label_data or "")` if the print report is absent |
| Shipment `meta.tracking_url` | `modules/connectors/dpd_meta/karrio/providers/dpd_meta/shipment/create.py` | Stamp `meta=dict(tracking_url=...)` on `ShipmentDetails` |
| Capability-by-method derivation | `modules/sdk/karrio/references.py` (`detect_capabilities`) | Implement only `create_shipment`; omit `get_rates`, `get_tracking`, cancel |
| Per-connection `server_url` override | `modules/connectors/postat/karrio/providers/postat/{utils.py,units.py}` | Mirror `ConnectionConfig.server_url = lib.OptionEnum(...)` + resolve `self.connection_config.server_url.state or <default-by-test_mode>` |
| Scaffolding | `modules/cli/karrio_cli/commands/sdk.py` (`add_extension`) | `./bin/cli sdk add-extension` |

### Architecture overview

```
                        ┌────────────────────────────────────────┐
                        │            dhl_freight connector        │
                        │                                         │
  Karrio unified   ┌────┴─────┐   ┌──────────┐   ┌────────────┐   │
  ShipmentRequest ─▶│ mapper / │──▶│  proxy   │──▶│  utils.py  │   │
                    │ provider │   │ (HTTP)   │   │ client-key │   │
  ShipmentDetails ◀─│  create  │◀──│ book+prnt│   │ + hosts    │   │
                    └────┬─────┘   └────┬─────┘   └─────┬──────┘   │
                        │              │               │          │
                        └──────────────┼───────────────┘          │
                                       │                          │
                        ┌──────────────┴──────────────────────────┘
                        │  client-key: <api-key>  (every request)
          ┌─────────────▼───────────────┐   ┌───────────────────────┐
          │  Transport Instruction API  │   │  Print API            │
          │  /transportinstruction/     │   │  /print/printdocuments│
          │   sendtransportinstruction  │──▶│   byid (op TBD)       │
          │  → transportInstruction.id  │   │  → reports[].content  │
          └─────────────────────────────┘   └───────────────────────┘
   Tracking (URL-only): create stamps meta.tracking_url.format(id); no API call.
```

### Sequence diagram

```
create_shipment(ShipmentRequest)
   │   headers on every call: { client-key: <api-key>, content-type: application/json }
   │
   ├─▶ POST /transportinstructionapi/v1/transportinstruction/sendtransportinstruction
   │      (mapped Shipment: parties, pieces, payerCode, productCode)
   │   ◀─ { status, transportInstruction: { id } }        # tracking id
   │
   ├─▶ POST /printapi/v1/print/printdocumentsbyid          (op TBD)
   │      { shipmentIds: [id], options: { label, pageOptions.pageType } }
   │   ◀─ { reports: [ { name, content, contentType, type, valid } ] }
   │
   └─▶ parse → ShipmentDetails(
             tracking_number=id, shipment_identifier=id,
             docs=Documents(label=<label report content>),
             meta={ tracking_url: tracking_url.format(id) })
```

### Data flow diagram

```
REQUEST FLOW
  ShipmentRequest
    → recipient/shipper      → Party(type=Consignee) / Party(type=Consignor)
    → parcels[]              → pieces[] (packageType, weight[kg], W/H/L[cm], numberOfPieces)
    → service                → productCode
    → options.dhl_freight_payer_code   → payerCode.code (default DAP) + payer party.id = account_number
    → options.dhl_freight_label_layout → ReportOptions.pageOptions.pageType (default Label)
    → references             → references[] { qualifier, value }

RESPONSE FLOW
  Booking { transportInstruction.id } → tracking_number, shipment_identifier
  Print   { reports[].content }       → docs.label (label report; base64 assumed)
  (derived) tracking_url.format(id)   → meta.tracking_url
  errors  { validationErrors[], errorMessage } → Messages[] (field, code, message)
```

### Data models

Generated schema types (from the vendored OpenAPI 2.10.0 specs) drive all request/response handling. Key objects:

- **Booking request** `Shipment`: `productCode`, `payerCode{code,location}`, `parties[]{type,subType,id,name,contactName,address,phone,email}`, `pieces[]{numberOfPieces,packageType,weight,width,height,length,volume,goodsType,stackable}`, `references[]{qualifier,value}`, `pickupDate`, `additionalServices`, `customsInformation`.
- **Booking response** `TransportInstructionResponse`: `{ status, transportInstruction: Shipment{ id, ... } }`.
- **Booking error** `TransportInstructionErrorResponse`: `{ status, validationErrors[]: IValidationError{ field, errorCode, message, incompatibleFields }, errorMessage }`.
- **Print request** `PrintOptionsById`: `{ shipmentIds[], options: ReportOptions{ label, waybill, returnLabel, pageOptions{ pageType, marginLeft, marginTop, padding } } }`.
- **Print response** `PrintResult`: `{ reports[]: PrintReport{ name, content, contentType, type, valid } }`.

### Field reference (unified to carrier)

| Karrio field | Carrier field | Required | Notes |
|--------------|---------------|----------|-------|
| `shipper` | `parties[type=Consignor]` | Yes | name, address, contact, phone, email |
| `recipient` | `parties[type=Consignee]` | Yes | as above |
| `service` | `productCode` | Yes | numeric code (e.g. `102`, `232`); see product table |
| `options.dhl_freight_payer_code` | `payerCode.code` | No | default `DAP` |
| `settings.account_number` | payer `parties[].id` | Conditional | mandatory for the freight-payer party |
| `parcels[]` | `pieces[]` | Yes | weight→kg, dims→cm, `packageType` (default `PAL`), `numberOfPieces` |
| `options.dhl_freight_label_layout` | `pageOptions.pageType` | No | default `Label`; `Label2xPortraitA4` / `Label3xLandscapeA4` / `LabelCompact` / `LabelCompact2x2PortraitA4` |
| `reference` / `options` | `references[]{qualifier,value}` | No | e.g. CNR/CNZ/INV |
| booking `transportInstruction.id` | `tracking_number` | — | also `shipment_identifier` |

### Product codes

The API Farm's `productCode` is a numeric code; `units.py` encodes the full domestic and international set below.
Only the six marked (Fixture) products get hermetic test fixtures in Phase 0; the rest are encoded for completeness.
`SPI Standard Pallet International` has no numeric code and is encoded by its label.

| Direction | Code | Product | Fixture |
|-----------|------|---------|---------|
| Domestic (SE↔SE) | 118 | Hemleverans Paket B2C | |
| Domestic (SE↔SE) | 401 | Home Delivery B2C | Fixture |
| Domestic (SE↔SE) | 402, 502 | Home Delivery C2B | |
| Domestic (SE↔SE) | 210 | Pall | |
| Domestic (SE↔SE) | 102 | Paket | Fixture |
| Domestic (SE↔SE) | 212 | Parti | |
| Domestic (SE↔SE) | 103 | Service Point B2C | Fixture |
| Domestic (SE↔SE) | 104 | Service Point C2B | |
| Domestic (SE↔SE) | 209 | Special | |
| Domestic (SE↔SE) | 211 | Stycke | |
| International (to/from SE) | 202 | Road Freight Standard | Fixture |
| International (to/from SE) | 232 | Euroconnect Plus | Fixture |
| International (to/from SE) | 205 | Road Freight Direct | |
| International (to/from SE) | 233 | Road Freight Priority | |
| International (to/from SE) | 601 | Home Delivery International B2C | |
| International (to/from SE) | 109 | Parcel Connect B2C | Fixture |
| International (to/from SE) | 107 | Parcel Return Connect C2B | |
| International (to/from SE) | 112 | Parcel Connect Plus | |
| International (to/from SE) | SPI | Standard Pallet International | |

The three B2C / service-point fixture products (103, 401, 109) may require an `AccessPoint` or `Delivery` party carrying a `subType` (`Servicepoint`) and a locator id sourced from the Service Point or Home Delivery Locator APIs.
If that reference cannot be caller-supplied in Phase 0, these three drop from the fixture set; 102, 232, and 202 still fully exercise the book-then-print pipeline (see Pending question #3).

### API changes

| Endpoint (base path + operation) | Method | Auth | Purpose |
|----------------------------------|--------|------|---------|
| `/transportinstructionapi/v1/transportinstruction/sendtransportinstruction` | POST | `client-key` header | Create booking → tracking id |
| `/printapi/v1/print/printdocumentsbyid` (op TBD) | POST | `client-key` header | Retrieve label bytes by id |

Base host resolution (in `utils.py`): `self.connection_config.server_url.state` if set, else the API Farm default — test `https://test-api.freight-logistics.dhl.com`, production `https://api.freight-logistics.dhl.com` — selected by `test_mode`.
Each service's base path (`/transportinstructionapi/v1`, `/printapi/v1`, ...) is appended to the resolved host.

---

## Edge Cases & Failure Modes

### Edge cases

| Case | Handling |
|------|----------|
| Booking succeeds, print fails | Surface print error as `Messages`; booking id still recoverable via `meta`; return `ShipmentDetails` with empty label + `meta.tracking_url`, or fail per parser policy |
| Print report `content` not base64 | Assume base64 per DHL norm; verify against a sample before release |
| Missing `account_number` when payer party requires id | Validate early; return a clear `Message` rather than a DHL 400 |
| International shipment | Allowed; no geo gate — DHL API validates |
| Service-point / home-delivery product without a locator reference | Return a clear `Message` if the API rejects it; may drop these products from Phase 0 fixtures |
| Multiple print reports (label + waybill) | Select the label report for `docs.label`; others ignored in Phase 0 |

### Failure modes

| Failure | Detection | Response |
|---------|-----------|----------|
| Booking validation error | `validationErrors[]` / `errorMessage` | Map each to `Message(field, code, message)` |
| Print error | Defensive `validationErrors` / `errorMessage` parse | Map to `Message`; note booking id in `meta` |
| Invalid or missing `client-key` | DHL 401/403 | Parse into `Message`; abort create |
| Network/timeout | `lib.request` raises | Standard Karrio error propagation |

---

## Implementation Plan

### Phase 0 scope

Phase 0 delivers the shipping capability against the SE API Farm with hermetic, mocked tests.
Tracking (`tracking.py`) and cancel (`cancel.py`) remain documented deferred stubs; rating is deferred.

### Phase 1: Scaffold & schema generation

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Scaffold connector | `./bin/cli sdk add-extension` | Done | S |
| Vendor raw specs (upstream filenames, git-tracked) | `modules/connectors/dhl_freight/vendor/se-api-farm/*.json` | Done | S |
| Derive JSON generation samples from the vendored specs | `modules/connectors/dhl_freight/schemas/*.json` | In progress | M |
| Configure + run generation | `generate`, `./bin/run-generate-on modules/connectors/dhl_freight` | In progress | S |

### Phase 2: Settings, units, errors, proxy

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Settings + resolvable server URL (config override, default-by-test_mode) + tracking_url + label_type | `karrio/providers/dhl_freight/utils.py`, `karrio/mappers/dhl_freight/settings.py` | Pending | M |
| `ConnectionConfig.server_url` override + `label_type` | `karrio/providers/dhl_freight/units.py`, `karrio/plugins/dhl_freight/__init__.py` | Pending | S |
| Services (full product set) / options enums | `karrio/providers/dhl_freight/units.py` | Pending | M |
| Error parser (booking/print) | `karrio/providers/dhl_freight/error.py` | Pending | S |
| Proxy: `create_shipment` (book→print) with `client-key` header | `karrio/mappers/dhl_freight/proxy.py` | Pending | M |

### Phase 3: Providers

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Shipment create request build + response parse (with `meta.tracking_url`) | `karrio/providers/dhl_freight/shipment/create.py` | Pending | L |
| Public exports + plugin METADATA (shipping only) | `karrio/providers/dhl_freight/__init__.py`, `karrio/plugins/dhl_freight/__init__.py` | Pending | S |
| Deferred stubs documented (`tracking.py`, `cancel.py`) | `karrio/providers/dhl_freight/{tracking.py,shipment/cancel.py}` | Pending | S |

### Phase 4: Tests

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Fixtures + shipment tests (book+print mocks) for the six fixture products | `tests/dhl_freight/fixture.py`, `test_shipment.py` | Pending | M |
| Run suites, confirm plugin registration + capabilities | — | Pending | S |

---

## Testing Strategy

> unittest only (never pytest). Print requests/responses before asserting, then remove. Use `assertDictEqual`/`assertListEqual` with full payloads and `mock.ANY` for dynamic fields. Run from the repo root.

Phase 0 is fully hermetic: mocked `lib.request`, `test_mode=True`, hardcoded fixture credentials, no network.
No live sandbox credentials are required.

### Test categories

| Category | What it verifies |
|----------|------------------|
| Request build | Unified model → DHL booking + print request |
| API call | Proxy issues booking + print to the correct API Farm URLs with the `client-key` header |
| Response parse | Booking+print → `ShipmentDetails` (id, label, meta.tracking_url) |
| Errors | Booking/print error payloads → `Messages` |

### Test cases

```
test_shipment.py
  test_create_shipment_request       # ShipmentRequest → {booking, print} request
  test_create_shipment               # mock lib.request: booking + print URLs/order + client-key header
  test_parse_shipment_response       # merged response → ShipmentDetails(+label,+tracking_url)
  test_parse_error_response          # booking validationErrors/errorMessage → Messages
```

The six fixture products (domestic 102, 401, 103; international 232, 202, 109) provide the fixture matrix; 102, 232, and 202 must at minimum pass end-to-end.

### Running tests

```bash
source bin/activate-env
python -m unittest discover -v -f modules/connectors/dhl_freight/tests
./bin/run-sdk-tests
./bin/cli plugins show dhl_freight
```

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Print report `content` not base64 | Corrupt label | Medium | Verify against a sample before release; isolate decode in one helper |
| Service-point / home-delivery products need a locator reference | 103/401/109 cannot be booked without it | Medium | Confirm whether it is caller-supplied (Pending #3); drop from fixtures if not — 102/232/202 still cover the pipeline |
| Booking succeeds but print fails | Orphaned booking without label | Low | Surface error + keep booking id in `meta`; document recovery |
| Wrong tracking-URL template | Broken tracking link | Low | Confirm template (Pending #2); single source in `utils.py` |
| Print operation choice (`byid` vs full payload) | Rework in create flow | Low | Resolve during schema analysis (Pending #1); default `byid` |
| Raster format (PDF/ZPL) assumption | Mismatched label type tag | Low | `label_type` tags returned bytes; provisional pending user confirmation |

---

## Appendices

### Appendix A: Reference specs

Vendored to `modules/connectors/dhl_freight/vendor/se-api-farm/` (upstream filenames, git-tracked; matches `gls` / `hermes` / `dpd_meta`).
The DHL Freight Sweden API Farm OpenAPI 2.10.0 set includes, among others:

- `transport-instruction-2.10.0.json` — booking (`/transportinstruction/sendtransportinstruction`)
- `print-api-2.10.0.json` — label (`/print/printdocuments`, `/print/printdocumentsbyid`)
- `product-api-2.10.0.json` — products (`/products`), for the `productCode` set
- `pricequote-api-2.10.0.json` — price quotes (deferred beyond Phase 0)
- `servicepoint-api-2.10.0.json`, `home-delivery-locator-api-2.10.0.json` — locators for service-point / home-delivery products (deferred)

### Appendix B: Carrier-specific reference

- Authentication: a single `client-key` HTTP header on every request (`apiKey`, `in: header`); no token exchange.
- Booking `productCode` set: enumerated in the product table above; the runtime source of truth is the Product API `GET /products`.
- Tracking URL template: a DHL Freight Sweden portal template (Pending #2), applied locally to `transportInstruction.id`.

Hosts (resolved host + spec base path):

| Environment | API Farm host | Base paths |
|-------------|---------------|------------|
| Test | `https://test-api.freight-logistics.dhl.com` | `/transportinstructionapi/v1`, `/printapi/v1`, ... |
| Production | `https://api.freight-logistics.dhl.com` | as above |

Per-connection `connection_config.server_url` overrides the host.

| Karrio field | DHL Freight field |
|--------------|-------------------|
| `tracking_number` | booking `transportInstruction.id` |
| `docs.label` | `PrintResult.reports[].content` (label report) |
| `meta.tracking_url` | `tracking_url.format(transportInstruction.id)` |
| `service` | `productCode` |
| `options.dhl_freight_payer_code` | `payerCode.code` |
| `options.dhl_freight_label_layout` | `ReportOptions.pageOptions.pageType` |
