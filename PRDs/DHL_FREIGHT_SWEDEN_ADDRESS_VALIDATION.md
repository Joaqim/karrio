# PRD: DHL Freight Sweden address validation via PostalCodes API

| Field | Value |
|-------|-------|
| Project | dhl_freight_sweden connector address-validation capability |
| Version | 1.0 |
| Date | 2026-09-17 |
| Status | Planning |
| Owner | Joaqim Planstedt |
| Type | Integration |
| Reference | [AGENTS.md](../AGENTS.md) |

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

Add Swedish postal-code address verification to the `dhl_freight_sweden` connector using DHL Freight's PostalCodes API, so shipments booked with product 118 (Hemleverans Paket B2C) can be verified as servable before booking.
The capability is exposed twice over one shared provider module: as the official karrio `validate_address` protocol method (callable standalone through `karrio.gateway` with no Django backend, following the dhl_express/mydhl precedent) and as a connection-config-gated pre-flight inside `create_shipment` with `off`/`warn`/`enforce` modes.

### Key Architecture Decisions

1. **Product 118 is the validation target**: DHL's product manual (§10.14.8) ties the route response's `homeDeliveryParcel` flag explicitly to product 118; the connector enum `dhl_freight_sweden_hemleverans_paket_b2c` maps to carrier code `118`.
2. **Official `validate_address` protocol implementation**: gets the fluent SDK wrapper, standalone gateway access, and the server `Address.validate` route (406 gate opens automatically) with zero server or dashboard code.
3. **Connection config gates booking behavior, not capability presence**: `address_validation: off | warn | enforce` (default `off`) controls the `create_shipment` pre-flight only; the unified lookup is always available (postnord `locale_by_recipient` behavior-gating precedent).
4. **Fail-open on infrastructure errors**: under `enforce`, a definitive negative (`homeDeliveryParcel = false` or a DHL 4xx `ErrorResult`) blocks the booking; an unreachable or erroring API warns and proceeds, so a PostalCodes API outage cannot take down bookings.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| Unified `validate_address` proxy/mapper/provider trio | Rating-time postal-code gating (universal rating stays carrier-call-free) |
| `off`/`warn`/`enforce` connection config with booking pre-flight | Local postal-register sync via `GET /postalcodes/{cc}/updated` |
| `ErrorResult` error-shape remap in `error.py` | `/postalcodes/validate`, `/info/{productCode}`, `/gateway` endpoints |
| `postal_code_api_url` settings property | SDK core model changes (`AddressValidationDetails` untouched) |
| External-tooling guide section (gateway snippet) | Server routes, dashboard code, migrations |

---

## Open Questions & Decisions

### Pending Questions

None. All design questions were resolved during the 2026-09-17 design session.

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | Validation target product | 118 (`hemleverans_paket_b2c`) | Manual §10.14.8: `homeDeliveryParcel = true` ⟺ product 118 available; the only product with a documented per-product flag. User's "home_delivery_b2c (118)" merged two products; 118 selected | 2026-09-17 |
| D2 | Booking failure mode | Configurable `off` / `warn` / `enforce`, default `off` | Roll out warn-first, flip to enforce when trusted; user-selected | 2026-09-17 |
| D3 | Exposure shape | Official `validate_address` protocol + config-gated pre-flight (Approach A) | Follows address-verification precedent (dhl_express, purolator, mydhl); satisfies standalone-gateway requirement; server route arrives for free | 2026-09-17 |
| D4 | Enforce + API outage | Fail open (warn and proceed) | Distinguish definitive negative (block) from infrastructure failure (proceed); a PostalCodes outage must not block bookable shipments | 2026-09-17 |
| D5 | Unified-call semantics | Unscoped → `success = bookable`; `options.service` scoped → `success = homeDeliveryParcel`; `complete_address` populated from route city | Generic call stays generic; service scoping rides the existing `options` dict on `AddressValidationRequest` | 2026-09-17 |
| D6 | Pre-flight trigger scope | Only when mode ≠ `off` AND service resolves to product 118 AND consignee country is SE | 118 is the only product with a documented flag; route endpoint is SE-oriented | 2026-09-17 |

### Edge Cases Requiring Input

None remaining; all edge cases are specified in [Edge Cases & Failure Modes](#edge-cases--failure-modes).

---

## Problem Statement

### Current State

The connector books transport instructions without any postal-code servability check.
DHL's transport API deliberately does not fully validate postal codes ("because of high performance requirements", API Farm manual), so an unservable destination for product 118 surfaces only as a rejected or mis-routed booking after the fact.
The PostalCodes API spec is already vendored (`vendor/se-api-farm/postalcode-api-2.10.0.json`) but no connector code references it.

```python
# proxy.py — booking posts directly, no destination servability check
response = lib.request(
    url=f"{self.settings.transport_instruction_url}/transportinstruction/sendtransportinstruction",
    ...
)
```

### Desired State

Two callers get the same answer from one shared evaluation:

```python
# External tooling, no backend — fluent entry
result = karrio.Address.validate(
    {"address": {..., "postal_code": "11120", "country_code": "SE"},
     "options": {"service": "dhl_freight_sweden_hemleverans_paket_b2c"}}
).from_(gateway).parse()
# result[0].success == True  (homeDeliveryParcel)

# Booking flow — config-gated pre-flight inside proxy.create_shipment
# enforce + homeDeliveryParcel=False → PostalCodeNotServableError raised,
# transport instruction never sent
```

### Problems

1. **No servability signal at booking time**: product-118 shipments to postal codes without home-delivery coverage are discovered only via DHL rejection or downstream failure.
2. **No address-validation capability**: the connector exposes shipping and rating only; external tooling has no postal-code verification surface consistent with the karrio address-verification precedent.
3. **Third error shape unhandled**: the PostalCodes API returns `ErrorResult {status, errorCode, userMessage}`, which `error.py` currently ignores.

---

## Goals & Success Criteria

### Goals

1. Implement the official `validate_address` trio for `dhl_freight_sweden`, callable via `karrio.gateway` without any server components.
2. Gate booking-time verification behind a `address_validation` connection config (`off`/`warn`/`enforce`, default `off`) that auto-renders in the dashboard connection dialog.
3. Block (enforce) or annotate (warn) product-118 bookings to non-servable Swedish postal codes, with fail-open behavior on API outages.
4. Cover both surfaces with the connector's established unittest patterns, using sandbox-captured fixtures.

### Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Connector test suite | All existing + new tests pass (`python -m unittest discover -v -f modules/connectors/dhl_freight_sweden/tests`) | Must-have |
| Pre-flight matrix coverage | Every row of the semantics table has a test | Must-have |
| Standalone invocation | Guide snippet runs against sandbox with the verified test key | Must-have |
| Capability registration | `validate_address` listed in proxy methods; server `Address.validate` 406 gate passes | Must-have |
| Zero behavior change at default config | `off` makes no route-endpoint HTTP calls (asserted) | Must-have |
| Server/dashboard code changes | None | Must-have |

### Launch Criteria

**Must-have (P0):**

- [ ] `test_address.py` passing (request/HTTP/parse/error)
- [ ] Pre-flight matrix tests passing in `test_shipment.py`
- [ ] `test_services.py` drift guard extended and settled (capabilities assertion reflects actual `get_carrier_capabilities()` output)
- [ ] Existing connector tests unchanged and green (default `off` path)
- [x] References payload regression test passing (`address_validation` classified as string enum; `test_references.py`)

**Nice-to-have (P1):**

- [ ] Live sandbox capture of route fixtures (cheapest probe: one route GET)
- [ ] Guide section with the gateway snippet

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| A. Unified `validate_address` + config-gated booking pre-flight | Follows dhl_express/mydhl precedent; fluent wrapper + free server route; shared evaluation helper; satisfies all stated requirements | Touches proxy `create_shipment`; mapper wiring must respect the generation mechanism | **Selected** |
| B. Duck-typed `find_postal_code_route` only | Mirrors `find_product_matches` precedent; full route dict incl. `lineHaul`/`terminalId` | Ignores the address-verification precedent the user named; callers hand-parse raw dicts; booking enforcement needs separate wiring anyway | Rejected |
| C. Unified `validate_address` only, no enforcement | Simplest; smallest diff | Connection config has nothing to gate; drops the booking-flow half of the requirement | Rejected |

### Trade-off Analysis

Approach A costs one shared provider module plus two proxy touch points, and buys protocol conformance (interface wrapper, `Gateway.check` support, automatic server-route exposure) that B forfeits and enforcement that C defers to callers.
The linehaul/terminal routing internals that B would expose are label-rendering data DHL fills itself; no current consumer needs them, and `AddressValidationDetails` has no meta field to carry them without SDK changes the dashboard-alignment decision rules out.

---

## Technical Design

### Existing Code Analysis

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| Official validate_address protocol (proxy slot, mapper pair) | `modules/sdk/karrio/api/proxy.py:160-174`, `modules/sdk/karrio/api/mapper.py:18-35,281-297` | Implement the overridable defaults; no SDK changes |
| Protocol trio precedent | `modules/connectors/dhl_express/.../{proxy.py:18,mapper.py:14,50}`, `.../dhl_express/address.py`; mydhl `proxy.py:134-149` (JSON GET analog) | Copy the structure: mapper delegates, provider builds/parses, proxy GETs |
| Unified models | `modules/sdk/karrio/core/models.py:237-242` (`AddressValidationRequest` with `options`), `:337-344` (`AddressValidationDetails`) | Use as-is; `options.service` carries product scoping |
| Connection config enums | `dhl_express units.py:288-293` (`label_type` enum option), postnord `units.py:68` (bool gate) | New `ServabilityMode` enum option in this connector's `ConnectionConfig` |
| URL properties | `providers/.../utils.py:28-42` (four sibling URL properties off `server_url`) | Add `postal_code_api_url = {server_url}/postalcodeapi/v1` |
| Duck-typed lookup + inline HTTP pattern | `mappers/.../proxy.py:79-125` (`lib.request`, `client-key` header, `on_error=lib.error_decoder`) | Same call shape for route GET and pre-flight |
| Client-side guard errors | `product_matches.py:19-22` (`ProductMatchPartiesError`, `SHIPPING_SDK_FIELD_ERROR`) | Same pattern for `PostalCodeNotServableError` |
| Error shape remaps | `providers/.../error.py:30-81` (`_extract_errors`, productapi remap at `:42-46`) | Add third shape `ErrorResult {status, errorCode, userMessage}` |
| Test templates | `tests/dhl_express/test_address.py`, `tests/dhl_freight_sweden/test_product_matches.py`, `fixture.py` `zpl_gateway` config variant | New `test_address.py`; `address_validation` gateway fixture variant |
| Capability/proxy-method detection | `modules/sdk/karrio/references.py:427-441` (`detect_proxy_methods` scans subclass `__dict__`), `modules/sdk/karrio/core/units.py:202-241` (`map_capability`) | Implementing `validate_address` on the subclass registers it automatically |
| External-tooling guide | `docs/notes/guides/dhl-freight-sweden-pudo-one-click-booking.md` | Append a validate_address section with the gateway snippet |
| Vendored API spec | `modules/connectors/dhl_freight_sweden/vendor/se-api-farm/postalcode-api-2.10.0.json` | Authoritative endpoint/schema source |

### Architecture Overview

```
External tooling (no backend)                Booking flow
─────────────────────────────                ─────────────────────────────────
karrio.Address.validate(payload)             models.ShipmentRequest
        │                                              │
        ▼                                              ▼
gateway.check("validate_address")            mapper.create_shipment_request
        │                                    (provider shipment/create.py)
        ▼                                              │
mapper.create_address_validation_request               ▼ lib.Serializable
        │                                     proxy.create_shipment
        ▼                                              │
proxy.validate_address ─────────┐            config.address_validation ≠ off,
        │                       │            service → product 118, consignee SE?
        ▼                       │                    │            │
GET {postal_code_api_url}       │              no ───┘    yes ────┤
 /postalcodes/{cc}/{pc}/route ──┤                                 ▼
        │                       │                    same GET ──► evaluate_route
        ▼                       │                                 │
provider address.py:            │            warn: message + book │ enforce:
 evaluate_route(route, product) │            enforce: block on     definitive negative
  118 → homeDeliveryParcel      │              definitive negative → raise
  else → bookable               │            infra error → fail open
        │                       │                                 │
        ▼                       │                                 ▼
AddressValidationDetails        │                    POST sendtransportinstruction
 + List[Message]                │                                 │
                                │                                 ▼
                                │                    POST printdocumentsbyid
                                │                                 │
                                └────────────────► parse_shipment_response
                                                    (+ optional warn messages)
```

### Sequence Diagram

```
Caller        gateway/mapper        proxy                  DHL API
  │                │                  │                      │
  │ validate(...)  │                  │                      │
  │───────────────>│ check("validate_address")               │
  │                │ create_address_validation_request       │
  │                │──────────────►   │                      │
  │                │                  │ GET /postalcodes/    │
  │                │                  │   SE/{pc}/route      │
  │                │                  │─────────────────────>│
  │                │                  │   PostalCodeRouteInfo│
  │                │                  │<─────────────────────│
  │                │ parse_address_validation_response       │
  │ (details,      │                  │                      │
  │  messages)     │                  │                      │
  │<───────────────│                  │                      │
```

Booking pre-flight (`mode = warn|enforce`):

```
Caller        mapper               proxy                  DHL API
  │ create_shipment │                 │                      │
  │────────────────>│ shipment_request│                      │
  │                 │────────────────►│                      │
  │                 │                 │ [pre-flight]         │
  │                 │                 │ GET .../route ──────>│
  │                 │                 │<─────────────────────│
  │                 │                 │ enforce + negative:  │
  │                 │                 │   raise, no booking  │
  │                 │                 │ else:                │
  │                 │                 │ POST transportinstr >│
  │                 │                 │<─────────────────────│
  │                 │                 │ POST print/by-id ───>│
  │                 │                 │<─────────────────────│
  │                 │ parse_shipment_response (+messages)    │
  │<────────────────│                 │                      │
```

### Data Flow Diagram

```
┌──────────────────────────── REQUEST ────────────────────────────┐
│ AddressValidationRequest ──► address_validation_request         │
│   {address, options.service?}      │ {cc, pc, service?}         │
│ models.ShipmentRequest ──────► shipment_request (unchanged)     │
│                                   │ serialized JSON             │
│                     proxy: extract productCode + consignee      │
└──────────────────────────────────────────────────────────────────┘
┌─────────────────────────── RESPONSE ────────────────────────────┐
│ PostalCodeRouteInfo ──► evaluate_route ──► flag per product     │
│   {city, lineHaul, terminalId, deviating,     118: homeDelivery │
│    updatedDate, bookable, homeDeliveryParcel} else: bookable    │
│ flag ──► AddressValidationDetails{success, complete_address}    │
│      └─► pre-flight decision: book | warn+book | raise          │
└──────────────────────────────────────────────────────────────────┘
```

### Data Models

```python
# providers/.../units.py — validation mode + connection config
# (named ServabilityMode, not AddressValidationMode: a class name containing
# "Address" makes the references parse_type heuristic classify the option as
# the Address model type, which the dashboard config renderer drops)
class ServabilityMode(lib.StrEnum):
    off = "off"
    warn = "warn"
    enforce = "enforce"

class ConnectionConfig(lib.Enum):
    # ... existing entries ...
    address_validation = lib.OptionEnum(
        "address_validation", ServabilityMode, "off"
    )

# providers/.../address.py — shared evaluation
PRODUCT_SERVICABILITY_FLAGS = {"118": "homeDeliveryParcel"}

def evaluate_route(route: dict, product: str = None) -> bool:
    """Servability flag for a product on a route response.

    Falls back to the general `bookable` flag for products without a
    documented per-product flag.
    """

# providers/.../address.py — client-side guard raised by enforce mode
class PostalCodeNotServableError(errors.ShippingSDKDetailedError):
    """Raised when the destination postal code is not servable for the product."""
    code = "SHIPPING_SDK_FIELD_ERROR"
```

Unified response mapping (no SDK model changes):

| `AddressValidationDetails` field | Source |
|---|---|
| `success` | `evaluate_route(route, product)` |
| `complete_address` | `Address(city=route.city, postal_code=route.postalCode, country_code=route.countryCode)` |
| failures | `List[Message]` via `parse_error_response` (incl. new `ErrorResult` shape) |

### Field Reference

`GET /postalcodes/{countryCode}/{postalCode}/route` response (`PostalCodeRouteInfo`):

| Field | Type | Used | Description |
|-------|------|------|-------------|
| `countryCode` | string | yes | Echoed country |
| `postalCode` | string | yes | Echoed postal code |
| `city` | string | yes | DHL canonical city for the code (`complete_address`) |
| `lineHaul` | string | no | Domestic routing code (label data) |
| `terminalId` | string | no | Serving terminal (label data) |
| `deviating` | string (bool in `UpdateInfo`; spec inconsistency) | no | Deviating city/postal pairing |
| `updatedDate` | date-time | no | Register freshness |
| `bookable` | bool | yes | General servability (unscoped `success`) |
| `homeDeliveryParcel` | bool | yes | Product 118 availability (scoped `success`) |

Errors (HTTP 400): `ErrorResult {status: int, errorCode: int, userMessage: str}`.

### API Changes

Karrio surface: none added manually.
Implementing the protocol method auto-registers `validate_address` in proxy methods, which opens the server's existing `Address.validate` route (406 gate at `modules/core/karrio/server/core/gateway.py:253`).
The dashboard connection dialog renders the `address_validation` enum option as a Select automatically from `/v1/references`.
Two conditions must hold: the option must classify as a string enum — `parse_type` in `karrio.references` classifies any enum class whose name contains "Address" as the Address model type, which the dialog's config renderer drops (hence `ServabilityMode`, locked in by a references-payload regression test) — and the server must have rebuilt its boot-cached reference models since the connector version shipped (API restart; constance `DHL_FREIGHT_SWEDEN_ENABLED` gates inclusion).

DHL surface consumed (one endpoint of seven; full list in Appendix A):

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `{postal_code_api_url}/postalcodes/{countryCode}/{postalCode}/route` | Unified validation + booking pre-flight |

Hosts: `postal_code_api_url = {server_url}/postalcodeapi/v1` where `server_url` follows the existing test/prod resolution (`utils.py:15-26`); the vendored spec lists only the test host, prod base path follows the sibling-API convention.

---

## Edge Cases & Failure Modes

### Edge Cases

| Scenario | Expected Behavior | Handling |
|----------|-------------------|----------|
| `homeDeliveryParcel = false` | warn: message + book; enforce: block | `evaluate_route` → mode branch |
| 4xx `ErrorResult` (invalid postal code) | warn: message + book; enforce: block | `parse_error_response` remap; definitive negative |
| Network error / 5xx / timeout | warn + book in both modes (fail open) | Distinguish exception/no-response from DHL error body |
| `homeDeliveryParcel = true` | Book normally | — |
| Service ≠ 118 or consignee ≠ SE | Skip pre-flight entirely (no HTTP call) | Trigger condition D6 |
| Consignee postal code missing | Skip pre-flight; DHL booking surfaces its own field error | Pre-flight checks servability, not field presence (that is `shipment_request`'s job) |
| Country code casing (`se`/`SE`) | Normalize upper before URL build | `str.upper()` |
| Postal code with spaces (`111 20`) | Pass through URL-encoded | Prior live practice used bare digits; no normalization |
| Unscoped unified call | `success = bookable` | D5 |
| `options.service` accepts karrio service code or `"118"` | Resolve via `ShippingService.map(...).value_or_key` | Same resolution as `create.py:118` |
| Non-SE country in unified call | Surface DHL `ErrorResult` as `Message` (API is SE-oriented) | No connector-side country guard on the unified path |
| Config value casing or unrecognized mode value | Resolve case-insensitively; values naming no mode resolve to `off` (no check) | `proxy._destination_route_messages` mode resolution |

### Failure Modes

| What Can Go Wrong | Impact | Mitigation |
|-------------------|--------|------------|
| PostalCodes API outage under `enforce` | Bookings would fail | Fail-open by design (warn + proceed) |
| `mapper.py` regeneration conflicts | Broken fluent wiring | Verify generation mechanism first; wire through the generator if mapper.py is generated, hand-edit only if repo practice shows it is hand-maintained |
| Capabilities drift-guard failure | `test_services.py` assertion breaks | Settle the contradictory research claims empirically (`get_carrier_capabilities()` run) and assert the actual result |
| Stale references payload after deploy | Dashboard shows no `address_validation` option | Restart the API (reference models are built at import and cached) and verify `/v1/references` lists the option with `type: "string"` |
| Undocumented prod base path | 404s in production | Follow sibling convention; verify with one live route GET against prod when credentials allow |
| Warn-mode message plumbing breaks existing parse | Existing shipment tests fail | Optional third `Deserializable` element only appended when a warning exists; default `off` path byte-identical |

---

## Implementation Plan

### Phase 1: Foundation

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| `ServabilityMode` enum + `ConnectionConfig.address_validation` option | `providers/.../units.py` | Pending | S |
| `postal_code_api_url` property | `providers/.../utils.py` | Pending | S |
| `ErrorResult` shape remap | `providers/.../error.py` | Pending | S |

### Phase 2: Unified capability

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Provider module: request builder, parser, `evaluate_route`, flag map | `providers/.../address.py` (new) | Pending | M |
| Proxy `validate_address` (GET route) | `mappers/.../proxy.py` | Pending | S |
| Mapper trio wiring (verify generation mechanism first) | `mappers/.../mapper.py` | Pending | S |
| Stale METADATA header comment cleanup | `plugins/.../__init__.py` | Pending | S |
| Drift guard: proxy method + capabilities assertion | `tests/.../test_services.py` | Pending | S |

### Phase 3: Booking pre-flight

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Pre-flight in `create_shipment` (trigger condition, mode branch, fail-open) | `mappers/.../proxy.py` | Pending | M |
| `PostalCodeNotServableError` | `providers/.../address.py` | Pending | S |
| Optional warning element in `parse_shipment_response` | `providers/.../shipment/create.py` | Pending | S |

### Phase 4: Tests and docs

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| `test_address.py` (4-method pattern) | `tests/.../test_address.py` (new) | Pending | M |
| Pre-flight matrix tests | `tests/.../test_shipment.py` | Pending | M |
| `address_validation` gateway fixture variant | `tests/.../fixture.py` | Pending | S |
| Sandbox route capture for fixtures | `tests/.../test_address.py` fixtures | Pending | S |
| Guide section with gateway snippet | `docs/notes/guides/dhl-freight-sweden-pudo-one-click-booking.md` | Pending | S |

**Dependencies:** Phase 2 and 3 depend on Phase 1; Phase 4 depends on 2 and 3.

---

## Testing Strategy

> All tests follow the connector's unittest patterns (no pytest), module-level fixture constants, and `unittest.mock.patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request")` for HTTP mocks, per `test_product_matches.py`.

### Test Categories

| Category | Location | Coverage Target |
|----------|----------|-----------------|
| Unit — unified capability | `tests/dhl_freight_sweden/test_address.py` | Request/HTTP/parse/error |
| Unit — pre-flight matrix | `tests/dhl_freight_sweden/test_shipment.py` | Every semantics-table row |
| Unit — registration | `tests/dhl_freight_sweden/test_services.py` | Proxy method + capabilities |

### Test Cases

```python
class TestDHLFreightSwedenAddressValidation(unittest.TestCase):
    def test_create_address_validation_request(self):
        """Unscoped and service-scoped serializations."""
        ...

    def test_validate_address(self):
        """GET route URL, client-key header, on_error decoder."""
        request = address.address_validation_request(AddressValidationParams, gateway.settings)
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.return_value = RouteResponse
            gateway.proxy.validate_address(request)
            self.assertEqual(mock.call_args.kwargs["method"], "GET")
            self.assertIn("/postalcodes/SE/11120/route", mock.call_args.kwargs["url"])

    def test_parse_address_validation_response(self):
        """Route dict -> AddressValidationDetails (scoped and unscoped)."""
        ...

    def test_parse_error_response(self):
        """ErrorResult -> List[Message]."""
        ...
```

Pre-flight matrix in `test_shipment.py` (each against the `address_validation` fixture gateway):

| Test | Config | Route mock | Expectation |
|------|--------|-----------|-------------|
| off makes no route call | `off` | unused | zero calls to route URL; booking proceeds |
| warn + servable | `warn` | `homeDeliveryParcel: true` | books, no extra messages |
| warn + not servable | `warn` | `homeDeliveryParcel: false` | books, warning message present |
| enforce + not servable | `enforce` | `homeDeliveryParcel: false` | raises `PostalCodeNotServableError`, no booking POST |
| enforce + invalid code | `enforce` | 400 `ErrorResult` | raises, no booking POST |
| enforce + outage | `enforce` | `lib.request` raises | books with warning (fail open) |
| enforce + non-118 service | `enforce` | unused | no route call, books |
| enforce + non-SE consignee | `enforce` | unused | no route call, books |

### Running Tests

```bash
source bin/activate-env
python -m unittest discover -v -f modules/connectors/dhl_freight_sweden/tests
```

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| mapper.py is generated and hand-editing breaks regeneration | High | Medium | Verify mechanism before editing (Phase 2 first task); wire through generator if generated |
| Capabilities set changes unexpectedly | Medium | Low | Empirical drift-guard assertion; one research claim says `validate_address` maps into existing `shipping` |
| Prod base path differs from convention | Medium | Low | Single live GET verification when prod credentials allow; `server_url` config override as escape hatch |
| Fail-open masks persistent API breakage under enforce | Medium | Low | Fail-open still emits a warning message per booking, making breakage visible |
| Warn-mode plumbing perturbs existing parse | Medium | Low | Optional third element only when warning exists; default path asserted unchanged |

---

## Migration & Rollback

### Backward Compatibility

- **API compatibility**: existing methods untouched; `validate_address` was previously `MethodNotSupportedError` and now succeeds — strictly additive.
- **Behavior compatibility**: default config `off` keeps `create_shipment` byte-identical (asserted by test); existing fixtures and tests unchanged.
- **Feature flags**: the `address_validation` connection config is the rollout lever — `off` → `warn` → `enforce` per connection, no deploy required (config is read at gateway creation).

### Rollback Procedure

1. Set affected connections' `address_validation` back to `off` (immediate, no code).
2. If code rollback is needed, revert the branch; no migrations, no data, no schema changes.

---

## Appendices

### Appendix A: PostalCodes API reference

Spec: `modules/connectors/dhl_freight_sweden/vendor/se-api-farm/postalcode-api-2.10.0.json` (OpenAPI 3.0.4, "Postalcode API" v2.10.0).
Auth: `client-key` HTTP header (same scheme as all sibling APIs).
Base: `{server_url}/postalcodeapi/v1/`.

| Method | Endpoint | Used | Response |
|--------|----------|------|----------|
| GET | `/postalcodes/{countryCode}/{postalCode}/route` | **yes** | `PostalCodeRouteInfo` |
| POST | `/postalcodes/validate` | no | boolean (`ValidationModel` incl. `allowDeviating`) |
| GET | `/postalcodes/{countryCode}/{postalCode}/info/{productCode}` | no | `PostalCodeInfo` (productCode semantics undocumented) |
| GET | `/postalcodes/{countryCode}/{postalCode}/gateway` | no | `PostalCodeGatewayInfo` |
| GET | `/postalcodes/{countryCode}/{city}` | no | `PostalCodeInfo[]` |
| GET | `/postalcodes/{countryCode}/updated?fromDate=` | no | delta rows incl. `deleted` tombstones (future register sync) |
| GET | `/postalcodes/ping` | probe | 200 OK |

Manual: SE product manual v5.23, §10.14.8 (p.243): "For product DHL HEMLEVERANS PAKET (118), this API is used to check availability for a postal code. If parameter homeDeliveryParcel = true, then product is available." Local copy: `/home/joaqim/.local/state/agent-logs/karrio/phone-print-probe/manuals/se-product-manual-v5.23.txt`.

### Appendix B: Product code context

| Connector service code | Carrier product code | Service name |
|------------------------|----------------------|--------------|
| `dhl_freight_sweden_hemleverans_paket_b2c` | 118 | Hemleverans Paket B2C (validation target) |
| `dhl_freight_sweden_home_delivery_b2c` | 401 | Home Delivery B2C |
| `dhl_freight_sweden_home_delivery_c2b` | 402 | Home Delivery C2B |
| `dhl_freight_sweden_home_delivery_c2b_502` | 502 | Home Delivery C2B |

### Appendix C: External-tooling invocation (guide snippet)

```python
import karrio.sdk as karrio
from karrio.mappers.dhl_freight_sweden.settings import Settings

gateway = karrio.gateway["dhl_freight_sweden"].create(
    Settings(client_key=CLIENT_KEY, account_number=ACCOUNT_NUMBER, test_mode=True)
)

details, messages = karrio.Address.validate(
    {
        "address": {"postal_code": "11120", "country_code": "SE"},
        "options": {"service": "dhl_freight_sweden_hemleverans_paket_b2c"},
    }
).from_(gateway).parse()
# details.success is True iff route.homeDeliveryParcel is True (product 118)
```
