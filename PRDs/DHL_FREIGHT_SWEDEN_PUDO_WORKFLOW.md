# PRD: DHL Freight Sweden PUDO workflow lookups

| Field | Value |
|-------|-------|
| Project | dhl_freight_sweden connector-local lookup capabilities |
| Version | 1.1 |
| Date | 2026-09-10 |
| Status | Implemented |
| Owner | Joaqim Planstedt |
| Type | Integration |
| Reference | [PRD_DHL_FREIGHT_INTEGRATION](PRD_DHL_FREIGHT_INTEGRATION.md) (booking, print, PUDO options, decisions #14/#17) |

## Executive Summary

Add two connector-local lookup capabilities to `dhl_freight_sweden`: product eligibility (`POST /productapi/v1/productmatches`) and service-point discovery (`POST /servicepointlocatorapi/v1/servicepoint/findnearestservicepoints`).
Together with the shipped booking and by-id print they complete the PUDO workflow: match products for an address pair, pick a nearby service point, then book with a complete `AccessPoint` party via the five PUDO options.
Both surface as duck-typed proxy methods following the postnord `find_service_points` precedent (postnord PRD decision SP1); no SDK capability, server route, serializer, or dashboard change is involved.

### Key architecture decisions

1. **Connector-local surface** (user decision 2026-09-10).
Callers invoke `gateway.proxy.find_product_matches(...)` and `gateway.proxy.find_service_points(...)` directly from external tooling; nothing registers in connection capabilities (`map_capability` returns `None` for both names), and no REST or GraphQL surface is added.
2. **`productmatches` is a standalone lookup only** (user decision 2026-09-10).
Rating stays static (integration PRD decision #17 zones); booking performs no pre-validation call.
3. **Raw-dict providers, no generated schemas** (postnord `service_points.py` precedent).
The vendored specs type every enum as `integer` with string values (NSwag quirk), so codegen would infer ints; hand-written request builders and dict parsers avoid the hazard and keep `mapper.py` untouched.
4. **Client-side party guard** for productmatches.
The Consignor+Consignee requirement exists only in the spec's 200-description prose, so the connector enforces it and raises a field error naming the requirement before any carrier call.
5. **Both identifiers exposed** on normalized service points (`id` and `servicePointId`).
The sandbox accepts either at booking without registry validation (2026-09-10 evidence); which one DHL consumes downstream is a documented residual.
6. **subType derivation rule** from the transport-instruction spec text: locationType `locker` → `ParcelStation`, all others → `ParcelShop`; shipped as a mapping helper next to a `LocationType` enum.
7. **`findnearestservicepoints` only**; `getservicepointdetails` is out of scope (it returns no address and no opening hours — nothing it adds improves AccessPoint sourcing).
8. **Connector-local methods bypass the SDK origin gate** (`SHIPPING_SDK_ORIGIN_NOT_SERVICED_ERROR` blocks unified-fetch flows whose shipper country differs from the account country), so EU-origin return-lane lookups work here even though `Rating.fetch`/`Shipment.create` reject them.

### Scope

| In scope | Out of scope |
|----------|--------------|
| `find_product_matches` proxy method + provider | REST/GraphQL routes, serializers, dashboard UI |
| `find_service_points` proxy method + provider | Live rating filter (productmatches inside `get_rates`) |
| `LocationType` enum + subType mapping helper | Booking pre-validation via productmatches |
| Normalized dict outputs sufficient to fill the five PUDO options | `getservicepointdetails`, HomeDeliveryLocator |
| Hermetic five-test patterns per capability + live fixture capture | Generated schemas for either API |
| README calling-convention documentation | Capability or plugin METADATA changes |

---

## Open Questions & Decisions

### Pending questions

| # | Question | Context | Status |
|---|----------|---------|--------|
| 1 | Which service-point identifier the booking consumes (`id` vs `servicePointId`) | The sandbox accepted a bogus id with an invented name (2026-09-10), and routing derives from the party postalCode/countryCode, so the choice may be unobservable at booking time. PL capture 2026-09-10 sharpens it: `id` is a constant point-type code there (`101` = parcelshop, `501` = parcelstation) while `servicePointId` is the unique identifier (`8005-PL-4516440`) | Expose both; callers should prefer `service_point_id`; residual — if a production misroute ever implicates the id, probe deliberately |
| 2 | Opening hours for recipient-facing display | ServicePointLocator 2.10.0 exposes no opening-hours field on either endpoint | DHL API gap; surfaced to DHL if the UI ever needs it |

### Resolved decisions

Covered by key architecture decisions 1-8 above; all dated 2026-09-10 and sourced from the two research notes (vendored-spec analysis and fork-surface analysis) plus the user's surface/role selections.

---

## Problem Statement

### Current state

```
The connector books and prints, and create.py emits a complete AccessPoint
party from five PUDO options — but callers must source service-point ids,
names, and addresses out-of-band (integration PRD edge case 3), and product
eligibility knowledge is frozen into the static zone seed (decision #17).
There is no lookup capability: the fork has no unified service-points
interface, and postnord's find_service_points is deliberately local.
```

### Desired state

```
Two hermetically-tested, connector-local proxy methods return normalized
dicts: productmatches yields DHL's matching products (code, footprint,
rules) for an address pair; findnearestservicepoints yields nearby points
with full addresses. External tooling chains them into shipment/create,
auto-filling the five PUDO options and deriving subType via the spec's
locker→ParcelStation rule.
```

---

## Goals & Success Criteria

### Goals

1. Resolve eligible products from a consignor/consignee address pair plus optional piece criteria.
2. Discover nearby service points carrying the full address the AccessPoint party requires.
3. Return normalized dicts whose fields map one-to-one onto the five PUDO options.
4. Change nothing in capabilities, server, or dashboard.

### Success criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Product-match request build (incl. party guard) | `test_create_product_matches_request` + guard test pass | P0 |
| Product-match proxy call (URL/method/body/headers) | `test_find_product_matches` passes | P0 |
| Product-match response parse (normalized products) | `test_parse_product_matches_response` passes | P0 |
| Product-match error parse (defensive `BadRequestError` + in-band) | `test_parse_product_matches_error` passes | P0 |
| Service-point request build | `test_create_service_points_request` passes | P0 |
| Service-point proxy call (URL/method/body/headers) | `test_find_service_points` passes | P0 |
| Service-point response parse (normalized points, both ids) | `test_parse_service_points_response` passes | P0 |
| Service-point error parse (in-band `errorMessage`) | `test_parse_service_points_error` passes | P0 |
| Capabilities unchanged | assertion that the capability set remains exactly shipping + rating | P1 |
| Live fixture fidelity | fixtures captured from one bounded sandbox call per endpoint | P1 |

### Launch criteria

- [x] P0: all new test methods pass hermetically (nine lookup tests plus the capabilities-stability assertion).
- [x] P0: `./bin/run-sdk-tests` green.
- [x] P1: capabilities assert unchanged; README documents both calling conventions.
- [x] P1: live capture transcript recorded (`docs/notes/evidence/dhl-freight-sweden-pudo-lookups-live-capture.md`; suite stays hermetic).

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **A. Connector-local duck-typed proxy methods** | Postnord SP1 precedent; zero server work; origin-gate bypass | Not callable over HTTP; invisible to dashboard | **Chosen** |
| B. REST routes (proxy module) | HTTP-consumable workflow | New serializer/permission surface with no existing hook; rework if dashboard lands later | Rejected — revisit as a phase-later option on top of A |
| C. Productmatches as live rating filter | Always-authoritative UI service list | Live carrier call per rate fetch; supersedes the just-shipped static zones | Rejected (user decision); revisit if zones drift from the catalog |
| D. Productmatches as booking pre-validation | Fail-fast eligibility | Adds latency and a failure mode to a working booking path | Rejected |

---

## Technical Design

> Existing patterns were studied before proposing new code; reuse is favored over novel constructs.

### Existing code analysis

| Component | Location | Reuse strategy |
|-----------|----------|----------------|
| Connector-local lookup provider | `modules/connectors/postnord/karrio/providers/postnord/service_points.py` | Same shape: `*_request(payload, settings)` → `lib.Serializable`, `parse_*_response` → `(List[dict], List[Message])`, `_normalize_*` dicts, error reuse |
| Duck-typed proxy method | `modules/connectors/postnord/karrio/mappers/postnord/proxy.py:193` | Same pattern; ours POSTs JSON with `client-key` headers instead of GET+query |
| Client-key header set | `modules/connectors/dhl_freight_sweden/karrio/mappers/dhl_freight_sweden/proxy.py` | Reuse the existing header builder for both new calls |
| Host/base-path properties | `karrio/providers/dhl_freight_sweden/utils.py` | Add `product_api_url`, `service_point_locator_url` beside `transport_instruction_url`/`print_url` |
| Error parsing | `karrio/providers/dhl_freight_sweden/error.py` | Reuse for `BadRequestError {error, errors[]}` and in-band `errorMessage` shapes |
| AccessPoint party emission | `karrio/providers/dhl_freight_sweden/shipment/create.py` `_service_point_party` | The consumer of lookup outputs; defines the dict shape the normalizers must satisfy |
| subType enum | `karrio/providers/dhl_freight_sweden/units.py` `PartySubType` | Mapping target; add `LocationType` enum + `SUB_TYPE_BY_LOCATION_TYPE` beside it |

### Workflow diagram

```
  external tooling (workflow driver)
        │
        │ 1. address pair (+ optional piece criteria)
        ▼
  ┌─────────────────────────────┐   POST /productapi/v1/productmatches
  │ gateway.proxy               │ ────────────────────────────────────►
  │   .find_product_matches()   │        client-key header
  └──────────────┬──────────────┘ ◄── [{ product: Product }, ...]
                 │ 2. product.code; party subType if PUDO
                 ▼
  ┌─────────────────────────────┐   POST /servicepointlocatorapi/v1/servicepoint/
  │ gateway.proxy               │ ──────── findnearestservicepoints ────►
  │   .find_service_points()    │        client-key header
  └──────────────┬──────────────┘ ◄── { servicePoints: [...], status }
                 │ 3. chosen point: id, name, address, locationType
                 │    (locker → ParcelStation, else → ParcelShop)
                 ▼
  ┌─────────────────────────────┐   POST /transportinstruction/... (existing)
  │ unified shipment/create     │ ────────────────────────────────────►
  │  five PUDO options +        │ ◄── id + label (by-id print, existing)
  │  AccessPoint party          │
  └─────────────────────────────┘
```

### Data flow: normalized shapes

`find_product_matches` input payload (dict):

| Key | Type | Notes |
|-----|------|-------|
| `shipper` / `recipient` | `{postal_code, country_code}` | minimum; maps to Consignor/Consignee `AddressMatchCriteria` (the only formally required spec fields) |
| `parcels[]` | `{weight, width, height, length, volume?, package_type?}` | optional piece criteria |
| `import_export` | `"E"` \| `"I"` | optional |

Guard: both `shipper` and `recipient` (with postal+country) must be present; otherwise a `SHIPPING_SDK_FIELD_ERROR`-style field error naming the Consignor+Consignee requirement fires before any carrier call.

Normalized product output (dict per match):

| Key | Source field | Notes |
|-----|--------------|-------|
| `code`, `name`, `short_name` | `product.code/name/shortName` | `code` feeds `Shipment.productCode` |
| `is_domestic`, `active`, `is_default`, `hidden` | same-named booleans | |
| `from_countries`, `to_countries` | `fromCountries/toCountries[].country.countryCode` | footprint check without another call |
| `to_country_postal_excludes` | `toCountries[].{countryCode, postalCodeExcludes}` | preserved for caller-side postal filtering (not expressible in zones) |
| `payer_codes` | `payerCodes[].code` | |
| `transportation_mode`, `sub_categories` | code/name pairs | |
| `rules_for_country_delivery_types` | `rulesForCountryAndDeliveryTypes[]` | country + deliveryType code + min/max summaries |

`find_service_points` input payload (dict):

| Key | Type | Notes |
|-----|------|-------|
| `address` | `{street, city, postal_code, country_code}` | full street address supported (unlike productmatches) |
| `location_types[]` | enum values | filter: `servicepoint`, `locker`, `postoffice`, `postbank` |
| `max_items` | int | `maxNumberOfItems` |
| `distance` | `{value, unit}` | unit `m` \| `km` |
| `piece` | `{width, height, length, weight}` | capacity filter |

Normalized service point output (dict per point):

| Key | Source field | Notes |
|-----|--------------|-------|
| `id`, `service_point_id` | `id`, `servicePointId` | both exposed (pending question #1) |
| `name`, `shop_name` | `name`, `shopName` | |
| `type` | `locationType` | feeds the subType rule |
| `address` | `{street, city, postal_code, country_code}` | maps one-to-one onto the PUDO options |
| `coordinates` | `{latitude, longitude}` | |
| `distance`, `distance_unit` | `distance`, `distanceUnit` | |
| `service_types` | `serviceTypes[]` | |

### API changes

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/productapi/v1/productmatches` | POST | `client-key` header | Eligible products for an address pair |
| `/servicepointlocatorapi/v1/servicepoint/findnearestservicepoints` | POST | `client-key` header | Nearby service points with full addresses |

Both hosts resolve through the existing `server_url`/test-mode logic; base paths are appended per API.

---

## Edge Cases & Failure Modes

| Case | Handling |
|------|----------|
| Productmatches called without both parties | Field error naming the Consignor+Consignee requirement (spec prose-only rule) |
| No 4xx declared on either endpoint | Defensive `BadRequestError {error, errors[]}` parse on any non-200, reusing `error.py` |
| Locator in-band errors | `status`/`errorMessage` on the 200 body parsed into `Message`s |
| Empty `servicePoints[]` with ok status | Return empty list, no error |
| `postalCodeExcludes` per destination country | Passed through to callers (not enforceable in zones or the locator request) |
| Dual `loadingMeters`/`loadingMetres` spellings | Send one variant; tolerate either on read |
| Opening hours requested by consumers | Absent from the API 2.10.0 — documented DHL gap, not mapped |
| Enum int-typing in vendored specs | No codegen for these APIs; enums hand-written in `units.py` |

---

## Implementation Plan

| Phase | Task | Files | Status | Effort |
|-------|------|-------|--------|--------|
| 1 | URL properties | `karrio/providers/dhl_freight_sweden/utils.py` | Done | S |
| 1 | Product-match provider + guard | `karrio/providers/dhl_freight_sweden/product_matches.py`, `__init__.py` re-export | Done | M |
| 1 | Proxy method | `karrio/mappers/dhl_freight_sweden/proxy.py` (`find_product_matches`) | Done | S |
| 1 | Tests + captured fixture | `tests/dhl_freight_sweden/test_product_matches.py` | Done | M |
| 2 | Service-point provider + normalizer | `karrio/providers/dhl_freight_sweden/service_points.py`, `__init__.py` re-export | Done | M |
| 2 | `LocationType` enum + subType mapping | `karrio/providers/dhl_freight_sweden/units.py` | Done | S |
| 2 | Proxy method | `karrio/mappers/dhl_freight_sweden/proxy.py` (`find_service_points`) | Done | S |
| 2 | Tests + captured fixture | `tests/dhl_freight_sweden/test_service_points.py` | Done | M |
| 3 | README calling conventions; PRD closeout | `modules/connectors/dhl_freight_sweden/README.md`, this file | Done | S |

Fixture capture: one bounded live sandbox call per endpoint (productmatches SE→PL; findnearest for a PL address), recorded as evidence; the shipped tests consume the captured JSON hermetically.
No bookings are created by this work.

---

## Testing Strategy

> unittest only (never pytest); mocked `lib.request`; five-test pattern per capability (request build, proxy call, response parse, error parse, plus the productmatches party-guard test); run from the repo root.

```
test_product_matches.py
  test_create_product_matches_request      # payload → MatchCriteria body
  test_create_product_matches_missing_parties   # guard raises field error
  test_find_product_matches                # POST URL + client-key + body
  test_parse_product_matches_response      # → normalized products
  test_parse_product_matches_error         # defensive BadRequestError → Messages

test_service_points.py
  test_create_service_points_request       # payload → NearestServicePointRequest body
  test_find_service_points                 # POST URL + client-key + body
  test_parse_service_points_response       # → normalized points (both ids)
  test_parse_service_points_error          # in-band errorMessage → Messages
```

Plus one capabilities-stability assertion (shipping + rating only) so the duck-typed methods provably register nothing.

```bash
source bin/activate-env
python -m unittest discover -v -f modules/connectors/dhl_freight_sweden/tests
./bin/run-sdk-tests
```

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Wrong id field consumed downstream (`id` vs `servicePointId`) | Late misroute invisible at booking | Low | Both exposed; residual documented (pending #1); routing derives from party address regardless |
| Spec prose-only party rule missed by callers | DHL 400 on productmatches | Low | Connector-side guard with explicit field error |
| Catalog drift between static zones and reality | UI offers stale services | Medium | productmatches gives callers the authoritative answer now; revisit alternative C if drift is observed |
| NSwag enum quirks misread | Wrong wire values | Low | No codegen; hand-written builders with captured fixtures as oracles |
| Opening-hours expectation | Consumer disappointment | Medium | Documented as an API 2.10.0 gap up front |

---

## Migration & Rollback

Additive only: new provider files, two proxy methods, URL properties, enums, tests, README section.
No model, migration, serializer, capability, or generated-file change; `mapper.py` untouched.
Rollback is branch deletion; no data or API surface is affected.
