# PRD: PostNord Integration

<!-- INTEGRATION -->

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 2.0 |
| Date | 2026-09-24 |
| Status | Implemented |
| Owner | Joaqim Planstedt |
| Type | Integration |
| Reference | [AGENTS.md](../AGENTS.md), [CARRIER_INTEGRATION_GUIDE.md](../CARRIER_INTEGRATION_GUIDE.md), [TRACKER_LOCALE_PERSISTENCE.md](./TRACKER_LOCALE_PERSISTENCE.md) |

This document consolidates the connector's design record: the decisions taken, the constraints and gaps of PostNord's published API, and the alternatives that were rejected.
Carrier-neutral tracker locale persistence is specified in [TRACKER_LOCALE_PERSISTENCE.md](./TRACKER_LOCALE_PERSISTENCE.md) and is not repeated here.

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
12. [Future Work](#future-work)
13. [Appendices](#appendices)

---

## Executive Summary

PostNord is the Nordic postal and logistics carrier for Sweden, Denmark, Norway, and Finland.
This connector (`modules/connectors/postnord/`, a direct carrier) integrates its Booking (EDI) v3, Track & Trace v7, Transit Time v2, and Service Points v5 APIs.
PostNord publishes no money-rate API and no end-of-day manifest, so rating and manifest are adapted to what the API supports, and REST cancellation is not available at all.

### Key Architecture Decisions

1. **Single `apikey` query-parameter credential**: every PostNord API used here is `SECURED: False` and takes `?apikey=`; authorization is granted per API product.
2. **Static rating through the universal rate-sheet engine**: prices come from the connection's server-side `RateSheet`; an opt-in Transit Time lookup only enriches transit days and filters unbookable services.
3. **One-shot booking and label**: `POST /rest/shipment/v3/edi/labels/{pdf,zpl}` books and returns the label; the file format is chosen by endpoint path.
4. **Connector-local capabilities for what Karrio has no unified contract for**: service-point lookup and post-booking customs declaration are proxy methods reached through `gateway.proxy`.
5. **Cancellation never reports false success**: the id-based delete endpoint is absent from the published spec, so cancel returns an explicit `cancellation_unsupported` message.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| Rating from the rate sheet, opt-in transit-time enrichment, letter-service gating | Live money-rate quoting (no PostNord API) |
| Booking with PDF/ZPL labels, label size, returns via return service codes | Shipment cancellation (no documented REST endpoint) |
| Track & Trace v7 events with link-only fallback | End-of-day manifest documents (no PostNord endpoint) |
| Pickup scheduling (`/v3/pickups`) | Pickup update and cancel (no PostNord route) |
| Service-point lookup (connector-local) | A unified Karrio service-point contract |
| Booking locale, recipient-country locale, entry code, notification options | Karrio-native notification pipeline |
| CN22 customs at booking, standalone customs document, post-booking declarations | Automatic CN23 and customs-invoice embedding; NVIT data set (see [Future Work](#future-work)) |

---

## Open Questions & Decisions

### Pending Questions

| # | Question | Context | Status |
|---|----------|---------|--------|
| Q1 | Which endpoint cancels a booking? | `/v3/edi` ignores `updateIndicator: "Deletion"` and books a duplicate (verified live); the swagger's `deleteEdiRequest {ids:[{id}]}` body has no documented endpoint | Pending PostNord's v3 REST reference manual |
| Q2 | Handling when a declared value exceeds the CN22 ceiling (300 SDR) | Field error versus escalation to CN23; the only local signal is the swagger note that CN23 `commercialItems` apply above 200 EUR | Deferred until sandbox evidence exists |
| Q3 | Should Åland (`AX`, Swedish-speaking) map to `sv` in `CountryLocale`? | The mapping covers SE, DK, NO, FI only | Deferred |
| Q4 | NVIT declaration branch, net-weight modeling, per-parcel linkage | See [Future Work](#future-work) | Pending PostNord confirmation |

### Resolved Decisions

| # | Area | Decision | Rationale |
|---|------|----------|-----------|
| D1 | Auth | One `apikey` setting, appended to every URL by `Proxy._url` | The Booking, Pickup, Tracking, Transit Time, and Service Points specs are `SECURED: False` with an `apikey` query parameter |
| D2 | Auth errors | Surface the API-gateway envelope `{"error": {status_code, error_type, message}}` as an error message stating the key is not authorized for the product | PostNord authorizes each API product separately; a 403 "Invalid API Key" means a missing product subscription, not a malformed key |
| D3 | Rating | `Settings` inherits `RatingMixinSettings`; the proxy delegates to `RatingMixinProxy.get_rates`; `DEFAULT_SERVICES` seeds the catalog with `rate=0.0` placeholders | No PostNord money-rate API; merchant contract prices live in the server `RateSheet`, matching the `generic` carrier pattern |
| D4 | Transit times | Opt-in `enable_transit_times` (default off) calls Transit Time v2 once per rate request to set `transit_days`, `meta.estimated_delivery`, and drop unbookable services | Keys without a Transit Time subscription get 403, so always-on enrichment would warn on every rate for most accounts |
| D5 | Transit degrade | Any transit failure keeps static transit days, applies no filtering, and adds one warning (`transit_time_unauthorized` for 401/403, else `transit_time_unavailable`) naming the opt-in setting | Price rating must never fail because of an enrichment call |
| D6 | Transit variants | Map only the base entry (no `additionalServices`) per `basicServiceCode` | The response lists one entry per variant (`18`, `18+Q1`, …) with differing bookability; the catalog is keyed on bare codes |
| D7 | Transit not-found | An entry with `isSupported=false` (or a "Requested service …" message) keeps the static rate with no message; a route rejection drops the rate with an info `service_not_bookable` message | "Requested service 'SE-37' not found." marks services absent from the transit system (37, 48, 49, 51), not route verdicts |
| D8 | Letter services | Tracked Letter (34) and Export Letter (UX) are rated only when `offer_tracked_letter` / `offer_export_letter` are on; UX additionally requires issuer `Z12`; gating filters `settings.shipping_services` | Keeps the default catalog unchanged; the universal engine and dashboard need no change |
| D9 | Issuer code | `issuer_code` stays a user-set connection setting (Z11–Z14) | It encodes the merchant's market agreement and drives letter gating, so it cannot be derived from a shipment's origin |
| D10 | Booking ids | `itemId="0"` lets PostNord allocate the parcel id (the tracking number); `shipmentId` is the caller reference or a generated id | An arbitrary item id fails with "unable to determine id type"; the client shipment id makes bookings searchable in Track & Trace |
| D11 | Partial bookings | Any item with allocated ids yields shipment details; inline per-item faults surface as messages alongside them | PostNord reports mixed item outcomes inside a 200/201 body |
| D12 | Label format | `label_type` resolves payload → connection `label_type` → `PDF` and selects `/labels/pdf` or `/labels/zpl`; `label_size` (`standard`/`small`/`ste`) is the `labelType` query parameter, omitted when unset | PostNord selects the file format only by endpoint path |
| D13 | Label encoding | Printouts with `encoding` `base64` or absent pass through; any other encoding is raw text and is base64-encoded | ZPL printouts arrive as raw UTF-8 with `encoding: "none"`, which the swagger does not document; Karrio's label pipeline expects base64 |
| D14 | Tracking | Track & Trace v7 `findByIdentifier` keyed by the tracking number; 13 `ItemStatus` values map onto `TrackerStatus` (unknown → `in_transit`); no usable item degrades to a link-only result | The v7 `id` accepts the allocated item id; per-product authorization means T&T can 403 while booking works |
| D15 | Pickup vs manifest | `Pickup.schedule` → `POST /v3/pickups` with a consignor-only body; `Manifest.create`, `Pickup.update`, and `Pickup.cancel` return `not_supported` without an HTTP call | `/v3/pickups` is a courier collection, not a scan form; pickups support only `Original` |
| D16 | Service points | Connector-local `find_service_points` proxy method over Service Points v5 (`byaddress`, or `bycoordinates` when northing/easting are given), parsed into plain dicts | Karrio has no unified service-point contract; the duck-typed proxy-method pattern needs no core change |
| D17 | Booking locale | Locale resolves request `options.language` > `config.language` > recipient country (with `locale_by_recipient`) > `en`; sent lowercase as the `locale` query parameter and uppercase as the body `language` element | The query `locale` sets SMS/e-mail language; the body `language` sets label text; `en` matches the Track & Trace default |
| D18 | Recipient-country locale | `CountryLocale` maps SE→sv, DK→da, NO→no, FI→fi; `Settings.recipient_locale` returns it when `locale_by_recipient` is on and `config.language` is unset | The server persists the derived locale on the shipment and its tracker through the carrier-neutral hook, so polls keep it |
| D19 | Entry code | `options.entry_code` (string, coerced and stripped, max 50 chars) becomes a shipment `freeText` with usage code `ZDC`; over-length values reject the booking with an `ENTRY_CODE_LENGTH` message and no HTTP call | ZDC is printed as "Ref 2"; no PostNord source lists which services accept it, so it passes through unverified; a truncated door code is a wrong door code |
| D20 | Notifications | `sms_notification` → A3, `email_notification` → A4, plus `postnord_notify_by_letter` (A2), `postnord_notify_by_phone` (A9), `postnord_driver_notification` (B8); codes are emitted only for truthy option states | PostNord notifications are an additive opt-in menu with no suppress flag; an explicit `False` must mean opt-out |
| D21 | Booking customs | Unified `customs` maps to the `customsDeclarationCN22` branch when commodities are present; `content_type` resolves through `CN22CategoryType`; registration numbers come from `customs.options` via a provider `CustomsOption` enum | CN22 is the only branch fully derivable from the unified model; the core `CustomsOption` enum lacks `voec_number`/`ioss_number`, which the typed-options helper would drop |
| D22 | Misplaced registration numbers | `eori_number`/`voec_number`/`ioss_number` under shipment `options` reject a customs booking with a field error | Unknown shipment options are dropped silently, and PostNord rejects a CN22 without any of them (`SACUS-BR-24062502`) |
| D23 | Line limit | At most 13 `detailedDescription` lines per declaration, enforced by one shared guard at booking and in the declaration builder | Documented in PostNord's Booking Customs Information; the swagger has no `maxItems` |
| D24 | Standalone customs document | Export-letter bookings with an embedded declaration fetch `POST /v3/labels/ids/{pdf,zpl}?definePrintout=onlyCustomsDeclarations` keyed by `printId` (item id as fallback) and attach results to `docs.extra_documents`; failures are messages, never booking failures | Merged booking printouts carry composition counts without page ranges; the by-id endpoint resolves `printId`, not the item id (verified live) |
| D25 | Post-booking declaration | `create_customs_declaration` and `create_customs_declaration_pdf` proxy methods take a caller-built declaration (one id, one branch); Karrio builds the envelope, submits, and reports | The caller owns branch, ids, and update semantics; Karrio does not reconcile or retract declarations |

---

## Problem Statement

### Current State

Karrio has no PostNord connector, so Nordic merchants cannot rate, book, track, or collect PostNord shipments.

```python
karrio.gateway["postnord"]  # KeyError: no such carrier
```

### Desired State

```python
import karrio.sdk as karrio

gateway = karrio.gateway["postnord"].create(
    dict(apikey="...", customer_number="...", application_id="...", test_mode=True)
)
karrio.Rating.fetch(rate_request).from_(gateway)        # rate sheet, optional transit times
karrio.Shipment.create(shipment_request).from_(gateway) # booking + PDF/ZPL label
karrio.Tracking.fetch(tracking_request).from_(gateway)  # Track & Trace v7 events
karrio.Pickup.schedule(pickup_request).from_(gateway)   # courier collection
```

### Problems

1. PostNord's API surface does not match Karrio's operations one-to-one: no rates, no manifest, no REST cancellation.
2. The published swagger omits behaviors observed live (ZPL transport encoding, `printId` keying, registration-number rule), which the connector has to encode explicitly.

---

## Goals & Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Connector registered and discoverable | `karrio.gateway["postnord"]` resolves | Must-have |
| Rate, shipment, tracking, pickup tests | Request, proxy, parse, and error paths covered | Must-have |
| Unsupported operations | Explicit messages, never false success | Must-have |
| Generated files | `mapper.py` and `karrio/schemas/postnord/*.py` never hand-edited | Must-have |
| Live verification | Booking, label, tracking, and pickup verified against the sandbox; customs declaration verified on a production booking | Done |

---

## Alternatives Considered

| Approach | Decision | Reason |
|----------|----------|--------|
| OAuth2 `booking-sao` surface | Rejected | The supplied Booking spec is apikey EDI and sufficient; the SAO schema is login-gated |
| Bespoke `ConnectionConfig.rate_table` | Rejected | Duplicates the universal rate-sheet engine, its CSV import, and CRUD |
| Transit times surfaced as rates | Rejected | Transit data is serviceability, not price |
| Two-step booking then `/v3/labels/ids` for labels | Rejected | Extra round trip and id-token ambiguity; the one-shot path returns the label |
| Cancel by re-posting `updateIndicator: "Deletion"` | Rejected | Books a duplicate shipment (verified live) |
| Manifest mapped onto `/v3/pickups` | Rejected | Forced a degenerate consignee and conflated manifest with courier collection |
| Origin-derived `issuerCode` with a Nordic-origin guard | Rejected | `issuer_code` is a market agreement read by letter gating; PostNord documents no closed origin set |
| Content sniffing (`^XA`/`%PDF`) for label encoding | Rejected | The response carries `encoding`; sniffing is brittle for short payloads |
| Book PDF and convert to ZPL (Labelary) | Rejected | External dependency and fidelity loss in the label path |
| Track & Trace v7 `findByReference` | Rejected | Keys on the client reference plus customer number, not the tracking number Karrio stores |
| First-class SDK service-point capability | Rejected | Shared-core design decision; the connector-local method is forward compatible |
| Entry code as an `additionalServiceCode` or connection default | Rejected | Service codes carry no value; door codes differ per recipient |
| Truncating over-length entry codes | Rejected | Produces a wrong door code silently |
| Suppressing notifications by clearing consignee contact slots | Rejected | Breaks mandatory contact-data rules of services 17, 20, 24 |
| Enforcing per-service notification rules client-side | Rejected | Duplicates PostNord validation of rules only documented in prose |
| Choosing CN22/CN23/invoice per shipment at booking | Rejected | Invents threshold semantics the spec does not document |
| Splitting the booking printout into label and customs pages | Rejected | Composition counts carry no page ranges |
| Plain-dict customs declaration bodies | Rejected | Deeply structured bodies benefit from generated types |

---

## Technical Design

### Existing Code Analysis

| Component | Location | Reuse |
|-----------|----------|-------|
| Universal rate-sheet engine | `karrio.universal.mappers.rating_proxy`, `karrio.universal.providers.rating` | Price resolution and zone matching |
| Duck-typed proxy capability | `plugins/googlegeocoding` (`validate_address`) | `find_service_points`, `create_customs_declaration*` |
| Unified extra documents | `models.Documents.extra_documents`, `models.ShippingDocument` | Standalone customs documents |
| Label bundling | `lib.bundle_base64` | Multi-printout labels |
| Recipient locale hook | `Settings.recipient_locale` (SDK) | Recipient-country locale at purchase |
| Enum and option patterns | `usps`, `seko` connectors | `ShippingService`, `ShippingOption`, `ConnectionConfig` |

### Architecture Overview

```
┌──────────────┐    ┌───────────────────────────────┐    ┌──────────────────────────────┐
│ Karrio SDK / │───>│ postnord connector            │───>│ PostNord APIs (?apikey=)      │
│ server       │    │                               │    │                              │
└──────────────┘    │ settings: apikey, issuer_code │    │ /rest/shipment/v3/edi/labels │
                    │   rate sheet, letter gating,  │    │ /rest/shipment/v3/labels/ids │
                    │   recipient_locale            │    │ /rest/shipment/v3/customs/*  │
                    │ proxy: _url + one method per  │    │ /rest/shipment/v3/pickups    │
                    │   operation                   │    │ /rest/shipment/v7/trackand…  │
                    │ providers: request builders + │    │ /rest/transport/v2/transit…  │
                    │   parsers, error.py, units.py │    │ /rest/businesslocation/v5/…  │
                    └───────────────────────────────┘    └──────────────────────────────┘
```

### Sequence Diagram: booking with customs

```
Caller          create.py              Proxy                         PostNord
  │ ShipmentRequest │                    │                               │
  ├────────────────>│ resolve label_type, locale, entry_code, CN22      │
  │                 │ ctx = {shipment_id, label_type, locale,           │
  │                 │        entry_code_error, basic_service_code,      │
  │                 │        customs_declared}                           │
  │                 ├───────────────────>│ entry_code_error? → fault body (no call)
  │                 │                    ├── POST /v3/edi/labels/{fmt} ─>│
  │                 │                    │<──── ediLabelResponse ────────┤
  │                 │                    │ UX + customs_declared?        │
  │                 │                    ├── POST /v3/labels/ids/{fmt} ─>│
  │                 │                    │   definePrintout=onlyCustoms  │
  │                 │                    │<──── labelPrintout[] ─────────┤
  │                 │<── Deserializable(response, ctx + customs results) │
  │ ShipmentDetails (label, extra_documents) + messages                  │
  │<────────────────┤                    │                               │
```

### Data Flow Diagram: locale and label format

```
options.language ──┐
config.language ───┼─> locale ─┬─> ?locale=xx      (SMS / e-mail text)
recipient country ─┤  (first   └─> "language": "XX" (label text)
 (locale_by_       │   set)
  recipient)       │
"en" ──────────────┘

payload.label_type ─┐
config.label_type ──┼─> PDF | ZPL ─> /v3/edi/labels/pdf | /v3/edi/labels/zpl
"PDF" ──────────────┘
config.label_size ─────> ?labelType=standard|small|ste (omitted when unset)
```

### API Changes

| Method | Endpoint | Karrio operation |
|--------|----------|------------------|
| — | (no carrier call) | `get_rates` from the rate sheet |
| GET | `/rest/transport/v2/transittime/addresstoaddress` | `get_rates` enrichment (opt-in) |
| POST | `/rest/shipment/v3/edi/labels/{pdf,zpl}` | `create_shipment`, returns |
| POST | `/rest/shipment/v3/labels/ids/{pdf,zpl}` | standalone customs document (export letters) |
| POST | `/rest/shipment/v3/edi` | `cancel_shipment` placeholder body `{ids:[{id}]}`, rejected by PostNord |
| POST | `/rest/shipment/v3/pickups` | `schedule_pickup` |
| GET | `/rest/shipment/v7/trackandtrace/id/{id}/public` | `get_tracking` |
| GET | `/rest/businesslocation/v5/servicepoints/nearest/{byaddress,bycoordinates}` | `find_service_points` (connector-local) |
| POST | `/rest/shipment/v3/customs/declaration[/pdf]` | `create_customs_declaration[_pdf]` (connector-local) |

### API Constraints and Spec Gaps

| Topic | Published spec | Observed or documented elsewhere | Connector handling |
|-------|----------------|----------------------------------|--------------------|
| Cancellation | `deleteEdiRequest` body, no endpoint | `/v3/edi` books a duplicate on `Deletion` | Placeholder body; explicit unsupported message |
| ZPL printout encoding | `encoding` "base64" only | `/labels/zpl` returns raw UTF-8 with `encoding: "none"`, sometimes without `labelFormat` | Encode non-base64 printouts; fall back to the requested format |
| By-id printout key | Examples use item ids | Real bookings resolve by `printId`; item id yields per-id `FAIL "id not found"` | Key by `printId`, fall back to item id |
| By-id error reporting | — | HTTP error bodies that still parse as `labelPrintout` arrays with per-id `FAIL` members | Inspect members; report per-id failures and empty results |
| CN22 registration numbers | Optional fields | `SACUS-BR-24062502` rejects a CN22 without EORI, VOEC, or IOSS | Pass through `customs.options`; reject misplaced keys |
| Declaration line limit | No `maxItems` | 13 lines per item id (Booking Customs Information) | Shared pre-submission guard |
| Digital declaration response | `bookingResponseCN` | Bare object; only the PDF variant wraps it under `bookingResponse` | Parser accepts both |
| Body `language` | "ISO 3166 country code", example `EN` | Language codes are accepted | Uppercase ISO 639-1 |
| Entry code usage code | `freeText.usageCode` list omits ZDC | General descriptions: "ZDC … Door code", printed as Ref 2 | Pass through unverified |
| Per-product authorization | `SECURED: False` | Gateway 403 "Invalid API Key" per unsubscribed product | Explicit authorization message; tracking and transit degrade |
| `applicationId` | Optional | Required as an integer by the label endpoints | `lib.to_int(settings.application_id)` |
| Consignor address | Free-form | Must match the account-registered sender (origin validation) | Merchant-supplied, not defaulted |

### Field Reference

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `apikey` | str | — | Query-parameter credential |
| `customer_number` | str | — | Consignor `partyId` (`partyIdType` 160) |
| `application_id` | str | — | EDI `application.applicationId`, sent as an integer |
| `issuer_code` | Z11–Z14 | `Z12` | Market agreement; gates the export letter |
| `config.label_type` | PDF/ZPL | `PDF` | Default label file format |
| `config.label_size` | standard/small/ste | unset | `labelType` query parameter |
| `config.language` | str | unset | Booking locale default |
| `config.locale_by_recipient` | bool | false | Derive the locale from the recipient country |
| `config.enable_transit_times` | bool | false | Transit Time enrichment |
| `config.offer_tracked_letter` / `offer_export_letter` | bool | false | Letter-service gating |

---

## Edge Cases & Failure Modes

| Scenario | Handling |
|----------|----------|
| Destination outside every rate-sheet zone | Empty rate list from the universal engine |
| Transit call fails or returns 401/403 | Static transit days, one warning naming `enable_transit_times` |
| Mixed per-item booking outcome | Details from allocated ids plus per-item fault messages |
| ZPL response without `labelFormat` | Requested label type from the request context |
| Multiple printouts | Bundled with `lib.bundle_base64` |
| Track & Trace not authorized or empty | Link-only detail: tracking URL, `in_transit`, no events, plus the fault message |
| Non-string `options.language` or `options.entry_code` | Coerced with `str()` before use |
| Entry code over 50 characters | `ENTRY_CODE_LENGTH` message, no HTTP call |
| More than 13 customs lines | `SHIPPING_SDK_FIELD_ERROR` naming the limit, no HTTP call |
| Registration number under shipment `options` on a customs booking | Field error pointing to `customs.options` |
| By-id customs fetch transport, protocol, or unreadable-body failure | Booking stands; one message reports the failure |
| Booking without allocated item ids | No customs fetch; booking faults surface |
| Manifest, pickup update, pickup cancel | `not_supported` message, no HTTP call |

### Security Considerations

- [x] The apikey is reused from the connection; no new secrets.
- [x] The apikey travels in the query string by carrier design; trace redaction of URL parameters is a shared concern.
- [x] Fixtures use a fake key.
- [x] Customs, entry-code, and locale inputs are validated or coerced before request building.

---

## Implementation Plan

| Commit scope | Files |
|--------------|-------|
| Static rating and letter gating | `karrio/mappers/postnord/{mapper,proxy,settings}.py`, `karrio/providers/postnord/{rate,units,utils}.py`, `karrio/plugins/postnord/__init__.py`, `tests/postnord/test_rate.py` |
| Transit-time enrichment | `proxy.py`, `rate.py`, `units.py` |
| Booking with PDF labels, returns, error parsing | `providers/postnord/shipment/{create,return_shipment}.py`, `error.py`, `schemas/shipment_*.json` |
| ZPL labels and label size | `create.py`, `proxy.py`, `units.py` |
| Cancellation placeholder | `shipment/cancel.py` |
| Track & Trace v7 | `tracking.py`, `units.py` |
| Pickup and manifest | `pickup/*.py`, `manifest.py`, `schemas/pickup_*.json` |
| Service points | `service_points.py`, `units.py` |
| Recipient-country locale | `units.py`, `create.py`, `settings.py` (`recipient_locale`) |
| Entry code and notifications | `units.py`, `create.py`, `proxy.py` |
| Booking customs and standalone document | `create.py`, `proxy.py`, `units.py`, `schemas/labels_ids_request.json` |
| Post-booking declarations | `customs.py`, `proxy.py`, `schemas/customs_declaration_*.json` |

Schemas are regenerated with `./bin/run-generate-on modules/connectors/postnord`.
Vendored API specs are referenced as `vendor/*.swagger.json` and ship separately.

---

## Testing Strategy

Tests use `unittest`, mock `karrio.mappers.postnord.proxy.lib.request`, and assert on outgoing URLs and bodies and on parsed results.

| Suite | Coverage |
|-------|----------|
| `test_rate.py` | Static rates, zone misses, cross-border catalog, transit enrichment, variants, not-found, degrade, letter gating |
| `test_shipment.py` | Booking request, label routing and encoding, locale tiers and `recipient_locale`, entry code, notifications, customs mapping and limits, by-id customs fetch fail-open paths, cancel, partial and auth errors |
| `test_tracking.py` | Delivered and in-transit events, link-only degrade |
| `test_pickup.py`, `test_manifest.py` | Pickup booking and unsupported operations |
| `test_servicepoints.py` | Address and coordinate lookups, parsing, faults |
| `test_customs_declaration.py` | Envelope validation, PDF parameters, wrapped and bare responses, rejections |

```bash
python -m unittest discover -v -f modules/connectors/postnord/tests
```

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Merchants expect cancellation | High | Explicit unsupported message; documented limitation |
| Rate-sheet prices drift from contracts | Medium | Prices are merchant-maintained; documented |
| Undocumented live behaviors change | Medium | Each is isolated in one parser branch and covered by fixtures modeled on live captures |
| Customs data previously ignored now reaches PostNord | Low | Intended; CN22 is emitted only when commodities are present |
| Duplicate CN22 pages between booking printout and standalone document | Low | Accepted; `definePrintout=onlyLabels` is the lever if consumers report double printing |

---

## Migration & Rollback

The change is additive: a new connector package and its registration in `requirements.sdk.dev.txt` and `source.requirements.txt`.
There are no database migrations, and connections are inert until configured.
Rollback removes the package and the two registration lines.

---

## Future Work

### NVIT customs data set

From 1 April 2026, Norwegian goods moving Norway-to-Norway via Sweden or Finland need per-goods-line trade description, six-digit HS code, net and gross weight, and packaging details at booking.
The CN22 mapping carries gross weight only; PostNord's `customsInvoice` branch models line net and gross weight, per-parcel `refItemIds`, and `totalNetWeight`.
Open questions: which branch PostNord expects for NVIT flows, whether to add a unified `Commodity.net_weight` or use a connector convention, whether lines come from `Parcel.items` or `customs.commodities`, where packaging details land, and whether to gate on the affected postcode bands.
Per-parcel linkage requires replacing the constant `itemId="0"` with unique item ids.
Until then, callers can submit caller-built `customsInvoice` declarations per item id through `create_customs_declaration`.

### Per-product credential verification

A connector-local `validate_credentials` proxy method could probe Transit Time, Service Points, and Track & Trace with side-effect-free GETs and report `authorized`, `unauthorized`, or `unknown` per product.
No side-effect-free probe is known to exercise Booking authorization; `GET /v3/edi/labels/manage/health` needs live confirmation that it is apikey-gated.

---

## Appendices

### Appendix A: Environments

| | Host | Portal |
|---|---|---|
| Sandbox (`test_mode=True`) | `https://atapi2.postnord.com` | `atdeveloper.postnord.com` |
| Production | `https://api2.postnord.com` | `developer.postnord.com` |

### Appendix B: Spec provenance

The swagger files are point-in-time downloads from <https://developer.postnord.com/apis/active>, which offers no permanent download URL, vendored under `modules/connectors/postnord/vendor/`: Booking APIs v3.5.29.1 (`booking.swagger.json`), Service Points v5 (`servicepoints-v5.swagger.json`), Transit Time (`transit-time-v1-v2.swagger.json`), and Track & Trace v7 (`track-and-trace-v7-findbyidentifier.swagger.json`).
Code lists (service, additional-service, package, and notification codes) come from PostNord's General Descriptions (`vendor/docs/general-descriptions.pdf`) and the delivery-options spec (`delivery-options.swagger.json`).
