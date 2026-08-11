# PRD: DHL Freight Integration

| Field | Value |
|-------|-------|
| Project | DHL Freight carrier connector (`dhl_freight`) |
| Version | 1.0 |
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

Add a `dhl_freight` connector for DHL Freight's palletized road-freight booking service (> 35 kg), covering shipment creation (with label) and a tracking link.
The connector composes three DHL Freight APIs — Authentication, Shipment Booking, and Print — into Karrio's single `shipment/create` contract, and exposes a URL-only tracking capability.
It is used for domestic freight in our deployment, but imposes no geographic gate: DHL's own API validation remains authoritative, so international shipments are implicitly allowed.

### Key Architecture Decisions

1. **`shipment/create` chains book → print-by-id (approach A).** One proxy method books via `POST /sendtransportinstruction`, captures the assigned 13-char `shipment.id`, then calls `POST /print/printdocumentsbyid` with `{ shipmentIds: [id] }` and returns a merged `{ booking, print }` payload. This preserves Karrio's expectation that create returns a label in one step.
2. **OAuth2 client-credentials over HTTP Basic yields a ~30-minute Bearer token.** `utils.py` exchanges `consumer_key`/`consumer_secret` (the portal's API Key / API Secret) at `POST /auth/v1/token?response_type=id_token&grant_type=client_credentials` (Basic auth: `username=consumer_key`, `password=consumer_secret`), extracts the token, and caches it via Karrio's thread-safe connection cache keyed on `expires_in` (~30 min per the User Guide). Booking and Print send `Authorization: Bearer <token>`. Auth is bundled into the Freight APIs on the same host; the standalone Authentication API is documentation only. Mirrors the `dhl_parcel_de` token-cache pattern; credential naming matches `dhl_universal` (`consumer_key`/`consumer_secret`).
3. **Tracking is URL-only, no network call.** `get_tracking` builds `TrackingDetails` locally: `carrier_tracking_link = tracking_url.format(tracking_number)`, a neutral in-transit status, empty events. `shipment/create` also stamps `meta.tracking_url`. The DHL Unified Tracking API (UTAPI) is intentionally not called; it uses a different credential and is deferred to a future events phase.
4. **No rating.** No spec quotes prices; omitting `get_rates` from the proxy makes the `rating` capability absent automatically (capabilities are derived from proxy method names).
5. **No void/cancel.** The Booking API declares no cancellation endpoint, so `void_shipment` is not implemented (see [Resolved Decisions](#resolved-decisions)).
6. **Label format (PDF/ZPL) is not selectable; page layout is.** The Print API exposes no raster-format field. The connector models a label-layout option mapping to `pageType` (`Label`, `Label2xPortraitA4`, `Label3xLandscapeA4`, `LabelCompact`); raster format is governed by DHL account configuration.
7. **API host is per-connection overridable.** The default host is the DHL Group platform (test `https://api-sandbox.dhl.com`, production `https://api.dhl.com`) — the officially documented path per the User Guide — selected by `test_mode`, with a `connection_config.server_url` override (the `postat` precedent). The SE "API Farm" (`test-api` / `api.freight-logistics.dhl.com`, a recommended path for SE-based consumers) is a first-class override reached through the same field. Base paths from the specs (`/freight/shipping/orders/v1`, `/freight/shipping/labels/v1`, `/auth/v1/token`) are appended to the resolved host.
8. **Live validation is a success criterion.** Beyond hermetic unit tests, an opt-in smoke test must obtain valid responses from test-api. This is net-new to the repo (all existing connector tests are hermetic) and is therefore isolated and gated (see [Testing Strategy](#testing-strategy)).

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| Shipment booking (`POST /sendtransportinstruction`) | Rating / price quotes |
| Label retrieval (`POST /print/printdocumentsbyid`) | Live tracking events (UTAPI calls) |
| Auth token exchange + caching (`POST /auth/v1/token`) | Shipment cancellation / void |
| Tracking link + tracking id (URL-only) | Pickup, manifest, address validation |
| `productCode` services + `payerCode` / layout options | Dangerous goods, temperature-controlled, ADR (phase 2) |
| Domestic and international (no geo gate) | PDF-vs-ZPL format selection (not in API) |

---

## Open Questions & Decisions

### Pending Questions

| # | Question | Context | Options | Status |
|---|----------|---------|---------|--------|
| 1 | Which token do Booking/Print accept as `Bearer`? | Auth API returns both an opaque `access_token` and a JWT `id_token`; Booking declares `bearerFormat: JWT`. | (a) `id_token` (literal spec match) — default; (b) `access_token` | Default `id_token`; verify against sandbox during Phase 3 |
| 2 | Correct public tracking-URL template for DHL Freight | Tracking is URL-only; the template lives in `utils.py`. | (a) `https://www.dhl.com/global-en/home/tracking/tracking-freight.html?submit=1&tracking-id={}`; (b) `activetracing.dhl.com` variant | Default (a); confirm with DHL Freight docs |
### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| 1 | Create flow | Approach A: book → print-by-id chained in `create_shipment` | Preserves one-step "create returns label"; by-id is DHL's documented path | 2026-08-11 |
| 2 | Auth model | OAuth2 client-credentials (Basic) → cached JWT | Matches Auth API spec + `dhl_parcel_de` precedent | 2026-08-11 |
| 3 | Tracking scope | URL-only, no API call | User requirement: "tracking URL and id, not events for now" | 2026-08-11 |
| 4 | Rating | Not implemented | No pricing endpoint in any spec | 2026-08-11 |
| 5 | Void / cancel | Not implemented | No cancellation endpoint in the Booking API | 2026-08-11 |
| 6 | Label options | Expose `pageType` layout; no PDF/ZPL selector | Print API has no raster-format field | 2026-08-11 |
| 7 | Geographic gating | None | DHL API validation is authoritative; international implicitly allowed | 2026-08-11 |
| 8 | API host resolution | DHL Group platform default (by `test_mode`, User Guide) + `connection_config.server_url` override; SE API Farm is a first-class override | User: DHL Group platform default, allow per-connection override to the API Farm | 2026-08-11 |
| 9 | Live validation approach | Opt-in, credentials-via-env smoke test isolated from the hermetic suite | User chose "creds via env; gated smoke test"; repo has no existing gated-test convention, so keep it isolated + opt-in | 2026-08-11 |
| 10 | Token TTL | ~30 minutes (User Guide); cache with safety margin | Supersedes the auth spec's misleading `expires_in: 119` example | 2026-08-11 |
| 11 | Auth host | Same host as booking/print (auth bundled into the Freight APIs) | User Guide: no separate access to the Authentication API is required | 2026-08-11 |
| 12 | Credentials | `consumer_key` / `consumer_secret` (portal API Key / Secret) as Basic username/password | Matches DHL portal terminology + `dhl_universal` naming | 2026-08-11 |

### Edge Cases Requiring Input

| # | Edge Case | Needs |
|---|-----------|-------|
| 1 | Print `content` encoding | Confirm base64 vs raw against a live sandbox response before shipping (spec omits `format: byte`) |
| 2 | Freight-payer party id source | Confirm whether `account_number` is a connection setting or per-request; default: connection setting used as the payer party's `id` |

---

## Problem Statement

### Current State

```
Karrio has DHL connectors (dhl_express, dhl_parcel_de, dhl_poland,
dhl_universal, mydhl) but none for DHL Freight (palletized road freight > 35 kg).
There is no way to book a DHL Freight transport order, retrieve its label,
or surface a DHL Freight tracking link through the Karrio unified API.
```

### Desired State

```
A dhl_freight connector books a transport order, returns a printable label
in one shipment/create call, and exposes a tracking id + tracking URL —
authenticating via DHL's OAuth2 token service with a cached JWT.
```

### Problems

1. DHL Freight bookings cannot be created programmatically through Karrio today.
2. Freight labels (the Print API) are not integrated, so no label artifact is produced.
3. No DHL Freight tracking link is surfaced to dashboard or API consumers.

---

## Goals & Success Criteria

### Goals

1. Book a DHL Freight transport order from a unified `ShipmentRequest` and return the assigned tracking id.
2. Retrieve the label bytes for that booking and return them as `ShipmentDetails.docs.label`.
3. Authenticate transparently with a cached, auto-refreshing JWT.
4. Return a tracking id + constructed tracking URL via both shipment `meta` and `get_tracking`.
5. Map `productCode` services and `payerCode` / label-layout options through `units.py` enums (no hardcoded strings).

### Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Connector discovered as a plugin | `./bin/cli plugins show dhl_freight` succeeds | P0 |
| Shipment create builds a valid booking + print request | `test_create_shipment_request` passes | P0 |
| Shipment parse returns tracking id + label + tracking_url | `test_parse_shipment_response` passes | P0 |
| Tracking returns id + constructed URL | `test_parse_tracking_response` passes | P0 |
| Error responses parsed for booking/print/auth | `test_parse_error_response` passes | P0 |
| Valid live responses from test-api | opt-in smoke test returns non-error auth + booking id + label report | P0 |
| Capabilities = shipping, tracking only | no `rating` / `pickup` reported | P1 |

### Launch Criteria

- [ ] P0: all four test methods pass for shipment + tracking.
- [ ] P0: `./bin/run-sdk-tests` green (hermetic suite; live smoke test skips offline).
- [ ] P0: live smoke test against test-api returns valid auth + booking + print responses (run with env creds + `DHL_FREIGHT_LIVE_TEST=1`).
- [ ] P1: token cache verified to refresh on expiry.

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **A. Book → print-by-id chained in `create_shipment`** | One-step create returns label; by-id is DHL's documented path; minimal payload on print | Two sequential API calls; must merge two responses | **Chosen** |
| B. Book only; print deferred to a separate document call | Simpler create | Breaks "order label" in one step; dashboard/API consumers get no label at create time | Rejected |
| C. Print via full-payload `/print/printdocuments` | No second id round-trip dependency | Re-sends entire shipment; by-id is the recommended path; larger request | Rejected |

### Trade-off Analysis

Approach A accepts a two-call create in exchange for honoring Karrio's contract that shipment creation yields a label.
If the print call fails after a successful booking, the booking still exists at DHL; the connector surfaces the print error while the booking id is recoverable via `meta` (see [Failure Modes](#failure-modes)).

---

## Technical Design

> Existing patterns were studied before proposing new code; reuse is favored over novel constructs.

### Existing Code Analysis

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| OAuth token cache | `modules/connectors/dhl_parcel_de/karrio/providers/dhl_parcel_de/utils.py` | Mirror the cached-token property + `lib.connection_cache` / thread-safe access for the JWT exchange |
| Tracking-URL template property | `modules/connectors/dhl_express/karrio/providers/dhl_express/utils.py` | Same `tracking_url` `@property` returning a `.format()` template |
| Empty-label fallback | `modules/connectors/gls/karrio/providers/gls/shipment/create.py` | `docs=Documents(label=label_data or "")` if the print report is absent |
| Shipment `meta.tracking_url` | `modules/connectors/dpd_meta/karrio/providers/dpd_meta/shipment/create.py` | Stamp `meta=dict(tracking_url=...)` on `ShipmentDetails` |
| Capability-by-method derivation | `modules/sdk/karrio/references.py` (`detect_capabilities`) | Implement only `create_shipment` + `get_tracking`; omit `get_rates`/cancel |
| Per-connection `server_url` override | `modules/connectors/postat/karrio/providers/postat/{utils.py,units.py}` | Mirror `ConnectionConfig.server_url = lib.OptionEnum(...)` + resolve `self.connection_config.server_url.state or <default-by-test_mode>` |
| Scaffolding | `modules/cli/karrio_cli/commands/sdk.py` (`add_extension`) | `./bin/cli sdk add-extension` with `--features "shipping,tracking"` |

### Architecture Overview

```
                        ┌────────────────────────────────────────┐
                        │            dhl_freight connector        │
                        │                                         │
  Karrio unified   ┌────┴─────┐   ┌──────────┐   ┌────────────┐   │
  ShipmentRequest ─▶│ mapper / │──▶│  proxy   │──▶│  utils.py  │   │
                    │ provider │   │ (HTTP)   │   │ auth+token │   │
  ShipmentDetails ◀─│  create  │◀──│          │   │  cache     │   │
                    └────┬─────┘   └────┬─────┘   └─────┬──────┘   │
                        │              │               │          │
                        └──────────────┼───────────────┘          │
                                       │                          │
                        ┌──────────────┴──────────────────────────┘
                        │
          ┌─────────────▼──────────┐  ┌──────────────┐  ┌──────────────┐
          │  Auth API              │  │  Booking API │  │  Print API   │
          │  /auth/v1/token (Basic)│  │ /sendtransp… │  │ /print/print │
          │  → JWT (Bearer)        │  │ → shipment.id│  │  documentsbyid│
          └────────────────────────┘  └──────────────┘  │ → label bytes│
                                                         └──────────────┘
   Tracking (URL-only): get_tracking constructs tracking_url.format(id) locally.
```

### Sequence Diagram

```
create_shipment(ShipmentRequest)
   │
   ├─▶ utils.access_token
   │      │  cache miss / expired?
   │      └─▶ POST /auth/v1/token?response_type=id_token&grant_type=client_credentials
   │             Authorization: Basic base64(consumer_key:consumer_secret)
   │          ◀─ { token, expires_in (~30 min) }   → cache with margin
   │
   ├─▶ POST /sendtransportinstruction        Authorization: Bearer <jwt>
   │      (mapped Shipment: parties, pieces, payerCode, productCode)
   │   ◀─ { status, shipment: { id } }        # 13-char tracking id
   │
   ├─▶ POST /print/printdocumentsbyid         Authorization: Bearer <jwt>
   │      { shipmentIds: [id], options: { label, pageOptions.pageType } }
   │   ◀─ { reports: [ { name, content, type, valid } ] }
   │
   └─▶ parse → ShipmentDetails(
             tracking_number=id, shipment_identifier=id,
             docs=Documents(label=<label report content>),
             meta={ tracking_url: tracking_url.format(id) })
```

### Data Flow Diagram

```
REQUEST FLOW
  ShipmentRequest
    → recipient/shipper      → Party(type=Consignee) / Party(type=Consignor)
    → parcels[]              → pieces[] (packageType, weight[kg], W/H/L[cm], numberOfPieces)
    → service                    → productCode
    → options.dhl_freight_payer_code   → payerCode.code (default DAP) + payer party.id = account_number
    → options.dhl_freight_label_layout → ReportOptions.pageOptions.pageType
    → options.references          → references[] (CNR/CNZ/INV)

RESPONSE FLOW
  Booking { shipment.id }           → tracking_number, shipment_identifier
  Print   { reports[].content }     → docs.label (label report; base64 assumed)
  (derived) tracking_url.format(id) → meta.tracking_url, carrier_tracking_link
  errors  { validationErrors[] } /  → Messages[] (field, code, message)
          { status,title,detail }
```

### Data Models

Generated schema types (from the four OpenAPI specs) drive all request/response handling. Key objects:

- **Booking request** `Shipment`: `productCode`, `payerCode{code,location}`, `parties[]{type,id,name,address,contactName,phone,email}`, `pieces[]{numberOfPieces,packageType,weight,width,height,length,volume,goodsType}`, `references[]{qualifier,value}`, `pickupDate`, `additionalServices` (subset).
- **Booking response** `TransportInstructionResponseSuccess`: `{ status, shipment{ id, ... } }`.
- **Print request** `PrintOptionsById`: `{ shipmentIds[], options: ReportOptions{ label, waybill, returnLabel, pageOptions{ pageType, marginLeft, marginTop } } }`.
- **Print response** `PrintResult`: `{ reports[]: { name, content, type, valid } }`.
- **Auth response**: `{ access_token, id_token, token_type, expires_in }`.
- **Error shapes**: booking `TransportInstructionResponseError{ status, validationErrors[]{ field, errorCode, message, incompatibleFields[] } }`; auth `{ status, title, detail }`.

### Field Reference (unified → carrier)

| Karrio field | Carrier field | Required | Notes |
|--------------|---------------|----------|-------|
| `shipper` | `parties[type=Consignor]` | Yes | name, address, contact, phone, email |
| `recipient` | `parties[type=Consignee]` | Yes | as above |
| `service` | `productCode` | Yes | e.g. `ECI` + Road Freight Standard/Priority codes |
| `options.dhl_freight_payer_code` | `payerCode.code` | No | default `DAP`; DAP/DDP/EXW/CIP |
| `settings.account_number` | payer `parties[].id` | Conditional | mandatory for the freight-payer party |
| `parcels[]` | `pieces[]` | Yes | weight→kg, dims→cm, `packageType` (default `PAL`), `numberOfPieces` |
| `options.dhl_freight_label_layout` | `pageOptions.pageType` | No | `Label`/`Label2xPortraitA4`/`Label3xLandscapeA4`/`LabelCompact` |
| `reference` / `options` | `references[]{qualifier,value}` | No | CNR/CNZ/INV |
| booking `shipment.id` | `tracking_number` | — | 13-char id; also `shipment_identifier` |

### API Changes

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/auth/v1/token` | POST | Basic | Exchange client credentials for JWT |
| `/freight/shipping/orders/v1/sendtransportinstruction` | POST | Bearer JWT | Create booking → tracking id |
| `/freight/shipping/labels/v1/print/printdocumentsbyid` | POST | Bearer JWT | Retrieve label bytes by id |

Base host resolution (in `utils.py`): `self.connection_config.server_url.state` if set, else the DHL Group platform default (User Guide) — test `https://api-sandbox.dhl.com`, production `https://api.dhl.com` — selected by `test_mode`.
The SE API Farm hosts (`test-api` / `api.freight-logistics.dhl.com`) are a first-class override reached via the same field (or `DHL_FREIGHT_SERVER_URL` in tests).
The `/auth/v1/token`, `/freight/shipping/orders/v1/...`, and `/freight/shipping/labels/v1/...` base paths are appended to the resolved host.

---

## Edge Cases & Failure Modes

### Edge Cases

| Case | Handling |
|------|----------|
| Booking succeeds, print fails | Surface print error as `Messages`; booking id still recoverable; return `ShipmentDetails` with empty label + `meta.tracking_url`, or fail per parser policy (confirm in Phase 3) |
| Print report `content` not base64 | Assume base64 per DHL norm; verify against sandbox (Q#1 pending) before release |
| Missing `account_number` when payer party requires id | Validate early; return a clear `Message` rather than a DHL 400 |
| International shipment | Allowed; no geo gate — DHL API validates |
| Token expired mid-session | Cache refresh on expiry via `expires_in` margin |
| Multiple print reports (label + waybill) | Select the label report for `docs.label`; others ignored in v1 |

### Failure Modes

| Failure | Detection | Response |
|---------|-----------|----------|
| Auth 400/401 | `{ status, title, detail }` | Parse into `Message`; abort create |
| Booking validation error | `validationErrors[]` | Map each to `Message(field, code, message)` |
| Print error (undocumented) | Defensive `IValidationError` parse | Map to `Message`; note booking id in `meta` |
| Network/timeout | `lib.request` raises | Standard Karrio error propagation |

---

## Implementation Plan

### Phase 1: Scaffold & schema generation

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Scaffold connector | `./bin/cli sdk add-extension --path modules/connectors --carrier-slug dhl_freight --display-name "DHL Freight" --features "shipping,tracking" --no-is-xml-api --version 2026.4 --confirm` | Pending | S |
| Vendor raw specs + User Guide (upstream filenames, git-tracked) | `modules/connectors/dhl_freight/vendor/` | Pending | S |
| Derive JSON generation samples from the vendored YAMLs | `modules/connectors/dhl_freight/schemas/*.json` | Pending | M |
| Configure + run generation | `generate`, `./bin/run-generate-on modules/connectors/dhl_freight` | Pending | S |

### Phase 2: Auth, settings, units, errors

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Settings + token cache + resolvable server URL (config override, default-by-test_mode) + tracking_url | `karrio/providers/dhl_freight/utils.py`, `karrio/mappers/dhl_freight/settings.py` | Pending | M |
| `ConnectionConfig.server_url` override field | `karrio/providers/dhl_freight/units.py`, `karrio/plugins/dhl_freight/__init__.py` (`connection_configs=`) | Pending | S |
| Services/options/tracking-status enums | `karrio/providers/dhl_freight/units.py` | Pending | M |
| Error parser (booking/print/auth) | `karrio/providers/dhl_freight/error.py` | Pending | S |
| Proxy: `create_shipment` (book→print), `get_tracking` | `karrio/mappers/dhl_freight/proxy.py` | Pending | M |

### Phase 3: Providers

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Shipment create request build + response parse | `karrio/providers/dhl_freight/shipment/create.py` | Pending | L |
| Tracking (URL-only) build + parse | `karrio/providers/dhl_freight/tracking.py` | Pending | S |
| Public exports | `karrio/providers/dhl_freight/__init__.py`, `karrio/plugins/dhl_freight/__init__.py` (METADATA) | Pending | S |

### Phase 4: Tests & validation

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Fixtures + shipment tests (book+print mocks) | `tests/dhl_freight/fixture.py`, `test_shipment.py` | Pending | M |
| Tracking tests (URL construction) | `tests/dhl_freight/test_tracking.py` | Pending | S |
| Opt-in live smoke test vs test-api (env creds) | `tests/dhl_freight/test_live_smoke.py` | Pending | M |
| Run suites, confirm plugin registration | — | Pending | S |

---

## Testing Strategy

> unittest only (never pytest). Print requests/responses before asserting, then remove. Use `assertDictEqual`/`assertListEqual` with full payloads and `mock.ANY` for dynamic fields. Run from the repo root.

### Test Categories

| Category | What it verifies |
|----------|------------------|
| Request build | Unified model → DHL booking + print request |
| API call | Proxy issues auth + booking + print to the correct URLs |
| Response parse | Booking+print → `ShipmentDetails` (id, label, meta.tracking_url) |
| Tracking | `get_tracking` → id + constructed URL, no HTTP |
| Errors | Booking/print/auth error payloads → `Messages` |

### Test Cases

```
test_shipment.py
  test_create_shipment_request       # ShipmentRequest → {booking, print} request
  test_create_shipment               # mock lib.request: auth + booking + print URLs/order
  test_parse_shipment_response       # merged response → ShipmentDetails(+label,+tracking_url)
  test_parse_error_response          # booking validationErrors → Messages

test_tracking.py
  test_parse_tracking_response       # tracking_number → TrackingDetails(carrier_tracking_link), no HTTP
  test_tracking_url_construction     # blank/invalid tracking number handled gracefully
```

### Running Tests

```bash
source bin/activate-env
python -m unittest discover -v -f modules/connectors/dhl_freight/tests
./bin/run-sdk-tests
./bin/cli plugins show dhl_freight
```

### Live smoke test (net-new convention, opt-in gated)

> Every existing connector test in this repo is hermetic — mocked, `test_mode=True`, hardcoded fixture credentials, no network. A live test is net-new here, so it is isolated in its own file and opt-in, keeping the default suite green and offline.

`tests/dhl_freight/test_live_smoke.py` calls the real test-api and is skipped unless credentials *and* an explicit opt-in are present:

```python
import os, unittest

LIVE = bool(os.getenv("DHL_FREIGHT_CONSUMER_KEY") and os.getenv("DHL_FREIGHT_LIVE_TEST"))

@unittest.skipUnless(LIVE, "set DHL_FREIGHT_LIVE_TEST=1 + DHL_FREIGHT_CONSUMER_KEY/SECRET to run")
class TestDHLFreightLiveSmoke(unittest.TestCase):
    def test_auth_book_print(self):
        # build gateway from env creds against the API Farm test host,
        # create a shipment, assert non-error auth + a booking id + a label report
        ...
```

Environment variables (following the repo's `<CARRIER_ID_UPPER>_*` convention):

| Var | Purpose |
|-----|---------|
| `DHL_FREIGHT_CONSUMER_KEY` / `DHL_FREIGHT_CONSUMER_SECRET` | OAuth credentials (portal API Key / Secret) for the token exchange |
| `DHL_FREIGHT_ACCOUNT_NUMBER` | Freight-payer party id |
| `DHL_FREIGHT_SERVER_URL` | Optional host override (else DHL Group platform default by `test_mode`; set to the SE API Farm here to target it) |
| `DHL_FREIGHT_LIVE_TEST` | Explicit opt-in (`1`) so the test never fires in the default/CI hermetic run unless intended |

`./bin/run-sdk-tests` stays green offline: the class skips when the opt-in or credentials are absent. Real responses captured here become the fixtures for the hermetic tests.

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Bearer token ambiguity (`id_token` vs `access_token`) | Auth fails against Booking/Print | Medium | Default `id_token`; make the field a one-line switch; verify in sandbox (Q#1) |
| Print `content` not base64 | Corrupt label | Medium | Verify against sandbox before release; isolate decode in one helper |
| Token expiry mid-flow (~30 min TTL) | Occasional re-auth | Low | Cache with margin; refresh on expiry; reuse `dhl_parcel_de` pattern |
| Booking succeeds but print fails | Orphaned booking without label | Low | Surface error + keep booking id in `meta`; document recovery |
| Wrong tracking-URL template | Broken tracking link | Low | Confirm template (Q#2); single source in `utils.py` |
| Wrong host for a given consumer (DHL Group vs SE API Farm) | Live calls fail | Low | Default DHL Group platform + `connection_config.server_url` override to the API Farm; confirm via smoke test |
| Net-new gated live test deviates from hermetic-suite norm | CI flakiness / accidental live calls | Low | Isolate in its own file; double-gate on creds + `DHL_FREIGHT_LIVE_TEST`; skips by default |

---

## Appendices

### Appendix A: Reference specs

Vendored to `modules/connectors/dhl_freight/vendor/` during Phase 1 (repo convention — upstream filenames, git-tracked; matches `gls` / `hermes` / `dpd_meta`). Currently working copies at repo root.

- `DHL Freight Authentication API YAML - 2026 R04.yaml`
- `DHL Freight Shipment Booking API YAML - 2026 R04.yaml`
- `DHL Freight Print API YAML - 2026 R04.yaml`
- `DHL Freight Shipment Tracking API YAML - 2026 R04.yaml` (retained for future events phase; not called in v1)
- `DHL Freight User Guide.md` — authoritative for hosts, ~30-min token, and API Key/Secret credentials

### Appendix B: Carrier-Specific Reference

- DHL Authentication API: `POST /auth/v1/token`, Basic auth, `response_type` ∈ {`access_token`, `id_token`}, grant `client_credentials`.
- Booking `productCode` and `payerCode` options: per DHL Product Manual / `GET /products` (not in provided specs; enumerate during Phase 2).
- Tracking URL template (proposed): `https://www.dhl.com/global-en/home/tracking/tracking-freight.html?submit=1&tracking-id={}`.

Hosts (resolved host + spec base path):

| Environment | Default host (DHL Group platform) | Override (SE API Farm) |
|-------------|-----------------------------------|------------------------|
| Test | `https://api-sandbox.dhl.com` | `https://test-api.freight-logistics.dhl.com` |
| Production | `https://api.dhl.com` | `https://api.freight-logistics.dhl.com` |

The DHL Group platform hosts are the documented general path (User Guide); the SE API Farm is a recommended path for SE-based consumers. Per-connection `connection_config.server_url` selects either.

Live-test env vars: `DHL_FREIGHT_CONSUMER_KEY`, `DHL_FREIGHT_CONSUMER_SECRET`, `DHL_FREIGHT_ACCOUNT_NUMBER`, `DHL_FREIGHT_SERVER_URL` (optional), `DHL_FREIGHT_LIVE_TEST` (opt-in).

| Karrio field | DHL Freight field |
|--------------|-------------------|
| `tracking_number` | booking `shipment.id` |
| `docs.label` | `PrintResult.reports[].content` (label report) |
| `meta.tracking_url` | `tracking_url.format(shipment.id)` |
| `service` | `productCode` |
| `options.dhl_freight_payer_code` | `payerCode.code` |
| `options.dhl_freight_label_layout` | `ReportOptions.pageOptions.pageType` |
