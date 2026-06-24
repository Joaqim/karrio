# PostNord Service Points (connector-local capability)

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-06-24 |
| Status | Planning |
| Owner | PostNord connector |
| Type | Enhancement (LSP-style capability) |
| Reference | [PRD_POSTNORD_INTEGRATION.md](./PRD_POSTNORD_INTEGRATION.md) (D6), [AGENTS.md](../AGENTS.md) |

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

PostNord exposes a Service Points API (`servicepoints-v5`) that returns nearby pickup locations (agents, parcel lockers, collect-in-store) for a destination — the lookup behind MyPack Collect.
Karrio has no unified service-point contract (no core models, no `CarrierCapabilities` member, no SDK fluent entry), so this PRD adds the lookup as a **connector-local, duck-typed proxy method** (`find_service_points`) inside the existing PostNord connector, reachable via `gateway.proxy.find_service_points(...)`, with no changes to SDK core, Django, or GraphQL.
This resolves D6 (previously deferred) by implementing the LSP-style pattern the connector's swagger-ingestion findings prescribed.

### Key Architecture Decisions

1. **Connector-local proxy method, not a first-class SDK capability**: add `find_service_points` to the PostNord `Proxy`; no `karrio.ServicePoints.find` fluent entry and no new `karrio.core.models` pair, keeping the change inside `modules/connectors/postnord/` (D6's "no new core/Django/GraphQL contract").
2. **Housed in the existing connector, not a standalone `plugins/` package**: PostNord is a dual-purpose carrier; service points reuses its existing `apikey`/gateway rather than a separate LSP plugin (unlike `googlegeocoding`, which has no carrier side).
3. **Normalized dict return shape, parsed without a generated schema**: since no unified `ServicePoint` model exists, the parser returns a stable connector-local list of dicts, parsing the response as a plain dict with `lib` helpers (the transit-time precedent) to avoid generating the heavy `servicepoints-v5` schema.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| `find_service_points` proxy method (GET, apikey) | New `karrio.core.models` ServicePoint pair |
| `byaddress` lookup (primary) + `bycoordinates` (when coordinates given) | A `karrio.ServicePoints.find` SDK fluent entry |
| Normalized dict result (id, name, type, address, coordinates, hours, distance) | Django REST route / GraphQL query / dashboard UI |
| `ServicePointType`/context enums in `units.py` | Selecting a service point and attaching it to a booking |
| 4-method unittest coverage + fixtures | Bulk/admin servicepoint ops (`/ids`, `/delta`, BLOM sync) |

---

## Open Questions & Decisions

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| SP1 | Capability shape | Connector-local proxy method (no SDK-core contract) | User-selected. Keeps the change self-contained per D6; avoids an upstream-design decision on a brand-new SDK capability. | 2026-06-24 |
| SP2 | Housing | Inside `modules/connectors/postnord/` | PostNord is already a carrier connector; reuse its `apikey`/gateway rather than a standalone `plugins/` LSP package. | 2026-06-24 |
| SP3 | Auth | Reuse `Settings.apikey` (query param) | Service Points spec is `SECURED: False`, `apikey` in query — identical to the connector's existing model. | 2026-06-24 |
| SP4 | Primary endpoint | `GET /v5/servicepoints/nearest/byaddress`; `bycoordinates` when coordinates are supplied | Address is the input Karrio naturally has; coordinate variant covers map-driven callers. | 2026-06-24 |
| SP5 | Return shape | Normalized list of dicts; parse response as dict, no generated schema | No unified model to target; dict parsing matches the transit-time approach and avoids the large servicepoints schema generation. | 2026-06-24 |
| SP6 | Error handling | Reuse `providers/postnord/error.py::parse_error_response` | The servicepoints `ResponseDto` carries the same `compositeFault` shape the parser already handles. | 2026-06-24 |

### Edge Cases Requiring Input

| Edge Case | Impact | Proposed Handling | Needs Input? |
|-----------|--------|-------------------|--------------|
| Exact base path under `server_url` | Wrong path → 404 | The `servicepoints-v5` swagger has null `host`/`basePath`; assume PostNord's business-location base (`/rest/businesslocation/v5/servicepoints/...`) and confirm on the live-validation pass, mirroring the transit-time base-path caveat. | Confirm live (not blocking the PRD) |

---

## Problem Statement

### Current State

```python
# PostNord can rate/ship/track/pickup, but cannot look up pickup locations.
gw = karrio.gateway["postnord"].create(settings)
gw.proxy.find_service_points  # AttributeError: no such method
# MyPack Collect (service 19) has no way to surface its collection points.
```

### Desired State

```python
# Connector-local capability, reached via the gateway proxy (no SDK fluent entry).
import karrio.providers.postnord.service_points as service_points

response = gw.proxy.find_service_points(
    service_points.service_points_request(
        dict(country_code="SE", postal_code="11528", number_of_points=3),
        gw.settings,
    )
)
points, messages = service_points.parse_service_points_response(response, gw.settings)
# points -> [{"id": "...", "name": "...", "type": "...", "address": {...},
#            "coordinates": {...}, "opening_hours": [...], "distance": 123}, ...]
```

### Problems

1. **No pickup-location lookup**: MyPack Collect cannot present collection points, the core use of the Service Points API.
2. **No unified contract to extend**: karrio has no `ServicePoint` model/op, so a first-class capability would mean an upstream-scoped SDK-core change; this PRD intentionally stays connector-local.

---

## Goals & Success Criteria

### Goals

1. Provide a PostNord service-point lookup callable from the gateway proxy, returning a stable normalized result.
2. Keep the change entirely within `modules/connectors/postnord/` (no SDK core / Django / GraphQL).
3. Cover the capability with the connector's 4-method unittest pattern.

### Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| `find_service_points` issues the correct GET (URL, apikey, params) | Verified by test | Must-have |
| Response parses into the normalized dict shape | Verified by test | Must-have |
| Error body surfaces Messages via `error.py` | Verified by test | Must-have |
| Connector suite stays green | 25 → 29 tests | Must-have |
| `bycoordinates` variant | Supported when coordinates given | Nice-to-have |

### Launch Criteria

**Must-have (P0):**
- [ ] `find_service_points` proxy method + `service_points_request`/`parse_service_points_response`
- [ ] `byaddress` lookup with apikey auth
- [ ] 4-method tests pass

**Nice-to-have (P1):**
- [ ] `bycoordinates` variant
- [ ] `ServicePointType`/context enums in `units.py`

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Connector-local proxy method | Self-contained; reuses apikey/gateway; no upstream-core risk; matches D6 | Not reachable via the standard `karrio.X.op()` SDK/dashboard surface | **Selected** (SP1) |
| First-class SDK capability (new core models + `karrio.ServicePoints.find` + detector) | Fully integrated; dashboard-usable | Touches shared SDK core; upstream-design decision; supersedes D6's no-core stance | Rejected |
| Standalone `plugins/` LSP package | Independently installable | Duplicates a second apikey/gateway for the same account; PostNord already has a connector | Rejected |
| Defer (keep blueprint only) | No work | Leaves MyPack Collect without its lookup | Rejected |

### Trade-off Analysis

The connector-local method delivers the lookup with the least surface area and zero risk to shared SDK code, at the cost of not being a first-class SDK operation.
That trade-off is acceptable because no unified service-point contract exists to be a first-class citizen of, and defining one is an upstream-design decision out of scope here.
If karrio later introduces a unified contract, the connector-local `service_points_request`/`parse_service_points_response` functions are the natural adapters to wire into it, so this is a forward-compatible step rather than a dead end.

---

## Technical Design

> Studied the `googlegeocoding` LSP plugin (the duck-typed capability reference), the existing PostNord `proxy.py`/`error.py`/`units.py`, and the vendored `servicepoints-v5` spec.

### Existing Code Analysis

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| LSP duck-typed capability pattern | `plugins/googlegeocoding/karrio/mappers/googlegeocoding/proxy.py` (`validate_address`) | Template for a single GET proxy method + provider request/parse pair |
| Capability is "supported" iff proxy has the method | `modules/sdk/karrio/api/gateway.py` (`proxy_methods` reflection) | `find_service_points` becomes discoverable purely by existing on the Proxy |
| PostNord URL builder + apikey | `modules/connectors/postnord/karrio/mappers/postnord/proxy.py` (`_url`) | Reuse to append `?apikey=` + query params |
| Error parsing (compositeFault/faults) | `modules/connectors/postnord/karrio/providers/postnord/error.py` | Reuse `parse_error_response` for the servicepoints `ResponseDto` faults |
| Dict-based response parsing (no schema) | `modules/connectors/postnord/karrio/providers/postnord/rate.py` (transit merge) | Parse the servicepoints response as a dict with `lib` helpers |
| Enums home | `modules/connectors/postnord/karrio/providers/postnord/units.py` | Add `ServicePointType`/context enums |
| API spec | `modules/connectors/postnord/vendor/servicepoints-v5.swagger.json` | Field reference for request params + `ResponseDto` |

### Architecture Overview

```
┌──────────────┐   find_service_points   ┌───────────────────┐   GET byaddress   ┌──────────────┐
│ Caller / SDK │────────────────────────>│ postnord Proxy    │──────────────────>│ PostNord     │
│ gateway.proxy│                         │ (_url + apikey)   │   ?apikey=...      │ Service      │
└──────┬───────┘                         └─────────┬─────────┘                   │ Points v5    │
       │                                           │                             └──────┬───────┘
       │ service_points_request(params)            │ Deserializable[dict]               │
       ▼                                           ▼                                    │
┌──────────────────────────┐            ┌────────────────────────────┐                 │
│ providers.service_points │            │ parse_service_points_       │<────────────────┘
│ (build query Serializable)│           │ response -> ([points], msgs)│   ResponseDto / fault
└──────────────────────────┘            └────────────────────────────┘
```

### Sequence Diagram

```
┌────────┐        ┌────────┐        ┌──────────────┐        ┌──────────┐
│ Caller │        │ Proxy  │        │ providers.sp │        │ PostNord │
└───┬────┘        └───┬────┘        └──────┬───────┘        └────┬─────┘
    │ service_points_request(params)       │                     │
    │─────────────────────────────────────>│                     │
    │<─── Serializable(query) ─────────────│                      │
    │ find_service_points(serializable)    │                      │
    │────────────────────>│                │                      │
    │                     │  GET byaddress?apikey=...&params       │
    │                     │───────────────────────────────────────>│
    │                     │<──────────── ResponseDto ──────────────│
    │<── Deserializable[dict] ──────────────│                      │
    │ parse_service_points_response(resp)   │                      │
    │─────────────────────────────────────>│                      │
    │<──── ([service_points], [messages]) ──│                      │
```

### Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                         REQUEST FLOW                               │
│  ┌─────────┐    ┌──────────────────┐    ┌─────────────┐           │
│  │ params  │───>│ service_points_  │───>│ GET query   │──> PostNord│
│  │ dict    │    │ request()        │    │ (apikey,..) │            │
│  └─────────┘    └──────────────────┘    └─────────────┘           │
├──────────────────────────────────────────────────────────────────┤
│                         RESPONSE FLOW                              │
│  ┌──────────────┐  ┌──────────────────────┐  ┌────────────┐       │
│  │ [normalized  │<─│ parse_service_points_│<─│ ResponseDto│<─ PN   │
│  │  point dicts]│  │ response (+ error.py)│  │ / fault    │        │
│  └──────────────┘  └──────────────────────┘  └────────────┘       │
└──────────────────────────────────────────────────────────────────┘
```

### Data Models

No `karrio.core.models` changes. The normalized connector-local result shape (returned as plain dicts via `lib.to_dict`):

```python
# Normalized service point (connector-local dict shape; not a core model)
{
    "id": str,                  # servicePointId
    "name": str,                # name
    "type": str,                # type / servicePointType
    "address": {                # from deliveryAddress/visitingAddress (models.Address-shaped)
        "address_line1": str,   # streetName + streetNumber
        "city": str,
        "postal_code": str,
        "country_code": str,
    },
    "coordinates": {            # PostNord uses easting/northing + SRID
        "northing": float,
        "easting": float,
        "sr_id": str,
    },
    "opening_hours": list,      # openingHours.postalServices (passed through)
    "distance": int,            # routeDistance (meters from the query point)
}
```

### Field Reference (request)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `returnType` | string | Yes | Fixed `json` |
| `countryCode` | string | Yes | ISO country of the search |
| `postalCode` | string | One of postal/city | Recipient postal code (byaddress) |
| `city` / `streetName` / `streetNumber` | string | No | Refine the address search |
| `numberOfServicePoints` | int | No | Cap on results (proximity-ordered) |
| `typeId` | string | No | Filter by point type (e.g. `2` box, `25` SE servicepoint, `51` collect-in-store) |
| `context` | string | No | e.g. `optionalservicepoint` |
| `apikey` | string | Yes | Appended by `_url` (query param) |

### API Changes

**Endpoints (consumed; no Karrio API surface change):**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v5/servicepoints/nearest/byaddress` | Nearest points by address (primary) |
| GET | `/v5/servicepoints/nearest/bycoordinates` | Nearest points by coordinates (P1) |

---

## Edge Cases & Failure Modes

### Edge Cases

| Scenario | Expected Behavior | Handling |
|----------|-------------------|----------|
| No points found | Empty list, no crash | `parse_service_points_response` returns `([], [])` |
| Missing required `countryCode`/postal | Request rejected by PostNord | Surface the fault via `error.py` |
| Coordinates supplied instead of address | Use `bycoordinates` | `service_points_request` routes by which params are present (P1) |
| Verbose/partial point records | Normalize defensively | `lib`-guarded dict access; omit missing keys |

### Failure Modes

| What Can Go Wrong | Impact | Mitigation |
|-------------------|--------|------------|
| Wrong base path (null host in spec) | 404, no points | Confirm base path on live-validation pass (see edge-case table) |
| Service Points API down | No lookup | Return the fault as Messages; callers degrade (lookup is non-blocking to shipping) |
| apikey lacks Service Points scope | 401/403 | Surface fault via `error.py` |

### Security Considerations

- [x] apikey travels as a query param by carrier design (same as existing ops); ensure trace redaction covers it (shared connector concern).
- [x] No new secrets; reuse existing `Settings.apikey`.
- [x] Input is read-only lookup; no tenant data written.

---

## Implementation Plan

### Phase 1: Capability

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| `find_service_points` proxy method (GET via `_url`) | `modules/connectors/postnord/karrio/mappers/postnord/proxy.py` | Pending | S |
| `service_points_request` + `parse_service_points_response` (dict parse, normalize, reuse `error.py`) | `modules/connectors/postnord/karrio/providers/postnord/service_points.py` (new) | Pending | M |
| `ServicePointType` / context enums | `modules/connectors/postnord/karrio/providers/postnord/units.py` | Pending | S |
| Provider re-exports | `modules/connectors/postnord/karrio/providers/postnord/__init__.py` | Pending | S |

### Phase 2: Tests

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| 4-method tests + fixtures | `modules/connectors/postnord/tests/postnord/test_servicepoints.py`, `fixture.py` | Pending | M |

**Dependencies:** Phase 2 depends on Phase 1.

---

## Testing Strategy

> `unittest` only (never pytest). Run from repo root. Module-level fixture constants; `assertListEqual` on `lib.to_dict`; `mock.ANY` for dynamic fields.

### Test Cases

```python
"""PostNord service points tests (connector-local capability)."""

import unittest
from unittest.mock import patch
from .fixture import gateway

import karrio.lib as lib
import karrio.providers.postnord.service_points as service_points


class TestPostNordServicePoints(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_create_service_points_request(self):
        request = service_points.service_points_request(SearchParams, gateway.settings)
        self.assertEqual(lib.to_dict(request.serialize()), ServicePointsQuery)

    def test_find_service_points(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            request = service_points.service_points_request(SearchParams, gateway.settings)
            gateway.proxy.find_service_points(request)
            url = mock.call_args.kwargs["url"]
        self.assertIn("/v5/servicepoints/nearest/byaddress", url)
        self.assertIn("apikey=TEST_API_KEY", url)
        self.assertEqual(mock.call_args.kwargs["method"], "GET")

    def test_parse_service_points_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ServicePointsResponse
            request = service_points.service_points_request(SearchParams, gateway.settings)
            parsed = service_points.parse_service_points_response(
                gateway.proxy.find_service_points(request), gateway.settings
            )
            self.assertListEqual(lib.to_dict(parsed), ParsedServicePoints)

    def test_parse_error_response(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = ErrorResponse
            request = service_points.service_points_request(SearchParams, gateway.settings)
            parsed = service_points.parse_service_points_response(
                gateway.proxy.find_service_points(request), gateway.settings
            )
            self.assertListEqual(lib.to_dict(parsed), ParsedErrorResponse)
```

### Running Tests

```bash
nix develop .#default --command bash -c 'export PYTHONPATH=modules/connectors/postnord:$PYTHONPATH; python -m unittest discover -f modules/connectors/postnord/tests'
```

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Base path wrong (null host in spec) | Medium | Medium | Confirm live; isolated to one `_url` path string |
| Result shape churn (verbose schema) | Low | Medium | Normalize to a small stable dict; parse defensively with `lib` |
| Capability invisible to dashboard/SDK fluent API | Low | High (by design) | Documented as connector-local (SP1); forward-compatible if a unified contract lands |
| Test regressions | Low | Low | Additive; run full connector suite before merge |

---

## Migration & Rollback

### Backward Compatibility

- **API compatibility**: purely additive — a new proxy method and a new provider module; no existing op changes.
- **Data compatibility**: read-only lookup; no models, migrations, or stored data.
- **Feature flags**: none needed; the capability is inert unless `find_service_points` is called.

### Rollback Procedure

1. **Identify issue**: lookup returns 404/faults or wrong shape.
2. **Revert changes**: drop the `service_points.py` module, the `find_service_points` proxy method, and the enums (single connector, isolated commit).
3. **Verify recovery**: connector suite green; rate/ship/track/pickup unaffected.
