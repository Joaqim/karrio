# PRD: PostNord Integration

<!-- INTEGRATION -->

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.2 |
| Date | 2026-06-24 |
| Status | Planning |
| Owner | Joaqim Planstedt |
| Type | Integration |
| Reference | [AGENTS.md](../AGENTS.md), [CARRIER_INTEGRATION_GUIDE.md](../CARRIER_INTEGRATION_GUIDE.md) |

> **v1.1 revision note:** Revised after analyzing the authoritative specs `postnord-booking.swagger.json` and `postnord-servicepoints-v5.swagger.json`. The Booking (EDI) and Service Points APIs are **apikey-only (query param), not OAuth2** — superseding v1.0's dual-credential/OAuth2 design. This resolves the prior open question on API generation. Tracking awaits a Track & Trace spec; Service Points is documented but deferred.
>
> **v1.2 revision note:** Analyzed `postnord-tracking.swagger.json`. It is a `Track Shipment URL` API (`GET /rest/links/v1/tracking/{country}/{id}`) that returns only a tracking **URL string**, not events/status. Tracking is therefore implemented **link-only** (D7): `get_tracking` populates `tracking_url` plus a single generic status, no events. A future enhancement upgrades to the Track & Trace v5/v7 `findByIdentifier` events API.

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
12. [Appendices](#appendices)

---

## Executive Summary

This PRD specifies a greenfield Karrio connector for **PostNord**, the Nordic postal and logistics carrier serving Sweden, Denmark, Norway, and Finland. The connector lives at `modules/connectors/postnord/` (a direct carrier, not a hub) and is scaffolded with `./bin/cli sdk add-extension`. It targets rating, shipping, tracking, and manifest — but, because PostNord's public API exposes no money-rates and no end-of-day manifest, rating and manifest are adapted to what the API genuinely supports.

The authoritative Booking (EDI) spec resolves the central design question: every Booking endpoint is **apikey-authenticated via a query parameter** (`SECURED: False`), and the Service Points spec is likewise apikey-only. The connector therefore uses a **single `apikey` credential** across all operations — no OAuth2, no dual credentials. This makes SEKO (apikey auth) the closest auth reference; USPS remains the structural reference for the provider/test layout.

### Key Architecture Decisions

1. **Direct-carrier connector at `modules/connectors/postnord/`**: PostNord operates its own first-party API, so it follows the standard direct-carrier pattern (not the `community/plugins/` hub pattern).
2. **Single `apikey` credential (query param)**: the Booking (EDI) and Service Points specs are `SECURED: False` and take `?apikey=...` on every call. One `apikey` setting authorizes Booking, Manifest-as-Pickup, Service Points, and Tracking. The OAuth2/dual-credential design from v1.0 is removed.
3. **Shipping via the Booking EDI API**: `POST /rest/shipment/v3/edi/labels/{pdf,zpl}` books and returns the label in one call; cancellation re-POSTs the `ediInstruction` with `updateIndicator: "Deletion"` (no DELETE endpoint exists).
4. **Rating via merchant-configured static rates** (D1): PostNord exposes no money-rate API, so `get_rates` returns rates from a merchant-supplied `ConnectionConfig` rate table keyed by service code rather than calling the carrier.
5. **Manifest mapped to the Booking API's `/v3/pickups`** (D2): PostNord has no manifest/scan-form endpoint, so `Manifest.create()` books a physical pickup via `POST /rest/shipment/v3/pickups` — an endpoint within the same Booking spec. Semantics differ from a true manifest document; documented as a limitation.
6. **Service Points documented but deferred** (D6): the supplied Service Points v5 spec (pickup-location lookup for MyPack Collect) is mapped in this PRD as a planned carrier-specific helper, not implemented in the first pass.
7. **Tracking is link-only** (D7): the supplied tracking spec returns only a tracking URL, so `get_tracking` populates `TrackingDetails.tracking_url` and a single generic status — no events. Upgrading to the Track & Trace v5/v7 events API is a future enhancement.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| Shipping: book + label (PDF/ZPL/SVG/QR) via Booking EDI `/v3/edi/labels/*` | Real-time money-rate quoting (no public PostNord API) |
| Shipment cancellation via `updateIndicator: "Deletion"` | True end-of-day scan-form manifest document |
| Rating: static/config-driven rate table per service (D1) | Service-point lookup *implementation* (documented/deferred, D6) |
| Manifest: pickup booking via `/v3/pickups` (D2) | Event-based tracking (status/locations/events) until a Track & Trace v5/v7 spec is supplied |
| Tracking: link-only (`tracking_url` + generic status, D7) | Customs CN22/CN23/invoice & dangerous-goods declarations (future) |
| Service & additional-service / package / issuer enums in `units.py` | Digital/QR returns flow (future enhancement) |
| Sandbox (`atapi2`) + production (`api2`) switching | Dashboard/UI carrier-connection form changes |

---

## Open Questions & Decisions

### Pending Questions

| # | Question | Context | Options | Status |
|---|----------|---------|---------|--------|
| Q2 | Sandbox apikey availability | Tests are mocked and need no live key, but end-to-end validation against `atapi2.postnord.com` does. | A) Obtain partner sandbox apikey before live validation; B) mock-only | ⏳ Pending |
| Q3 | Static rate table location | D1 chose static/config rates; this sub-decision sets whether each merchant configures rates or a default ships. | A) `ConnectionConfig.rate_table` per connection; B) config over shipped default | ⏳ Pending |
| Q4 | Label-by-id token (`id` vs `printId`) | Booking response returns both `assignedIds.value` and `assignedIds.printId`; the `/v3/labels/ids/*` body schema (`ids_inner`) only has `{id, labelType}`. Which token the retrieval keys on is ambiguous in the spec. Only relevant if the two-step (book then fetch label) path is used; the one-shot `/v3/edi/labels/*` path avoids it. | A) Use one-shot path (avoids the question) — **recommended**; B) confirm with PostNord | ⏳ Pending |

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | Rating given no public rate API | Static/config rates | Prices are contract-specific and unexposed. Merchant-configured flat rates per service keep rate-driven flows working without fabricating carrier data. | 2026-06-24 |
| D2 | Manifest given no manifest API | Map to Booking `/v3/pickups` | No native manifest/EOD endpoint (EDI file flow retired 2024). The Booking spec's `createPickups` is the nearest physical-handover mechanism and lives in the same API. | 2026-06-24 |
| D3 | API generation / auth | apikey EDI generation (per supplied spec) | `postnord-booking.swagger.json` is `SECURED: False`, apikey query param. Authoritative spec supersedes the web-sourced OAuth2 claim. Resolves v1.0's Q1. | 2026-06-24 |
| D4 | Connector location/pattern | `modules/connectors/postnord/`, direct carrier | First-party carrier with its own API, not an aggregator. | 2026-06-24 |
| D5 | Reference carriers | SEKO (auth) + USPS (structure) | SEKO models apikey auth; USPS models JSON provider/test/manifest layout. | 2026-06-24 |
| D6 | Service Points v5 scope | Document, defer implementation | Pickup-location lookup for MyPack Collect; no unified Karrio service-point contract exists. Mapped here; implemented later. | 2026-06-24 |
| D7 | Tracking depth | Link-only (no events) | Supplied `postnord-tracking.swagger.json` returns only a tracking URL, not events. `get_tracking` populates `tracking_url` + generic status; events deferred to a future Track & Trace v5/v7 integration. | 2026-06-24 |

### Edge Cases Requiring Input

| Edge Case | Impact | Proposed Handling | Needs Input? |
|-----------|--------|-------------------|--------------|
| Rate requested for a service absent from the static table | `get_rates` returns empty | Return `[]` + informational `Message`; never raise | ❌ No |
| Cancellation has no DELETE endpoint | Void flow unclear | Re-POST `ediInstruction` with `updateIndicator: "Deletion"` to `/v3/edi` | ❌ No (spec-confirmed pattern) |
| Two-step label retrieval token ambiguity | Wrong/empty label | Prefer one-shot `/v3/edi/labels/*`; if two-step needed, resolve Q4 | ✅ Yes (Q4) |
| Partial item failure (some `idInformation` FAIL) | Mixed success reported inline, not as HTTP error | Parse per-item `errorResponse` inside `bookingResponse`; surface as `Message`s alongside details | ❌ No |
| MyPack Collect (service 19) needs a delivery service point | Cannot complete service-point delivery without point id | Document Service Points helper (D6); for now require `partyIdType 156` service-point id supplied by merchant | ❌ No |

---

## Problem Statement

### Current State

PostNord has **no connector** in the Karrio codebase. `grep -ri postnord` matches only git metadata — zero source, schema, test, or config files. Nordic merchants cannot ship, track, or rate via PostNord through Karrio.

```python
# Current state: PostNord is absent from the carrier registry.
# karrio.gateway["postnord"]  -> KeyError: no such carrier
```

### Desired State

A registered, tested PostNord connector exposing the capabilities, adapted to PostNord's real apikey API surface.

```python
import karrio.sdk as karrio

gateway = karrio.gateway["postnord"].create(
    dict(
        apikey="...",        # single credential — Booking, Pickup, Tracking, Service Points
        issuer_code="Z12",   # market: Sweden
        test_mode=True,
    )
)

# Shipping — Booking EDI, returns PDF/ZPL label inline (base64)
karrio.Shipment.create(shipment_request).from_(gateway)

# Rating — static/config rate table (no carrier call)
karrio.Rating.fetch(rate_request).from_(gateway)

# Manifest — pickup booking via /v3/pickups
karrio.Manifest.create(manifest_request).from_(gateway)

# Tracking — link-only: tracking_url + generic status (D7)
karrio.Tracking.fetch(tracking_request).from_(gateway)
```

### Problems

1. **No PostNord coverage** for SE/DK/NO/FI merchants.
2. **API-surface mismatch**: a naive four-feature build would assume rate and manifest endpoints PostNord does not publish. Rating and manifest must be adapted.
3. **Auth correction**: v1.0 assumed OAuth2; the authoritative spec is apikey-only. Building on OAuth2 would have been wrong.

---

## Goals & Success Criteria

### Goals

1. Ship a registered `postnord` connector discoverable via `./bin/cli plugins list | grep postnord`.
2. Implement shipping (book + cancel + label), rating (static), manifest (pickup-mapped), and tracking (link-only), each with the mandatory 4-method test suite.
3. Keep `mapper.py` and all `karrio/schemas/postnord/*.py` generated — never hand-edited.
4. Pass the full SDK suite (`./bin/run-sdk-tests`) with no regressions.

### Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Connector registered/discoverable | `plugins list` shows `postnord` | Must-have |
| Per-feature tests (shipping, rating, manifest, tracking) | 4 methods each, all passing | Must-have |
| SDK suite regressions | 0 | Must-have |
| Schema regeneration reproducible | `./bin/run-generate-on modules/connectors/postnord` idempotent | Must-have |
| Error responses parsed to `Message` | All error paths covered | Must-have |
| Tracking upgraded to events | Once a v5/v7 events spec is supplied | Nice-to-have |
| Live sandbox round-trip (book) | 1 successful end-to-end (gated on Q2) | Nice-to-have |

### Launch Criteria

**Must-have (P0):**
- [ ] CLI scaffolding committed unmodified where generated (esp. `mapper.py`)
- [ ] `schemas/*.json` source files derived from `postnord-booking.swagger.json`; `karrio/schemas/postnord/*.py` regenerated
- [ ] Shipping create + cancel (`updateIndicator: "Deletion"`) implemented and tested
- [ ] Rating (static) implemented and tested
- [ ] Manifest (pickup-mapped, `/v3/pickups`) implemented and tested
- [ ] Tracking (link-only) implemented and tested
- [ ] `python -m unittest discover -v -f modules/connectors/postnord/tests` passes
- [ ] `./bin/run-sdk-tests` passes

**Nice-to-have (P1):**
- [ ] Tracking upgraded to events (Track & Trace v5/v7)
- [ ] Service Points helper implemented (D6)
- [ ] Live sandbox validation against `atapi2.postnord.com`
- [ ] README documenting rating/manifest adaptations and apikey setup

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| apikey EDI Booking API (`/rest/shipment/v3/edi`, supplied spec) | Authoritative spec in hand; single credential; one-shot book+label | EDI booking variant rather than the OAuth2 `booking-sao` SAO surface | **Selected (D3)** |
| OAuth2 `shipment-v3-booking-sao` | "Current" per web docs; richer SAO model | Login-gated schema; OAuth2 complexity; the supplied spec is apikey-EDI and sufficient | Rejected |
| Hub/aggregator pattern in `community/plugins/` | Reuses multi-carrier scaffolding | PostNord is first-party — wrong abstraction | Rejected |
| Omit rating + manifest (shipping only) | Truthful to API | User requested four features; static rates + pickup-manifest deliver usable value | Rejected (D1/D2) |
| Surface transit-time as informational rates | Uses a real public API | Not money-rates; misleading; transit-time is a service-availability helper, not a rate | Rejected (D1) |
| Two-step label retrieval (`/v3/edi` then `/v3/labels/ids/*`) | Decouples booking from printing | Token ambiguity (Q4); extra round trip | Rejected for first pass (use one-shot) |

### Trade-off Analysis

The supplied `postnord-booking.swagger.json` is authoritative and apikey-based, so D3 follows the spec rather than the earlier web research that described an OAuth2 SAO variant — the spec wins on provenance. Choosing the one-shot `/v3/edi/labels/{pdf,zpl}` book-and-label path sidesteps the `id`-vs-`printId` retrieval ambiguity (Q4) and matches Karrio's single-call `create_shipment` contract. Rating-as-static and manifest-as-pickup keep rate-driven label flows and handover scheduling functional without fabricating carrier responses; both are documented limitations. Cancellation uses the spec-confirmed `updateIndicator: "Deletion"` re-POST since no DELETE route exists.

---

## Technical Design

> Studied existing code before designing. SEKO is the auth reference (apikey); USPS is the structural reference (JSON provider/test/manifest layout). Schema facts below come from `postnord-booking.swagger.json` (Swagger 2.0, host `api2.postnord.com`, basePath `/rest/shipment`).

### Existing Code Analysis

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| apikey proxy auth | `modules/connectors/seko/karrio/mappers/seko/proxy.py` | Pattern for injecting `apikey` (PostNord puts it in the **query string**, not a header) |
| Base `Settings` + `server_url` test/prod switch | `modules/connectors/usps/karrio/providers/usps/utils.py` | `atapi2` vs `api2` switching; single `apikey` field |
| Enum patterns (`StrEnum`, `OptionEnum`, list-of-codes `TrackingStatus`) | `modules/connectors/usps/karrio/providers/usps/units.py` | Source for `ShippingService`, `ShippingOption`, `PackagingType`, `TrackingStatus` |
| Manifest request/response + `ManifestDetails` | `modules/connectors/usps/karrio/providers/usps/manifest.py` | Reference shape; adapt target to `/v3/pickups` |
| Static service catalog (`DEFAULT_SERVICES`) | `modules/connectors/usps/karrio/providers/usps/units.py` (`load_services_from_csv`) | Optional pattern for static rate table (Q3) |
| 4-method test + `cached`/fixture | `modules/connectors/usps/tests/usps/` | Template for `tests/postnord/test_*.py`, `fixture.py` |
| Plugin registration metadata | `modules/connectors/usps/karrio/plugins/usps/__init__.py` | Template for `karrio/plugins/postnord/__init__.py` |
| Scaffolding command | `modules/cli/karrio_cli/commands/sdk.py` (`add-extension`) | Generates the whole tree; never hand-create files |

### Architecture Overview

```
┌──────────────┐     ┌──────────────┐     ┌────────────────────────────────┐
│   Karrio     │────>│   PostNord   │────>│      PostNord APIs (apikey)     │
│   SDK / API  │     │   Connector  │     │                                 │
└──────────────┘     └──────┬───────┘     │  Booking EDI  /rest/shipment    │
                            │             │    /v3/edi, /v3/edi/labels/*    │
              ┌─────────────┼──────────┐  │    /v3/pickups  (manifest=D2)   │
              │             │          │  │  Track URL    /rest/links (D7)  │
        ┌─────▼────┐  ┌─────▼────┐  ┌──▼──────┐ Service Points (D6, defer)  │
        │ settings │  │  proxy   │  │  units  │ (rating: none — static, D1) │
        │ (apikey) │  │ (?apikey)│  │ (enums) │ └───────────────────────────┘
        └──────────┘  └──────────┘  └─────────┘
```

### Sequence Diagram

```
┌────────┐     ┌────────┐     ┌────────┐     ┌──────────┐     ┌──────────┐
│ Client │     │  API   │     │ Mapper │     │  Proxy   │     │ PostNord │
└───┬────┘     └───┬────┘     └───┬────┘     └────┬─────┘     └────┬─────┘
    │ Shipment.create             │               │                │
    │─────────────>│              │               │                │
    │              │ create_shipment_request      │                │
    │              │─────────────>│ (ediInstruction)               │
    │              │              │──────────────>│ POST /v3/edi/  │
    │              │              │               │  labels/pdf    │
    │              │              │               │  ?apikey=...   │
    │              │              │               │───────────────>│
    │              │              │     ediLabelResponse           │
    │              │              │  (bookingResponse + label b64) │
    │              │              │<──────────────│<───────────────│
    │              │ parse_shipment_response      │                │
    │              │<─────────────│               │                │
    │ ShipmentDetails (tracking_number, label)    │                │
    │<─────────────│              │               │                │
```

### Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                         REQUEST FLOW                              │
├──────────────────────────────────────────────────────────────────┤
│  ┌─────────┐    ┌─────────────┐    ┌─────────────┐    ┌────────┐ │
│  │ Unified │───>│   Mapper    │───>│ediInstruction│──>│Booking │ │
│  │ Payload │    │ (transform) │    │ shipment[]   │   │  EDI   │ │
│  └─────────┘    └─────────────┘    └─────────────┘    └────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                         RESPONSE FLOW                             │
├──────────────────────────────────────────────────────────────────┤
│  ┌─────────┐    ┌─────────────┐    ┌──────────────────┐  ┌──────┐ │
│  │ Unified │<───│  Provider   │<───│ ediLabelResponse │<─│Booking│ │
│  │ Response│    │  (parse)    │    │ ids[] + label b64│  │ EDI  │ │
│  └─────────┘    └─────────────┘    └──────────────────┘  └──────┘ │
├──────────────────────────────────────────────────────────────────┤
│  RATING uses NO carrier call — Provider reads static rate table  │
│  from ConnectionConfig and synthesizes RateDetails (D1).         │
└──────────────────────────────────────────────────────────────────┘
```

### Data Models

```python
# modules/connectors/postnord/karrio/providers/postnord/utils.py
import attr
import karrio.core as core
import karrio.lib as lib


class IssuerCode(lib.Enum):
    """PostNord issuer/market codes (which entity holds the agreement)."""

    Z11 = "Denmark"
    Z12 = "Sweden"
    Z13 = "Norway"
    Z14 = "Finland"
    ZDL = "Direct Link"


@attr.s(auto_attribs=True)
class Settings(core.Settings):
    """PostNord connection settings — single apikey credential.

    The Booking (EDI) and Service Points APIs are SECURED: False and take
    `apikey` as a query parameter on every request.
    """

    apikey: str = None          # query param — Booking, Pickup, Tracking, Service Points
    issuer_code: str = "Z12"    # market: Z11 DK / Z12 SE / Z13 NO / Z14 FI
    customer_number: str = None # consignor partyId (partyIdType 160)

    id: str = None
    test_mode: bool = False
    carrier_id: str = "postnord"
    account_country_code: str = "SE"
    metadata: dict = {}
    config: dict = {}

    @property
    def carrier_name(self):
        return "postnord"

    @property
    def server_url(self):
        return (
            "https://atapi2.postnord.com"
            if self.test_mode
            else "https://api2.postnord.com"
        )
```

```python
# modules/connectors/postnord/karrio/mappers/postnord/proxy.py (pattern)
class Proxy(proxy.Proxy):
    settings: Settings

    def create_shipment(self, request: lib.Serializable) -> lib.Deserializable:
        response = lib.request(
            url=f"{self.settings.server_url}/rest/shipment/v3/edi/labels/pdf?apikey={self.settings.apikey}",
            data=lib.to_json(request.serialize()),
            trace=self.trace_as("json"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        return lib.Deserializable(response, lib.to_dict)
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `apikey` | string | Yes | Query-param credential for all PostNord calls |
| `issuer_code` | string | No | `Z11`–`Z14`/`ZDL`; default `Z12` (Sweden) |
| `customer_number` | string | For shipping | Consignor `partyId` (`partyIdType` 160) |
| `test_mode` | bool | No | Switches `atapi2` (sandbox) vs `api2` (prod) |

<!-- INTEGRATION -->
### API Changes

**Endpoints (from `postnord-booking.swagger.json`, basePath `/rest/shipment`, apikey query param):**

| Method | Endpoint | Karrio op | Notes |
|--------|----------|-----------|-------|
| POST | `/v3/edi/labels/pdf` (or `/zpl`) | `create_shipment` | One-shot book + label; body `ediInstruction` |
| POST | `/v3/edi` | `cancel_shipment` | Re-POST with `updateIndicator: "Deletion"` |
| POST | `/v3/pickups` | `create_manifest` (mapped, D2) | Books physical pickup |
| GET | `/v1/tracking/{country}/{id}` (base `/rest/links`) | `get_tracking` (link-only, D7) | Returns `LinksResponse{ url, faults[] }`; `country` ∈ SE/NO/FI/DK, `id` 10–35 chars |
| GET | `/v5/servicepoints/nearest/byaddress` (base `/rest/businesslocation`) | `get_service_points` (D6, deferred) | Service-point lookup |
| — | (no endpoint) | `get_rates` | Static table (D1) |

**Request — `ediInstruction` (booking body, key shape):**

```json
{
  "messageDate": "2026-06-24T10:00:00",
  "updateIndicator": "Original",            // "Deletion" to cancel
  "application": { "name": "Karrio" },
  "shipment": [{
    "service": { "basicServiceCode": "18", "additionalServiceCode": ["A1"] },
    "parties": {
      "consignor": {
        "issuerCode": "Z12",
        "partyIdentification": { "partyId": "<customer_number>", "partyIdType": "160" },
        "party": { "nameIdentification": { "name": "..." },
                   "address": { "streets": ["..."], "postalCode": "...", "city": "...", "countryCode": "SE" } }
      },
      "consignee": {
        "party": { "nameIdentification": { "name": "..." },
                   "address": { "postalCode": "...", "city": "...", "countryCode": "SE" },
                   "contact": { "emailAddress": "...", "smsNo": "..." } }
      }
    },
    "goodsItem": [{
      "packageTypeCode": "PC",
      "items": [{ "itemIdentification": { "itemId": "...", "itemIdType": "..." },
                  "grossWeight": { "value": 1.5, "unit": "KGM" },
                  "dimensions": { "height": 10, "width": 20, "length": 30 } }]
    }]
  }]
}
```

**Response — `ediLabelResponse`:**

```json
{
  "bookingResponse": {
    "bookingId": "...",
    "idInformation": [{
      "status": "OK",
      "ids": [
        { "idType": "itemId", "value": "00373500454541020957", "printId": "..." },
        { "idType": "shipmentId", "value": "...", "printId": "..." }
      ],
      "urls": [{ "type": "TRACKING", "url": "https://tracking.postnord.com/se/?id=..." }],
      "errorResponse": null
    }]
  },
  "labelPrintout": [{
    "printout": { "type": "LABEL", "labelFormat": "PDF", "encoding": "base64", "data": "<base64>" }
  }]
}
```

- Tracking number ← `idInformation[].ids[]` where `idType == "itemId"`; shipment id ← `idType == "shipmentId"`.
- Label ← `labelPrintout[].printout.data` (base64, inline) or `printout.uriResource` (URL).
- Error ← `errorResponse { message, compositeFault.faults[]{ explanationText, faultCode } }`; partial failures appear inline per `idInformation[]`.

---

## Edge Cases & Failure Modes

### Edge Cases

| Scenario | Expected Behavior | Handling |
|----------|-------------------|----------|
| Rate requested for service absent from static table | Empty rate list, no crash | Return `[]` + informational `Message` (D1) |
| Cancellation (no DELETE route) | Booking voided | Re-POST `ediInstruction` `updateIndicator: "Deletion"` to `/v3/edi` |
| Partial item failure | Mixed OK/FAIL reported inline | Parse per-item `idInformation[].errorResponse` → `Message`s |
| `testIndicator` requested | Validate-only, no booking | Map a Karrio test/validation flag to `ediInstruction.testIndicator` |
| Empty/null booking response | No crash | Guard truthiness before extracting `ids`/`labelPrintout` |
| International parcel to non-Nordic country | Service 91 / DPD routing | Validate service availability; `Message` on unsupported combo |

### Failure Modes

| What Can Go Wrong | Impact | Mitigation |
|-------------------|--------|------------|
| `apikey` invalid/expired | All ops fail | Parse `errorResponse` → `Message`; `test_parse_error_response` covers it |
| Two-step label token mismatch (Q4) | Label fetch fails | Use one-shot `/v3/edi/labels/*` path in first pass |
| Static rate table stale vs contract | Wrong rate shown | Document as merchant responsibility; rates are config, not carrier truth (D1) |
| Pickup slots unavailable for manifest | Manifest "fails" | Surface Pickups error as `Message` |
| Merchants expect rich tracking events from PostNord | Medium | Document link-only limitation in README; offer v5/v7 events upgrade path |

### Security Considerations

- [ ] `apikey` marked sensitive (`attr.ib(metadata={"sensitive": True})`); never logged or traced; note it travels in the query string — ensure trace redaction covers URL query params
- [ ] Multi-tenancy preserved — credentials scoped to the carrier connection / org
- [ ] No secrets in fixtures (use a fake `apikey`)
- [ ] Input validation for postal/country codes before request build

---

## Implementation Plan

### Phase 1: Scaffold, settings, schemas

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Scaffold via CLI (`--features "tracking, rating, shipping, manifest"`, `--is-xml-api false`) | `modules/connectors/postnord/**` | Pending | S |
| Derive source schemas from `postnord-booking.swagger.json` | `modules/connectors/postnord/schemas/*.json` | Pending | M |
| Generate Python types | `karrio/schemas/postnord/*.py` (generated) | Pending | S |
| Single-apikey Settings + `server_url` + `IssuerCode` | `.../mappers/postnord/settings.py`, `.../providers/postnord/utils.py` | Pending | S |

### Phase 2: Proxy & provider logic

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| apikey query-param proxy (book/cancel/pickup) | `.../mappers/postnord/proxy.py` | Pending | M |
| Service / option / status / package / issuer enums | `.../providers/postnord/units.py` | Pending | M |
| Shipping create (one-shot label) + cancel (Deletion) | `.../providers/postnord/shipment/{create,cancel}.py` | Pending | L |
| Rating (static table from `ConnectionConfig`) | `.../providers/postnord/rate.py` | Pending | M |
| Manifest → `/v3/pickups` | `.../providers/postnord/manifest.py` | Pending | M |
| Tracking (link-only: `tracking_url` + generic status, D7) | `.../providers/postnord/tracking.py` | Pending | S |
| Error parsing (`errorResponse`/`compositeFault`, `LinksResponse.faults`) | `.../providers/postnord/error.py` | Pending | S |

**Dependencies:** Phase 2 depends on Phase 1; `mapper.py` left untouched from scaffolding.

### Phase 3: Tests & registration

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| `fixture.py` with fake apikey + `gateway` | `tests/postnord/fixture.py` | Pending | S |
| 4-method tests: shipment, rate, manifest, tracking | `tests/postnord/test_*.py` | Pending | L |
| Verify `plugins list`/`plugins show` | — | Pending | S |
| Full SDK suite green | — | Pending | S |

### Phase 4: Deferred enhancements

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Upgrade tracking to events (Track & Trace v5/v7) | `.../providers/postnord/tracking.py`, schemas from a v5/v7 spec | Deferred (needs events spec) | M |
| Service Points helper (D6) | `.../providers/postnord/...`, schemas from `postnord-servicepoints-v5.swagger.json` | Deferred | M |

---

## Testing Strategy

> All tests use `unittest` (never pytest), run from repo root after `source bin/activate-env`, with `assertDictEqual`/`assertListEqual` and `mock.ANY` for dynamic fields. The `fixture.py` uses a fake `apikey` (no live calls; apikey auth needs no token pre-seeding, unlike OAuth carriers).

### Test Categories

| Category | Location | Coverage Target |
|----------|----------|-----------------|
| Connector unit tests | `modules/connectors/postnord/tests/postnord/test_*.py` | 4 methods × each feature |
| SDK regression | `./bin/run-sdk-tests` | No regressions |

### Test Cases

Per feature, exactly four methods (per `.claude/rules/carrier-integration.md`):

```python
"""tests/postnord/test_shipment.py — pattern mirrors USPS/SEKO."""

import unittest
from unittest.mock import patch, ANY
import karrio.sdk as karrio
import karrio.lib as lib
from .fixture import gateway


class TestPostNordShipment(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_create_shipment_request(self):
        request = gateway.mapper.create_shipment_request(
            lib.to_object(..., ShipmentPayload)
        )
        self.assertEqual(request.serialize(), ShipmentRequest)

    def test_create_shipment(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(...).from_(gateway)
            self.assertIn("/v3/edi/labels/pdf", mock.call_args[1]["url"])

    def test_parse_shipment_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ShipmentResponse
            parsed = karrio.Shipment.create(...).from_(gateway).parse()
            self.assertListEqual(lib.to_dict(parsed), ParsedShipmentResponse)

    def test_parse_error_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ErrorResponse
            parsed = karrio.Shipment.create(...).from_(gateway).parse()
            self.assertListEqual(lib.to_dict(parsed), ParsedErrorResponse)


# Module-level fixtures: ShipmentPayload, ShipmentRequest, ShipmentResponse,
# ErrorResponse, ParsedShipmentResponse, ParsedErrorResponse
```

### Running Tests

```bash
# From repository root
source bin/activate-env

python -m unittest discover -v -f modules/connectors/postnord/tests
./bin/run-sdk-tests
./bin/cli plugins list | grep postnord
```

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Link-only tracking has no events (D7) | Medium | High (by design) | Document the limitation; populate `tracking_url` + generic status; upgrade path to v5/v7 events |
| No sandbox apikey (Q2) | Medium | Medium | Mock-driven tests need no key; defer live round-trip to P1 |
| Rating-as-static misread as carrier rates | Medium | Medium | Document in README + `Message` annotations |
| Manifest-as-pickup semantic mismatch | Medium | Medium | Document mapping; cancel routes to pickup cancel |
| Label-by-id token ambiguity (Q4) | Low | Low | Use one-shot label path; avoid two-step retrieval |
| apikey leakage via query-string traces | High | Low | Mark sensitive; verify trace redaction covers URL params |
| SDK suite regression | Medium | Low | Run `./bin/run-sdk-tests` before merge |

---

## Migration & Rollback

### Backward Compatibility

- **API compatibility**: additive only — a new carrier registration. No existing carrier/model/endpoint changes. No database migration.
- **Data compatibility**: no schema/data changes; the connector is self-contained under `modules/connectors/postnord/`.
- **Feature flags**: none required; the connector is inert until a merchant configures a PostNord connection.

### Rollback Procedure

1. **Identify issue**: errors isolated to `postnord` carrier connections.
2. **Stop rollout**: disable/remove the PostNord connection in affected orgs.
3. **Revert changes**: remove/uninstall `modules/connectors/postnord/`; no data cleanup (additive-only).
4. **Verify recovery**: `./bin/run-sdk-tests` green; other carriers unaffected.

---

## Appendices

### Appendix A: Resolved design decisions

D1 rating=static/config; D2 manifest=`/v3/pickups`; D3 auth=apikey EDI generation (per supplied spec); D4 direct-carrier location; D5 SEKO(auth)+USPS(structure) references; D6 Service Points documented/deferred; D7 tracking link-only (no events).

### Appendix B: Environments

| | Booking/Pickup/Tracking host | Service Points base | Portal |
|---|---|---|---|
| Sandbox | `https://atapi2.postnord.com/rest/shipment` | `https://atapi2.postnord.com/rest/businesslocation` | `atdeveloper.postnord.com` |
| Production | `https://api2.postnord.com/rest/shipment` | `https://api2.postnord.com/rest/businesslocation` | `developer.postnord.com` |

<!-- INTEGRATION -->
### Appendix C: Carrier-Specific Reference

**Spec provenance:** the swagger files are manually downloaded from the PostNord developer portal's active-APIs listing at <https://developer.postnord.com/apis/active>. There is **no permanent download URL** for any spec — the portal serves only the currently-active versions, so refreshing a spec means re-downloading from that page (and the `info.version` may drift between downloads). Treat the committed copies as point-in-time snapshots; re-capture and regenerate when a version bump is needed.

**Authoritative specs (vendored as point-in-time snapshots at `modules/connectors/postnord/vendor/`):**
- `vendor/booking.swagger.json` — Swagger 2.0, `Booking APIs` v3.5.29.1, host `api2.postnord.com`, basePath `/rest/shipment`, apikey query param, `SECURED: False`.
- `vendor/servicepoints-v5.swagger.json` — OpenAPI 3.0.0, `Service Points V5` v5.0.14, base `/rest/businesslocation`, apikey query param.
- `vendor/tracking-url.swagger.json` — Swagger 2.0, `Track Shipment URL` v1.0.2, host `api2.postnord.com`, basePath `/rest/links`, apikey query param. `GET /v1/tracking/{country}/{id}` → `LinksResponse{ url, faults[] }` (URL only, **no events** — drives D7's link-only tracking).

**Codes (free-form strings in the spec; enumerate in `units.py` from PostNord General Descriptions):**

| Kind | Values |
|------|--------|
| `basicServiceCode` (subset) | 17 MyPack Home, 18 Parcel, 19 MyPack Collect, 20 Return Pickup, 52 Pallet, 91 Postpaket Utrikes |
| `additionalServiceCode` (subset) | A1 COD, A5 Insurance, A7 Optional Service Point, C7 FlexChange, E4 Collect In-Store, F6 Early Collect |
| `issuerCode` | Z11 DK, Z12 SE, Z13 NO, Z14 FI, ZDL Direct Link |
| `packageTypeCode` | PC Parcel, PE EUR Pallet, AF Half Pallet, OA Quarter Pallet, OF Special Pallet, CW Cage Roll, BX Box, EN Envelope |
| `partyIdType` | 160 Customer no., 167 VAT customer no., 156 Service point id, 229 Geographic location |

**Field Mappings:**

| Karrio Field | Carrier Field | Notes |
|--------------|---------------|-------|
| `tracking_number` | `idInformation[].ids[]` (`idType=itemId`) | `shipmentId` for shipment-level |
| `tracking_url` | `LinksResponse.url` | From `/rest/links/v1/tracking/{country}/{id}` (D7) |
| `service` | `service.basicServiceCode` | `ShippingService` enum |
| options | `service.additionalServiceCode[]` | `ShippingOption` enum |
| `recipient`/`shipper` | `parties.consignee`/`consignor` | `issuerCode` + `partyIdentification` |
| `label` | `labelPrintout[].printout.data` | base64 PDF/ZPL/SVG; or `uriResource` URL |
| cancel | `updateIndicator: "Deletion"` | no DELETE route |
```
