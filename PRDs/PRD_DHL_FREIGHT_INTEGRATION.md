# PRD: DHL Freight Sweden integration

| Field | Value |
|-------|-------|
| Project | DHL Freight Sweden carrier connector (`dhl_freight_sweden`) |
| Version | 1.6 |
| Date | 2026-09-11 |
| Status | Implemented |
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

Add a `dhl_freight_sweden` connector targeting the DHL Freight Sweden API Farm, covering shipment booking (with label) and a tracking link.
The connector composes two API Farm services — the Transport Instruction API (booking) and the Print API (label) — into Karrio's single `shipment/create` contract, and surfaces a URL-only tracking link.
It is used for domestic Swedish freight in our deployment and also supports international products to and from Sweden; DHL's own API validation remains authoritative, so no geographic gate is imposed.

The two DHL front doors are the same underlying DHL Freight API.
The DHL Group Developer Portal (`api.dhl.com`, OAuth2 bearer tokens, a Unified Shipment Tracking API) is one path; the DHL Freight Sweden API Farm (`freight-logistics.dhl.com`, a single `client-key` header, no token exchange) is the other.
Phase 0 targets the API Farm exclusively, as documented by the vendored OpenAPI 2.10.0 specs.

### Key architecture decisions

1. **`shipment/create` chains book then print (approach A).**
One proxy method books via `POST /transportinstruction/sendtransportinstruction`, captures the assigned `transportInstruction.id`, then calls the Print API and returns a merged `{ booking, print }` payload.
This preserves Karrio's expectation that create returns a label in one step.
The print step posts `POST /print/printdocumentsbyid` with `{ shipmentIds: [id] }` (Resolved decision #15); the full-payload `POST /print/printdocuments` operation remains available as fallback knowledge.
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
5. **Rating is static-rate-sheet only (supersedes the earlier "no rating" decision).**
The API Farm Price Quote API remains out of scope, but the one-click shipment flow requires the `rating` capability to resolve a connection (the server's rate-fetch step filters connections and gateways on `capability=rating`).
`Proxy.get_rates` therefore delegates to the universal `RatingMixinProxy` against the service levels seeded in `units.DEFAULT_SERVICES` (rate=0.0 placeholders overridden by merchant prices at runtime); no carrier call is made.
6. **No cancel or returns in Phase 0.**
Shipment cancellation and returns are out of scope; `cancel.py` remains a documented stub and no `cancel_shipment` is wired.
7. **Label layout is selectable; raster format (PDF/ZPL) is not an API parameter.**
The Print API models label page layout via `ReportOptions.pageOptions.pageType` (`Label`, `Label2xPortraitA4`, `Label3xLandscapeA4`, `LabelCompact`, `LabelCompact2x2PortraitA4`); default `Label`.
The Print API 2.10.0 exposes no raster-format field, so PDF-versus-ZPL is governed by DHL account configuration, not by a request parameter.
A per-connection `label_type` setting (default `PDF`) tags the returned label bytes as the last resort; it is account-aligned metadata, not an API request parameter.
Live confirmation 2026-09-10: the account/sandbox emits PDF A4 regardless of the connection's `label_type`, so the label type is derived from the decoded document's magic prefix, then the report `contentType`, then the `label_type` setting.
8. **API host is per-connection overridable.**
The default host is the API Farm — test `https://test-api.freight-logistics.dhl.com`, production `https://api.freight-logistics.dhl.com` — selected by `test_mode`, with a `connection_config.server_url` override.
Each API's base path (`/transportinstructionapi/v1`, `/printapi/v1`, `/productapi/v1`, ...) is appended to the resolved host.
9. **Phase 0 verification is Karrio's mocked four-method unittest pattern.**
No live sandbox credentials are required; all Phase 0 tests are hermetic.
Live sandbox probes (2026-09-08, 2026-09-10) supplied decision evidence only; the shipped test suite remains hermetic.

### Scope

| In scope | Out of scope |
|----------|--------------|
| Shipment booking (`POST /transportinstruction/sendtransportinstruction`) | Rating / price quotes (Price Quote API deferred) |
| Label retrieval (Print API, by-id operation) | Live tracking events (`TrackingRequest` to `TrackingDetails`) |
| `client-key` header authentication | Shipment cancellation / returns |
| Tracking link + tracking id (URL-only, via shipment meta) | Pickup, manifest, service-point / home-delivery locator lookups |
| `productCode` services + `payerCode` / label-layout options | Dangerous goods, temperature-controlled, ADR (later phase) |
| Domestic and international products (no geo gate) | PDF-vs-ZPL request-time selection (account-governed) |

---

## Open Questions & Decisions

### Pending questions

None — all questions are resolved (see Resolved decisions).

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
| 8 | Raster format (PDF/ZPL) | Not a request parameter; account-governed; label type derived from the decoded document magic prefix (`%PDF-`, `^XA`), then report `contentType`, with the `label_type` setting as last-resort tag | Print API 2.10.0 has no raster-format field; live sandbox emits PDF A4 regardless of connection config (`%PDF-1.6`, 2026-09-10) | 2026-09-10 |
| 9 | Geographic gating | None | DHL API validation is authoritative; international implicitly allowed | 2026-08-11 |
| 10 | API host resolution | API Farm default (by `test_mode`) + `connection_config.server_url` override | Per-connection override supported | 2026-08-11 |
| 11 | Phase 0 verification | Mocked four-method unittest pattern; no live creds | Karrio hermetic-suite norm | 2026-08-11 |
| 12 | Booking-required fields | Payer code, consignor id, reference qualifier, customs procedure code mapped from sandbox-verified sources | Live 400 validation dump (product 601 and 102) plus the SE product manual v5.23 and the product API (`/productapi/v1/products/{code}`); both corrected bookings returned HTTP 200 | 2026-09-08 |
| 13 | Customs declaration currency | Single declaration currency resolved from `duty.currency`, then the commodities' common currency; per-line gaps filled, conflicts raise a field error | A declaration with mixed per-line currencies corrupts `customsValueCurrency`/`invoiceCurrency` consistency | 2026-09-08 |
| 14 | Service-point locator reference | Caller supplies the full service-point details via `options` (id + name + street + city + postal code + country code); the connector emits a complete `AccessPoint` party (`subType` `ParcelShop` \| `ParcelStation`); no client-side product/country gating | Live sandbox 2026-09-10: an id-only party is rejected (validationErrors 22001 "Address is mandatory for party AccessPoint" / "Name is mandatory for party AccessPoint", 22006 linehaul failure without postalCode); a full party returns HTTP 200 for 103 SE ParcelShop and 109 DK ParcelShop + ParcelStation (bookings 2906723792 / 2906723800 / 2906723826); the consignee party stays alongside the AccessPoint | 2026-09-10 |
| 15 | Print operation | By-id: `POST /print/printdocumentsbyid` with `{ shipmentIds: [id], options: ReportOptions }` | The booking response carries the shipment id, so the by-id op prints without re-sending the shipment; live-verified 2026-09-10 (`label_2906723792.pdf`, base64 PDF `reports[].content`); the generated schemas now carry the by-id request type (`PrintRequestByIDType`); the full-payload `printdocuments` op remains available as fallback knowledge | 2026-09-10 |
| 16 | Tracking-URL template | Keep the shipped template: `https://www.dhl.com/se-en/home/tracking/tracking-freight.html?submit=1&tracking-id={id}` | DHL Freight Sweden's own tracking FAQ links its track CTAs to `/se-en/home/tracking/tracking-freight.html` (verified in the page's raw HTML); the page runs the same Shipment Tracking Unified API widget and `?submit=1&tracking-id=` convention as all five sibling DHL connectors; the FAQ's "normally 10 digits" freight number matches `transportInstruction.id`; `activetracing.dhl.com` rejected (bare form page, no documented deep-link param, myACT login-gated). Residual: the client-side widget's auto-submit was not directly observed — close by clicking one production id in a browser or confirming with se.ecom@dhl.com | 2026-09-10 |
| 17 | Rate-sheet zone coverage for the international parcel family | Zones sourced from the Product API `toCountries` (test host, fetched 2026-09-10, `GET /productapi/v1/products/{code}`, all from SE): 109 → `Europe` zone with 24 countries (AT BE BG CZ DE DK EE ES FI FR HR HU IE IT LT LU LV NL NO PL PT RO SI SK); 112 → the same list minus FR (23); 232 → 26 countries adding CH/GB/GR and dropping HR; 107 → `Sweden` zone (`["SE"]`) | All four products are `isDomestic: false` per the catalog, so a Nordic-only zone understated the footprint (live-confirmed 2026-09-10: a SE→PL rate query offered only 202/205/233/601/SPI). The zone matches the recipient, so the reverse lane 107 (EU → SE) is gated on SE; the Nordic entries NO/DK/FI are not valid 107 recipients per the catalog. 107 keeps `domicile=True, international=True` because the universal rating mixin computes `is_domicile` as account-or-shipper country == recipient country, so a PL→SE return flow classifies as domicile and 107 surfaces through its domicile flag. The catalog's per-country `postalCodeExcludes` (e.g. DK `38*`, NO `917*`, PT `9*`) cannot be expressed in `ServiceZone` (inclusion lists only) — booking-time DHL validation stays authoritative for postal exclusions. Residual: the unified SDK interface additionally rejects any request whose shipper country differs from `account_country_code="SE"` (`SHIPPING_SDK_ORIGIN_NOT_SERVICED_ERROR`) before the mixin runs, so the return lane reaches rating only through a connection-level rate pipeline | 2026-09-10 |
| 18 | Receiver-phone label print rule | The connector sends the consignee phone unconditionally; no client-side suppression by destination country | The manual's 109/112 forbidden/mandatory receiver-phone country lists (label section 9) are enforced by DHL's label renderer server-side — live-verified 2026-09-10: the SE→DE probe's marker phone `+49 170 7000 777` was echoed verbatim in the booking response (booking 2906724865) yet is absent from the decoded label in every digit-normalized variant, and the DK PUDO reprint (booking 2906723800) printed no consignee phone either — in both cases exactly one `Phn.` line prints, the sender's; no machine-readable form of the rule exists in any vendored spec, the product-109 catalog, or a fresh `GET /products/112`. Label section 16 "Customer information" is auto-composed from the Consignee party for PUDO shipments. No connector change required (evidence: `docs/notes/evidence/dhl-freight-sweden-phone-print-live-probe.md`) | 2026-09-10 |
| 19 | Driver instructions | Map the SDK's universal instruction options — `shipper_instructions` → `pickupInstruction`, `recipient_instructions` → `deliveryInstruction` — with carrier-prefixed aliases; pass-through lengths with DHL validation authoritative | The transport-instruction spec carries both as optional top-level `Shipment` fields (maxLength 140 each) and the generated schema already typed them; the universal options are the fleet convention (FedEx consumer precedent, SDK category `INSTRUCTIONS`) and the initializer remaps them onto the carrier member names, so callers may use either key. Length handling follows the customs `commodityDescription` max-35 precedent (create passes through, DHL 400s on overruns) rather than client-side truncation or a guard | 2026-09-11 |

### Edge cases requiring input

| # | Edge case | Needs |
|---|-----------|-------|
| 1 | Print report `content` encoding | Resolved: `reports[].content` is base64 — live-verified 2026-09-10 by decoding the by-id print response to a valid PDF (`label_2906723792.pdf`, Resolved decision #15) |
| 2 | Freight-payer party id source | Resolved: the consignor party carries `settings.account_number` as its id; the separate FreightPayer party was dropped (its id is a customer number, not the payer code) |
| 3 | Service-point party data integrity: DHL does not registry-validate the id or name at booking (a bogus id with an invented name booked successfully in the sandbox); routing derives from the party postalCode/countryCode | Callers must source ids and details from the Service Point Locator API `findnearestservicepoints`, which returns the full address (`getservicepointdetails` does not); production may validate more strictly (see Resolved decision #14) |

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
A dhl_freight_sweden connector books a transport instruction, returns a printable
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
| Connector discovered as a plugin | `./bin/cli plugins show dhl_freight_sweden` succeeds | P0 |
| Shipment create builds a valid booking + print request | `test_create_shipment_request` passes | P0 |
| Shipment parse returns tracking id + label + tracking_url | `test_parse_shipment_response` passes | P0 |
| Proxy issues booking + print to the correct API Farm URLs | `test_create_shipment` passes | P0 |
| Error responses parsed for booking/print | `test_parse_error_response` passes | P0 |
| Capabilities = shipping + rating (static rate sheet) | no `tracking` / `pickup` reported in Phase 0 | P1 |

### Launch criteria

- [x] P0: all four shipment test methods pass (mocked, hermetic).
- [x] P0: `./bin/run-sdk-tests` green (hermetic suite; no live calls).
- [x] P0: the shipment parse asserts a tracking number, a label, and `meta.tracking_url`.
- [x] P1: capabilities report `shipping` + `rating` (static rate sheet via `RatingMixinProxy`); no `tracking` / `pickup`.

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **A. Book then print, chained in `create_shipment`** | One-step create returns label; honors Karrio's contract | Two sequential API calls; must merge two responses | **Chosen** |
| B. Book only; print deferred to a separate document call | Simpler create | Breaks "order label" in one step; consumers get no label at create time | Rejected |
| C. Print via full-payload `/print/printdocuments` | No id round-trip dependency | Re-sends the shipment; by-id is the leaner path | Rejected (Resolved decision #15); retained as fallback knowledge |

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
                        │      dhl_freight_sweden connector      │
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
          │  /transportinstruction/     │   │  /print/              │
          │   sendtransportinstruction  │──▶│   printdocumentsbyid  │
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
   ├─▶ POST /printapi/v1/print/printdocumentsbyid
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
    → options.dhl_freight_sweden_payer_code   → payerCode.code (default DAP) + payer party.id = account_number
    → options.dhl_freight_sweden_label_page_type → ReportOptions.pageOptions.pageType (default Label)
  → options.shipper_instructions / .recipient_instructions → pickupInstruction / deliveryInstruction
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
| `shipper` | `parties[type=Consignor]` | Yes | name, address, contact, phone, email; `id` = `settings.account_number` (customer/agreement number, mandatory per the payer code) |
| `recipient` | `parties[type=Consignee]` | Yes | as above |
| `service` | `productCode` | Yes | numeric code (e.g. `102`, `232`); see product table |
| `options.dhl_freight_sweden_payer_code` | `payerCode.code` | Yes | terms-of-delivery code: option, then `customs.incoterm`, then default `1` (consignor pays). Domestic products use `1`/`3`/`4`; international use Incoterms (`DAP`, `DDP`, …) or Combiterm (`022`/`023`); the valid set is per product (`/productapi/v1/products/{code}` `payerCodes`) |
| `settings.account_number` | `parties[type=Consignor].id` | Yes | customer/agreement number |
| `parcels[]` | `pieces[]` | Yes | weight→kg, dims→cm (per-product minimums apply, e.g. 102: L≥15/W≥11/H≥2; 601: L≥15/W≥11/H≥3), `numberOfPieces` |
| `options.dhl_freight_sweden_label_page_type` | `pageOptions.pageType` | No | default `Label`; `Label2xPortraitA4` / `Label3xLandscapeA4` / `LabelCompact` / `LabelCompact2x2PortraitA4` |
| `options.shipper_instructions` | `pickupInstruction` | No | alias `dhl_freight_sweden_pickup_instruction`; driver instruction for the pickup side, maxLength 140, DHL-validated (no client-side truncation) |
| `options.recipient_instructions` | `deliveryInstruction` | No | alias `dhl_freight_sweden_delivery_instruction`; driver instruction for the delivery side, maxLength 140, DHL-validated (no client-side truncation) |
| `reference` | `references[]{qualifier,value}` | No | qualifier `CU` (consignor reference, product manual appendix E; 3-char limit) |
| `options.dhl_freight_sweden_service_point` | `parties[type=AccessPoint].id` | With service point | service-point id sourced from `findnearestservicepoints`; not registry-validated by DHL at booking |
| `options.dhl_freight_sweden_service_point_type` | `parties[type=AccessPoint].subType` | No | `ParcelShop` (default) or `ParcelStation`; 109 DE allows `ParcelShop` only per the product catalog |
| `options.dhl_freight_sweden_service_point_name` | `parties[type=AccessPoint].name` | With service point | required with the id; missing details raise a `SHIPPING_SDK_FIELD_ERROR` naming the missing options |
| `options.dhl_freight_sweden_service_point_street` | `parties[type=AccessPoint].address.street` | With service point | as above |
| `options.dhl_freight_sweden_service_point_city` | `parties[type=AccessPoint].address.cityName` | With service point | as above |
| `options.dhl_freight_sweden_service_point_postal_code` | `parties[type=AccessPoint].address.postalCode` | With service point | as above; drives DHL linehaul routing |
| `options.dhl_freight_sweden_service_point_country_code` | `parties[type=AccessPoint].address.countryCode` | With service point | as above; drives DHL linehaul routing |
| `customs.commodities[]` | `customsInformation.customsCommodities[]` | No | description→`commodityDescription` (mandatory, max 35), hs_code→`hsItemId` (wire string, max 38), value_amount/currency→`customsValue`/`customsValueCurrency` (single declaration currency; gaps filled from `duty.currency`, conflicts rejected), weight→`netWeight`, quantity→`numberOfUnits`, origin_country→`countryCodeOfOrigin`; `procedureCode` defaults to `1042` (standard definitive export), overridable via `options.dhl_freight_sweden_customs_procedure_code` |
| `customs` invoice data | `customsInformation.customsDocuments[]` | With customs | one document always emitted: `CommercialInvoice` when invoice/commercial-invoice data exists, else `ProformaInvoice`; invoice→`id`, transportMovement=`Export` when destination differs from the account country, invoice_date→`invoiceDate`, duty.declared_value→`invoiceAmount`, declaration currency→`invoiceCurrency` |
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

Rate-sheet zones follow the Product API destination footprint (Resolved decision #17): the outbound parcels 109/112/232 carry `Europe` zones from their from-SE `toCountries` (109: 24 countries; 112: the same list minus FR; 232: 26 countries including CH/GB/GR but not HR), the return product 107 carries a `Sweden` zone because the zone matches the recipient, and the international freight products keep unrestricted zones.
Per-country `postalCodeExcludes` in the catalog are not expressible in `ServiceZone` (inclusion lists only), so booking-time DHL validation stays authoritative for postal exclusions.

The service-point fixture products (103, 109) require an `AccessPoint` party with a `subType` of `ParcelShop` or `ParcelStation` (the subType enum — not `Servicepoint`) carrying a caller-supplied service-point id, name, and full address; DHL rejects an id-only party (validationErrors 22001/22006, live sandbox 2026-09-10, see Resolved decision #14).
Per the product catalog (`GET /productapi/v1/products/{code}`), 109 DE allows `ParcelShop` only while DK allows both subTypes; the connector imposes no product/country gating of its own.
The home-delivery fixture product (401) uses the `doorstepDelivery` access-code path, not an AccessPoint party.
Service-point ids and details are sourced from the Service Point Locator API `findnearestservicepoints`, which returns the full address; `getservicepointdetails` does not.

### API changes

| Endpoint (base path + operation) | Method | Auth | Purpose |
|----------------------------------|--------|------|---------|
| `/transportinstructionapi/v1/transportinstruction/sendtransportinstruction` | POST | `client-key` header | Create booking → tracking id |
| `/printapi/v1/print/printdocumentsbyid` | POST | `client-key` header | Retrieve label bytes by id |

Base host resolution (in `utils.py`): `self.connection_config.server_url.state` if set, else the API Farm default — test `https://test-api.freight-logistics.dhl.com`, production `https://api.freight-logistics.dhl.com` — selected by `test_mode`.
Each service's base path (`/transportinstructionapi/v1`, `/printapi/v1`, ...) is appended to the resolved host.

---

## Edge Cases & Failure Modes

### Edge cases

| Case | Handling |
|------|----------|
| Booking succeeds, print fails | Surface print error as `Messages`; booking id still recoverable via `meta`; return `ShipmentDetails` with empty label + `meta.tracking_url`, or fail per parser policy |
| Print report `content` not base64 | Closed: base64 confirmed by decoding the live by-id print response to a valid PDF (2026-09-10, Resolved decision #15) |
| Missing `account_number` when payer party requires id | Validate early; return a clear `Message` rather than a DHL 400 |
| International shipment | Allowed; no geo gate — DHL API validates |
| Service-point product with incomplete party details | Raise a `SHIPPING_SDK_FIELD_ERROR` naming the missing options before any carrier call; DHL rejects id-only AccessPoint parties (validationErrors 22001/22006, Resolved decision #14) |
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
Tracking (`tracking.py`) and cancel (`cancel.py`) remain documented deferred stubs; rating is served statically from the seeded rate sheet (no carrier call).

### Phase 1: Scaffold & schema generation

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Scaffold connector | `./bin/cli sdk add-extension` | Done | S |
| Vendor raw specs (upstream filenames, git-tracked) | `modules/connectors/dhl_freight_sweden/vendor/se-api-farm/*.json` | Done | S |
| Derive JSON generation samples from the vendored specs | `modules/connectors/dhl_freight_sweden/schemas/*.json` | Done | M |
| Configure + run generation | `generate`, `./bin/run-generate-on modules/connectors/dhl_freight_sweden` | Done | S |

### Phase 2: Settings, units, errors, proxy

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Settings + resolvable server URL (config override, default-by-test_mode) + tracking_url + label_type | `karrio/providers/dhl_freight_sweden/utils.py`, `karrio/mappers/dhl_freight_sweden/settings.py` | Done | M |
| `ConnectionConfig.server_url` override + `label_type` | `karrio/providers/dhl_freight_sweden/units.py`, `karrio/plugins/dhl_freight_sweden/__init__.py` | Done | S |
| Services (full product set) / options enums | `karrio/providers/dhl_freight_sweden/units.py` | Done | M |
| Error parser (booking/print) | `karrio/providers/dhl_freight_sweden/error.py` | Done | S |
| Proxy: `create_shipment` (book→print) with `client-key` header | `karrio/mappers/dhl_freight_sweden/proxy.py` | Done | M |

### Phase 3: Providers

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Shipment create request build + response parse (with `meta.tracking_url`) | `karrio/providers/dhl_freight_sweden/shipment/create.py` | Done | L |
| Public exports + plugin METADATA (shipping + rating) | `karrio/providers/dhl_freight_sweden/__init__.py`, `karrio/plugins/dhl_freight_sweden/__init__.py` | Done | S |
| Deferred stubs documented (`tracking.py`, `cancel.py`) | `karrio/providers/dhl_freight_sweden/{tracking.py,shipment/cancel.py}` | Done | S |

### Phase 4: Tests

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Fixtures + shipment tests (book+print mocks) for the six fixture products | `tests/dhl_freight_sweden/fixture.py`, `test_shipment.py` | Done | M |
| Run suites, confirm plugin registration + capabilities | — | Done | S |

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
python -m unittest discover -v -f modules/connectors/dhl_freight_sweden/tests
./bin/run-sdk-tests
./bin/cli plugins show dhl_freight_sweden
```

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Print report `content` not base64 | Corrupt label | Low (retired) | Closed: base64 confirmed against the live by-id print response (`label_2906723792.pdf`, 2026-09-10) |
| Service-point party data integrity: DHL does not registry-validate the id or name at booking | A bogus or stale service point books successfully and misroutes (sandbox 2026-09-10) | Medium | Callers source ids/details from `findnearestservicepoints` (returns the full address; `getservicepointdetails` does not); the connector requires the complete party details (Resolved decision #14); production may validate more strictly |
| Booking succeeds but print fails | Orphaned booking without label | Low | Surface error + keep booking id in `meta`; document recovery |
| Wrong tracking-URL template | Broken tracking link | Low | Resolved (decision #16): template confirmed against DHL's own FAQ and the fleet-wide param convention; single source in `utils.py`; residual JS auto-submit check documented in the decision |
| Print operation choice (`byid` vs full payload) | Rework in create flow | Low | Resolved 2026-09-10 (Resolved decision #15): the connector ships the by-id op, live-verified via `label_2906723792.pdf`; the full-payload op remains fallback knowledge |
| Raster format (PDF/ZPL) assumption | Mismatched label type tag | Low (retired) | Closed: live confirmation 2026-09-10 — the account/sandbox emits PDF A4 regardless of connection config; label type now derived from the decoded document magic prefix with the `label_type` tag as last resort |

---

## Appendices

### Appendix A: Reference specs

Vendored to `modules/connectors/dhl_freight_sweden/vendor/se-api-farm/` (upstream filenames, git-tracked; matches `gls` / `hermes` / `dpd_meta`).
The DHL Freight Sweden API Farm OpenAPI 2.10.0 set includes, among others:

- `transport-instruction-2.10.0.json` — booking (`/transportinstruction/sendtransportinstruction`)
- `print-api-2.10.0.json` — label (`/print/printdocuments`, `/print/printdocumentsbyid`)
- `product-api-2.10.0.json` — products (`/products`), for the `productCode` set
- `pricequote-api-2.10.0.json` — price quotes (deferred beyond Phase 0)
- `servicepoint-api-2.10.0.json`, `home-delivery-locator-api-2.10.0.json` — locators for service-point / home-delivery products (deferred)

### Appendix B: Carrier-specific reference

- Authentication: a single `client-key` HTTP header on every request (`apiKey`, `in: header`); no token exchange.
- Booking `productCode` set: enumerated in the product table above; the runtime source of truth is the Product API `GET /products`.
- Tracking URL template: `https://www.dhl.com/se-en/home/tracking/tracking-freight.html?submit=1&tracking-id={id}` (Resolved decision #16), applied locally to `transportInstruction.id`; swapping `se-en` for `se-sv` yields Swedish-facing links if wanted.

Hosts (resolved host + spec base path):

| Environment | API Farm host | Base paths |
|-------------|---------------|------------|
| Test | `https://test-api.freight-logistics.dhl.com` | `/transportinstructionapi/v1`, `/printapi/v1`, ... |
| Production | `https://api.freight-logistics.dhl.com` | as above |

Per-connection `connection_config.server_url` overrides the host.

| Karrio field | DHL Freight field |
|--------------|-------------------|
| `tracking_number` | booking `transportInstruction.id` |
| `docs.label` | `PrintResult.reports[].content` via `POST /print/printdocumentsbyid` (label report) |
| `meta.tracking_url` | `tracking_url.format(transportInstruction.id)` |
| `service` | `productCode` |
| `options.dhl_freight_sweden_payer_code` | `payerCode.code` |
| `options.dhl_freight_sweden_label_page_type` | `ReportOptions.pageOptions.pageType` |
