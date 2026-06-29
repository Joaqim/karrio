# PostNord tracking events (Track & Trace v7)

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-06-29 |
| Status | Planning |
| Owner | PostNord connector |
| Type | Enhancement |
| Reference | [PRD_POSTNORD_INTEGRATION.md](./PRD_POSTNORD_INTEGRATION.md) (D7), [conformance-ralph-report.md](../docs/notes/postnord/conformance-ralph-report.md) |

---

## Executive Summary

Tracking is currently link-only (D7): `get_tracking` returns a tracking URL plus one generic `in_transit` status and no events, because the originally-supplied tracking API returns only a URL.
PostNord's Track & Trace v7 API returns full event history (timestamped events, locations, normalized statuses, signature), which would upgrade tracking to real events with a delivered status — closing the one literal carrier-integration DoD gap ("delivered + in-transit with events").
This PRD scopes that upgrade against the vendored `track-and-trace-v7-findbyreference.swagger.json`, whose central constraint is that it keys on **(customerNumber, reference)** while karrio tracks by the carrier-allocated **tracking_number (itemId)** — an identifier mismatch that must be resolved before implementation.

### Key Architecture Decisions

1. **Graceful capability, not a hard switch**: if the v7 product is not authorized for the key (PostNord authorizes per product — Transit Time already 403s for unsubscribed keys), tracking falls back to the current link-only behavior rather than failing.
2. **Status normalization in `units.TrackingStatus`**: map PostNord's 13-value `eventStatus` enum to karrio's `TrackerStatus`, replacing the placeholder enum.
3. **Identifier surface is a blocking decision (Q1)**: the vendored spec is *findByReference*; itemId-based tracking (karrio's default) needs either a findByIdentifier v7 spec or a deliberate "track by reference" model.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| Parse v7 events → `TrackingDetails.events` + normalized status + delivered flag | Webhook/push tracking (`callback` param) |
| Status mapping (`eventStatus` → `TrackerStatus`) | Multi-piece split-status reconciliation beyond a primary status |
| `signed_by` from `acceptor`/`signature`; estimated delivery | Tracking for non-PostNord-allocated references |
| Graceful fallback to link-only when v7 is unauthorized | Removing the link-only path entirely |
| Delivered + in-transit-with-events tests (closes DoD gap) | — |

---

## Open Questions & Decisions

### Pending Questions

| # | Question | Context | Options | Status |
|---|----------|---------|---------|--------|
| Q1 | How do we key the v7 call? | Vendored spec = `GET /v7/trackandtrace/customernumber/{customerNumber}/reference/{reference}/public`. karrio's `get_tracking` receives `tracking_number` (= the allocated **itemId**), not the client **reference**. `customerNumber` is in settings; `reference` is the `shipmentId` we set at booking (`payload.reference`). | A) Obtain the v7 **findByIdentifier/by-itemId** spec from PostNord (natural fit for tracking_number) — **recommended**; B) Track **by reference** (treat the tracking input as the client reference + settings `customer_number`) — works only when users track by their own reference, not our returned itemId; C) Hybrid: try itemId surface, fall back | ⏳ blocking — needs PostNord spec or product decision |
| Q2 | Is Track & Trace v7 a separately-authorized product? | Like Transit Time, the key may 403 on v7. | Live-validate; degrade to link-only on 401/403 | ⏳ live-test |
| Q3 | Exact `eventStatus` → `TrackerStatus` mapping | 13 PostNord values vs karrio's `TrackerStatus` set | See proposed mapping; confirm names against `karrio.core.units.TrackerStatus` | ⏳ confirm at impl |

### Edge Cases Requiring Input

| Edge Case | Impact | Proposed Handling | Needs Input? |
|-----------|--------|-------------------|--------------|
| v7 unauthorized (403) | No events | Fall back to current link-only result | ❌ (design) |
| Multi-piece `splitStatuses` | Ambiguous overall status | Use the shipment-level `status`; expose item statuses in events/meta | ◑ confirm |
| itemId not resolvable to a reference | Can't call findByReference | Resolve Q1 (A or B) | ✅ Yes (Q1) |

---

## Problem Statement

### Current State

```python
# tracking.py (link-only, D7): no events, always in_transit, never delivered.
def _extract_details(...):
    return models.TrackingDetails(
        ...,
        events=[],            # no events
        delivered=False,      # never delivered
        status="in_transit",  # single generic status
        meta=dict(tracking_url=...),
    )
```

### Desired State

```python
# v7: real events, normalized status, delivered flag, signature.
return models.TrackingDetails(
    tracking_number=item_id,
    events=[models.TrackingEvent(date=..., time=..., code=ev["eventCode"],
                                 description=ev["eventDescription"],
                                 location=ev["location"]) for ev in events],
    delivered=(status == "delivered"),
    status=TrackingStatus.map(event_status).name,
    meta=dict(tracking_url=..., signed_by=acceptor),
)
```

### Problems

1. **No event history / no delivered status** — the only literal carrier-integration DoD gap (D7).
2. **Single generic status** — `in_transit` regardless of reality.

---

## Goals & Success Criteria

### Goals
1. Return real tracking events and a normalized status (incl. `delivered`) from v7.
2. Degrade gracefully to link-only when v7 is unavailable/unauthorized.
3. Close the DoD "delivered + in-transit with events" test gap.

### Success Criteria
| Metric | Target | Priority |
|--------|--------|----------|
| Events parsed from a v7 response | Verified by test | Must-have |
| Delivered status detected | Verified by test | Must-have |
| Graceful fallback on 401/403 | Verified by test | Must-have |
| Q1 identifier surface resolved | Decided | Must-have (blocking) |

### Launch Criteria
**Must-have (P0):**
- [ ] Q1 resolved (spec or track-by-reference decision)
- [ ] v7 request + event/status parse
- [ ] `test_tracking.py`: delivered + in-transit-with-events + error/fallback

**Nice-to-have (P1):**
- [ ] `signed_by`, estimated delivery, location detail in events

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| v7 findByIdentifier (by itemId) | Matches karrio's tracking_number model | Spec not vendored; must obtain from PostNord | **Recommended (Q1-A)** |
| v7 findByReference (vendored) | Available now; rich events | Needs the client reference, not the allocated itemId — mismatched with how we return tracking numbers | Interim only (Q1-B) |
| Keep link-only (D7) | No work | Leaves the DoD gap | Rejected (this PRD) |

---

## Technical Design

> Studied: `tracking.py` (link-only), `units.TrackingStatus` (placeholder), `proxy.get_tracking`, `error.py` (gateway/auth envelope + graceful patterns), and `vendor/track-and-trace-v7-findbyreference.swagger.json`.

### Existing Code Analysis

| Component | Location | Reuse |
|-----------|----------|-------|
| Link-only tracking (fallback) | `providers/postnord/tracking.py` | Keep as the graceful-fallback path |
| Status enum (placeholder) | `providers/postnord/units.py` `TrackingStatus` | Expand to the v7 `eventStatus` mapping |
| Tracking proxy call | `mappers/postnord/proxy.py` `get_tracking` | Add the v7 path (gated/fallback) |
| Auth-error classification | `providers/postnord/error.py` (`_authorization_message`, gateway envelope) | Detect 401/403 → fall back |
| Transit graceful-degrade precedent | `proxy._get_transit_times` + `rate.py` | Same guard/fallback shape |

### API

`GET {server_url}/rest/shipment/v7/trackandtrace/customernumber/{customerNumber}/reference/{reference}/public?apikey=…&locale=…`

Response (relevant): `shipments[].items[].events[]` with `eventTime`, `eventCode`, `localEventCode`, `eventDescription`, `eventStatus`, `location`/`locationDetail`/`geoLocation`, `acceptor`, `signature`; item/shipment `status`, `statusText`, `splitStatuses`.

### Status mapping (proposed; confirm against `karrio.core.units.TrackerStatus`)

| PostNord `eventStatus` | karrio status |
|------------------------|---------------|
| `DELIVERED` | `delivered` |
| `EN_ROUTE`, `INFORMED`, `CREATED` | `in_transit` |
| `AVAILABLE_FOR_DELIVERY`, `AVAILABLE_FOR_DELIVERY_PAR_LOC` | `ready_for_pickup` |
| `DELAYED`, `EXPECTED_DELAY` | `delivery_delayed` |
| `DELIVERY_IMPOSSIBLE`, `DELIVERY_REFUSED` | `delivery_failed` |
| `RETURNED` | `return_to_sender` |
| `STOPPED` | `on_hold` |
| `OTHER` / unknown | `in_transit` (default) |

---

## Edge Cases & Failure Modes

| Scenario | Behavior | Handling |
|----------|----------|----------|
| v7 401/403 (unauthorized product) | Fall back to link-only | Detect via gateway envelope; reuse link-only `_extract_details` |
| No events yet | `in_transit`, empty events | Default status |
| Multi-piece split status | Use shipment-level status | item statuses in events/meta |
| Network/parse failure | Fall back to link-only | Guarded call |

---

## Implementation Plan

### Phase 0: Unblock
| Task | Status | Effort |
|------|--------|--------|
| Resolve Q1 (obtain findByIdentifier v7 spec OR decide track-by-reference) | Pending | — |
| Live-validate v7 authorization for the key (Q2) | Pending | S |

### Phase 1: Implement
| Task | Files | Effort |
|------|-------|--------|
| v7 request + response parse (events, status, delivered, signed_by) | `providers/postnord/tracking.py` | M |
| Expand `TrackingStatus` mapping | `providers/postnord/units.py` | S |
| Repoint/extend `get_tracking`; guard + fall back to link-only | `mappers/postnord/proxy.py` | M |
| Parse response as dict (no schema) or generate `tracking_response` types | `providers/postnord/tracking.py` (+ `schemas/` if generated) | S/M |
| Tests: delivered, in-transit-with-events, unauthorized→fallback | `tests/postnord/test_tracking.py` | M |

---

## Testing Strategy

> `unittest`, 4-method pattern. Mock `karrio.mappers.postnord.proxy.lib.request` with a v7 events body, a delivered body, and a 403 envelope (assert fallback to link-only).

```python
def test_parse_tracking_response_with_events(self):
    # delivered v7 body -> events populated, delivered=True, status="delivered".
    ...

def test_parse_tracking_response_unauthorized_falls_back(self):
    # 403 -> link-only result (tracking_url + generic status), no crash.
    ...
```

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| findByReference can't serve itemId tracking (Q1) | High | High | Obtain findByIdentifier spec; track-by-reference interim |
| v7 not authorized for the key (Q2) | Medium | Medium | Graceful fallback to link-only |
| Status mapping drift | Low | Medium | Confirm against `TrackerStatus`; default to `in_transit` |

---

## Migration & Rollback

- Additive: v7 path with link-only as the fallback; no API/model changes (TrackingDetails already supports events/status).
- Rollback: drop the v7 branch; `get_tracking` reverts to link-only.
- Closes the D7 DoD gap; update `PRD_POSTNORD_INTEGRATION.md` (D7) and the ralph report when shipped.
