# PostNord per-product credential verification

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-06-25 |
| Status | Planning |
| Owner | PostNord connector |
| Type | Enhancement |
| Reference | [PRD_POSTNORD_INTEGRATION.md](./PRD_POSTNORD_INTEGRATION.md), [PRD_POSTNORD_SERVICE_POINTS.md](./PRD_POSTNORD_SERVICE_POINTS.md) |

---

## Executive Summary

PostNord authorizes each API product (Booking, Transit Time, Service Points, Tracking) separately per apikey: an unauthorized product returns `403 "Invalid API Key"` even when the same key works for other products (verified live — the configured key 403s on Booking and Transit Time but a different developer key generates sandbox labels).
Today karrio validates carrier credentials only lazily, on the first real operation, so a merchant discovers a missing authorization as a failed label purchase.
This PRD scopes a way to **verify, on demand / at configuration time, which PostNord products a connection's apikey is authorized for**, surfacing per-product status so the merchant knows before buying a label.
The companion error-surfacing fix (already shipped) makes the runtime 403 explicit; this adds proactive verification.

### Key Architecture Decisions

1. **Per-product result, not a single boolean**: because PostNord authorizes per product, verification reports a status per product (Booking / Transit / Service Points / Tracking), not one "valid/invalid".
2. **Connector-local `validate_credentials` proxy method first (Phase 1)**: a duck-typed proxy method (mirroring the `validate_address` / `find_service_points` LSP pattern) that probes each product and returns structured results — reachable via SDK/API with no karrio-core change. A generic server "test connection" endpoint + dashboard button is an optional Phase 2.
3. **Probe with side-effect-free calls only**: use benign GETs (transit, service points) and a health/validation endpoint for Booking; never create a shipment to test booking authorization.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| A connector method that probes per-product apikey authorization | Auto-running verification on every connection save (perf/latency) |
| Structured per-product result (authorized / unauthorized / unknown) | A generic karrio `validate_credentials` SDK contract (Phase 2 / separate) |
| Reuse of existing benign endpoints as probes | Storing/caching authorization state in the DB (Phase 2) |
| Tests with mocked 403 / 200 per product | Dashboard "Test connection" UI (Phase 2) |

---

## Open Questions & Decisions

### Pending Questions

| # | Question | Context | Options | Status |
|---|----------|---------|---------|--------|
| Q1 | Is there a side-effect-free, apikey-authorized probe for **Booking** authorization? | No read-only endpoint clearly exercises the same authorization scope as `POST /v3/edi/labels/pdf`. Candidate: `GET /v3/edi/labels/manage/health` — but health endpoints often bypass auth, so it may 200 regardless of product authorization. | A) Validate `/v3/edi/labels/manage/health` is apikey-gated and product-scoped (live test), B) accept Booking can only be validated on first real booking, C) probe with a deliberately-invalid minimal booking and treat 403 vs 400 distinctly | ⏳ needs live test |
| Q2 | Phase 1 surface: connector proxy method only, or also a server endpoint now? | A proxy method is reachable via SDK/API but not the dashboard without an endpoint. | A) proxy method only (Phase 1), B) proxy method + thin REST/GraphQL pass-through | ⏳ |

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| CV1 | Result shape | Per-product status | PostNord authorizes per product; a single boolean is misleading | 2026-06-25 |
| CV2 | Mechanism (Phase 1) | Connector-local `validate_credentials` proxy method (duck-typed) | No karrio config-time hook exists; matches the LSP proxy-method pattern; no core change | 2026-06-25 |
| CV3 | Probe safety | Side-effect-free calls only | Must never create a real/sandbox shipment to test booking | 2026-06-25 |

### Edge Cases Requiring Input

| Edge Case | Impact | Proposed Handling | Needs Input? |
|-----------|--------|-------------------|--------------|
| Booking health endpoint ignores auth | False "authorized" for Booking | Mark Booking `unknown` if the probe can't distinguish; document | ✅ Yes (Q1) |
| Network/5xx during probe | Can't determine | Report `unknown` (not unauthorized) | ❌ No |
| Key authorized for none | All products `unauthorized` | Surface clearly; connection still saves | ❌ No |

---

## Problem Statement

### Current State

```python
# Credentials are validated lazily — only on the first real operation.
# A missing per-product authorization surfaces as a failed label purchase:
karrio.Shipment.create(req).from_(gateway).parse()
# -> (None, [Message(code="Forbidden", level="error",
#                    message="Invalid API Key: ... not authorized for this service/product")])
# The merchant only finds out at purchase time; there is no proactive check.
```

### Desired State

```python
# On demand (e.g. a dashboard "Test connection" action), probe per product:
results = gateway.proxy.validate_credentials(
    service_points.noop_request(["booking", "transit", "service_points", "tracking"])
)
# -> {"booking": "unknown", "transit": "unauthorized",
#     "service_points": "authorized", "tracking": "authorized"}
# The merchant sees exactly which products their key can use before buying a label.
```

### Problems

1. **Late discovery**: a key not authorized for Booking is only discovered when a label purchase fails.
2. **Per-product opacity**: PostNord's 403 doesn't say *which* product; merchants can't self-diagnose which subscription is missing.

---

## Goals & Success Criteria

### Goals

1. Provide an on-demand, per-product authorization check for a PostNord connection.
2. Use only side-effect-free probes (no shipment creation).
3. Keep Phase 1 connector-local (no karrio-core change).

### Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Per-product status returned for transit/service-points/tracking | Verified by test | Must-have |
| No shipment is ever created by a probe | Verified by test (no POST to `/edi/labels`) | Must-have |
| Booking probe story decided (Q1) | Resolved | Must-have |
| Reachable via SDK/API | Yes | Must-have |
| Dashboard "Test connection" button | — | Nice-to-have (Phase 2) |

### Launch Criteria

**Must-have (P0):**
- [ ] `validate_credentials` proxy method with per-product probes (transit, service points, tracking)
- [ ] Q1 resolved (Booking probe or documented limitation)
- [ ] Tests for authorized/unauthorized/unknown per product

**Nice-to-have (P1):**
- [ ] Server endpoint / GraphQL mutation pass-through
- [ ] Dashboard "Test connection" UI

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Connector-local `validate_credentials` proxy method | No core change; matches LSP duck-typed pattern; reachable via SDK/API | Not in dashboard without a Phase 2 endpoint | **Selected (Phase 1)** |
| First-class karrio `validate_credentials` SDK contract + server "test connection" endpoint | Reusable across all carriers; dashboard-native | Cross-cutting core change; bigger design/buy-in | Deferred (Phase 2) |
| Validate at connection create/update (serializer hook) | Automatic | Couples persistence to a network call; latency + failure semantics on save; per-product complexity | Rejected |
| Do nothing (rely on runtime error surfacing) | Zero work | Late discovery persists | Rejected (error surfacing already shipped, but proactive check still wanted) |

### Trade-off Analysis

The connector-local proxy method is the smallest step that delivers proactive, per-product feedback without a karrio-core change, consistent with how Service Points (D6) was scoped.
A serializer-time auto-probe is rejected because it couples connection save to carrier latency/failure and because PostNord's per-product model means one save-time probe can't validate everything anyway.
The first-class server feature remains the right long-term home (dashboard "Test connection"), deferred to Phase 2.

---

## Technical Design

> Studied: the `validate_address` LSP proxy-method pattern (`plugins/googlegeocoding`), our `find_service_points` (`providers/postnord/service_points.py`), the transit probe (`proxy._get_transit_times`), the booking spec health op (`/v3/edi/labels/manage/health`), and karrio's connection lifecycle (no config-time hook).

### Existing Code Analysis

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| Duck-typed proxy-method capability | `plugins/googlegeocoding/.../proxy.py` (`validate_address`) | Template for a `validate_credentials` method |
| Benign GET probes already built | `mappers/postnord/proxy.py` (`_get_transit_times`), `providers/postnord/service_points.py` | Reuse as transit / service-point probes |
| Gateway auth-error envelope parsing | `providers/postnord/error.py` (`_authorization_message`, gateway branch) | Classify probe responses (403 → unauthorized) |
| Booking health op | `vendor/booking.swagger.json` `GET /v3/edi/labels/manage/health` | Candidate Booking probe (pending Q1) |
| No config-time validation hook | `server/providers/serializers/base.py`, `graph/.../mutations.py` | Confirms Phase 2 needs a NEW endpoint |

### Architecture Overview

```
┌──────────────┐  validate_credentials   ┌──────────────────────┐
│ Caller / SDK │────────────────────────>│ postnord Proxy        │
│ (Phase 2:    │                         │ probe each product:   │
│  dashboard   │<────────────────────────│  GET transit  ───────────> 403/200
│  Test conn.) │   {product: status}     │  GET servicepoints ──────> 403/200
└──────────────┘                         │  GET tracking ───────────> 403/200
                                         │  GET edi/.../health (Q1) ─> 200?
                                         └──────────┬────────────┘
                                                    │ classify via error.py
                                                    ▼
                                         {booking, transit,
                                          service_points, tracking}
                                          = authorized|unauthorized|unknown
```

### Probe map (per product)

| Product | Probe (side-effect-free) | authorized | unauthorized | unknown |
|---------|--------------------------|-----------|--------------|---------|
| Transit | `GET /rest/transport/v2/transittime/addresstoaddress` | 200 | 403 | network/5xx |
| Service Points | `GET /rest/businesslocation/v5/servicepoints/nearest/byaddress` | 200 | 403 | network/5xx |
| Tracking | `GET /rest/links/v1/tracking/{cc}/{id}` | 200 | 403 | network/5xx |
| Booking | `GET /v3/edi/labels/manage/health` (Q1 — confirm apikey-gated) | 200 (if gated) | 403 | health bypasses auth → `unknown` |

### Data Models

No `karrio.core.models` change. Connector-local result dict:
```python
# validate_credentials -> Deserializable[dict]; parsed to:
{
    "booking": "authorized" | "unauthorized" | "unknown",
    "transit": "authorized" | "unauthorized" | "unknown",
    "service_points": "authorized" | "unauthorized" | "unknown",
    "tracking": "authorized" | "unauthorized" | "unknown",
}
```
Classification reuses `error.py`: a `{"error":{"status_code":403,...}}` body → `unauthorized`; a 200 → `authorized`; anything else → `unknown`.

---

## Edge Cases & Failure Modes

| Scenario | Expected Behavior | Handling |
|----------|-------------------|----------|
| Product 403 | `unauthorized` | classify via gateway envelope |
| Probe 200 | `authorized` | — |
| Network/5xx | `unknown` (not unauthorized) | guard each probe independently |
| Booking health ignores auth | `unknown` for booking | document; resolve Q1 |
| Key authorized for none | all `unauthorized` | connection still saves; surface result |

### Security Considerations

- [x] Probes are read-only; never create shipments.
- [x] apikey reused from the connection; no new secret. (Note: PostNord puts apikey in the query string and SDK tracing persists it — pre-existing.)

---

## Implementation Plan

### Phase 1: Connector-local probe

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| `validate_credentials` proxy method (parallel/sequential per-product GET probes) | `mappers/postnord/proxy.py` | Pending | M |
| Probe request builders + `parse_validate_credentials_response` (classify via error.py) | `providers/postnord/validation.py` (new) | Pending | M |
| Resolve Q1 (Booking probe) | live test against sandbox | Pending | S |
| Tests (authorized/unauthorized/unknown per product; assert no `/edi/labels` POST) | `tests/postnord/test_validation.py` | Pending | M |

### Phase 2 (optional): Server + dashboard

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| `POST /v1/connections/{id}/check` (or GraphQL mutation) calling `validate_credentials` if present | `modules/core/karrio/server/providers/...`, `modules/graph/...` | Pending | L |
| "Test connection" button + per-product display | `apps/dashboard/...` | Pending | M |

**Dependencies:** Phase 2 depends on Phase 1.

---

## Testing Strategy

> `unittest` only. Mock `karrio.mappers.postnord.proxy.lib.request` per product to return 200 / a 403 gateway envelope / raise, and assert the classified per-product map. Assert no probe issues a `POST` to `/rest/shipment/v3/edi/labels`.

```python
def test_validate_credentials_per_product(self):
    # transit 403, service points 200, tracking 200 -> mixed authorization map.
    with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
        mock.side_effect = _per_url_responses({
            "/transittime/": AUTH_403,
            "/servicepoints/": "{}",
            "/tracking/": "{}",
        })
        result = validation.parse_validate_credentials_response(
            gateway.proxy.validate_credentials(req), gateway.settings
        )
    self.assertEqual(result[0]["transit"], "unauthorized")
    self.assertEqual(result[0]["service_points"], "authorized")
```

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| No clean Booking auth probe (Q1) | Booking status `unknown` | Medium | Live-test the health endpoint; else document the limitation |
| Probe latency (4 GETs) | Slow "test connection" | Low | Run probes concurrently; it's an on-demand action |
| False `unauthorized` on transient error | Misleading | Low | Map only 403 to `unauthorized`; everything else `unknown` |

---

## Migration & Rollback

### Backward Compatibility

- Purely additive: a new proxy method + provider module; no existing op changes, no models/migrations.
- Rollback: drop `validation.py` and the `validate_credentials` method.
