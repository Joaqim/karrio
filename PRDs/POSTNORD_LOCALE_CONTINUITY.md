# PostNord Locale Continuity: Tracking Polls, Booking Language, and Notification Scope

## Table of Contents

- [Executive Summary](#executive-summary)
- [Open Questions & Decisions](#open-questions--decisions)
- [Problem Statement](#problem-statement)
- [Goals & Success Criteria](#goals--success-criteria)
- [Alternatives Considered](#alternatives-considered)
- [Technical Design](#technical-design)
- [Edge Cases & Failure Modes](#edge-cases--failure-modes)
- [Implementation Plan](#implementation-plan)
- [Testing Strategy](#testing-strategy)
- [Risk Assessment](#risk-assessment)
- [Migration & Rollback](#migration--rollback)
- [Appendices](#appendices)

## Executive Summary

`options.language` on tracking requests currently controls the display locale of a single PostNord Track & Trace fetch (event descriptions, status text) but is dropped at three lifecycle boundaries: (1) trackers created from shipments or from tracker-creation API calls persist only the response's options (which the PostNord parser never populates), so scheduled polls re-fetch with the default `en`; (2) the scheduled poller merges options across a 10-tracker batch with last-wins semantics, so even correctly-persisted per-tracker locale cannot be honored for mixed-locale batches; and (3) PostNord's booking endpoints accept a `locale` query parameter explicitly documented as the language of carrier-sent SMS/Email notifications, but shipment creation never sends it, so any carrier-side notifications default to Swedish.

This PRD specifies a three-layer fix: persist the request locale onto the tracker record, make poller batching locale-aware so each upstream request carries exactly one locale, and wire booking-time `locale` into the connector.

### Key Architecture Decisions

- **Per-tracker locale persistence on the `Tracking` model, in `options.language`** — reuses the shape karrio already uses for tracking options; no schema migration needed (options is a `PlainDictField`).
- **Locale-partitioned batching in the poller** — split each carrier batch by `options.language` before building the `TrackingRequest`, rather than switching to per-tracker HTTP requests (preserves the batching efficiency that motivated the design).
- **Booking locale sourced from shipment `options.language`** with a connection-config fallback (`config.language`) mirroring `label_type`'s config precedence (request > config > carrier default `sv`).
- **Notification additional-services explicitly out of scope for wiring** until the PostNord serviceguide is checked for which codes trigger SMS/Email; only the `locale` param is wired now. Rationale: the swagger describes `locale` unambiguously ("The SMS and Email is written in the defined language") but does not enumerate notification-triggering additionalServiceCodes.

### Scope

In scope: PostNord connector (`modules/connectors/postnord/`), tracking lifecycle in manager serializers, scheduled poller in events module, settings `ConnectionConfig`.

Out of scope: karrio-native notification/email/SMS pipeline (lives in `ee/platform`, inaccessible in this checkout — see Open Questions), dashboard UI for locale display, non-PostNord carriers (though the poller fix is carrier-agnostic in effect), label printout content language.

## Open Questions & Decisions

### Pending Questions

| # | Question | Impact if unresolved |
|---|----------|---------------------|
| Q1 | ~~Does the booking `locale` also affect label printout text, or only SMS/Email?~~ **Resolved during implementation**: label text is controlled by a separate body-level `language` element on `ShipmentRequestType` (swagger `definitions.language`: "the language in which the contents of text elements and code value text equivalents are written", 2 chars, example/default `EN`). Wired as the uppercase locale. Caveat: the description says "Use ISO 3166 two position alphabetic countrycode" but the example `EN` is not a country code — treated as uppercase ISO 639-1 (language) codes; verify against a live booking. | Implemented: query `locale` (SMS/Email) + body `language` (label text) both sent. |
| Q1b | Does track-and-trace `locale` affect only API response text, or also PostNord's own notification content sent to the end customer? Spec says: display language of the response. | If it affects carrier notifications, tracking-time locale matters beyond display; poller fix becomes customer-facing in a second sense. |
| Q1c | Which additionalServiceCode values trigger PostNord-side notifications (per product)? The serviceguide is the authority; the swagger does not enumerate them. | Without codes, karrio users cannot request PostNord-side notifications at all; locale param only is wired. |
| Q2 | ~~Canonical persistence shape~~ **Resolved**: flat key `options.language` alongside the keyed carrier entry; mapper and poller read the flat key. | Implemented. |
| Q2b | ~~Should tracker `options` survive tracker updates~~ **Resolved**: yes — the update path now carries persisted flat keys into the outgoing request, and the gateway echoes request options back into the persisted options. | Implemented. |
| Q3 | ~~Default language when none is set~~ **Resolved**: `en` everywhere (matches the track-and-trace spec default and the existing mapper fallback). Diverges from PostNord's documented booking default `sv`, accepted for developer consistency. | Implemented. |
| Q4 | The events poller is shared across all carriers. Is `language` a safe partition key given no other connector reads `options.language` today (per repo-wide grep)? | Partitioning on an unread key is inert for other carriers but establishes the pattern for future locale-aware connectors. Resolved by test: uniform batches produce one request. |

### Resolved Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Persist locale in tracker `options.language` (flat key) | Already the unified-model key the mapper reads; no migration; consistent with the ad-hoc fetch path. |
| D1b | Shipment-created trackers inherit `shipment.options.language` | Label purchase is the moment the merchant's locale assignment happens (external solution); inheritance preserves it into continuous tracking. |
| D2 | Locale-partitioned batches, not per-tracker requests | Preserves batch efficiency; PostNord applies one locale per request; mixed-locale batches otherwise degrade to last-wins. |
| D3 | Booking locale precedence: request `options.language` > connection `config.language` > PostNord default `sv` | Mirrors `label_type` precedence (request > config > default) established by the ZPL work. |
| D3b | Booking locale applies to all six booking endpoints | Spec defines `locale` on all six: `/v3/edi`, `/v3/edi/labels/zpl`, `/v3/edi/labels/pdf`, `/v3/returns/edi`, `/v3/returns/edi/labels/zpl`, `/v3/returns/edi/labels/pdf`. |
| D4 | `notifyParty` is out of scope | It is pickup paperwork semantics ("party to whom a notice of arrival must also be sent", `booking.swagger.json:6872`), not a notification trigger. |
| D5 | Locale enumeration shared by tracking and booking: `[en, sv, no, da, fi]` | Track-and-trace spec enumerates them explicitly; booking spec allows the same five values. |

### Edge Cases Requiring Input

| Scenario | Question |
|----------|----------|
| Tracker created via API with explicit `options: {"language": "sv"}`, then shipment purchased separately | Does the API-created tracker's explicit option win over shipment-inherited locale? |
| Shipment created with `options.language` but carrier lacks `get_tracking` capability | No tracker exists; locale never matters. Confirm no work needed. |
| PostNord rejects a locale value (e.g., `de`) | Does the API error or silently default? Affects upstream validation strictness. |
| Tracker options containing both `language` and the legacy keyed shape `{tn: {carrier: ...}}` | Merge semantics across shapes needs the canonical-form decision (Q2). |

## Problem Statement

### Current State

```python
# modules/events/karrio/server/events/task_definitions/base/tracking.py:218-226
options: dict = functools.reduce(
    lambda acc, t: {**acc, **(t.options or {})}, batch, {}
)

request = karrio.Tracking.fetch(
    datatypes.TrackingRequest(
        tracking_numbers=tracking_numbers, options=options
    )
)
```

```python
# modules/manager/karrio/server/manager/serializers/tracking.py:98
options=response.tracking.options,  # PostNord parser returns {} — locale lost
```

```python
# modules/manager/karrio/server/manager/serializers/shipment.py:974
options={shipment.tracking_number: dict(carrier=rate_provider)},  # keyed shape, no language
```

```python
# modules/connectors/postnord/karrio/providers/postnord/tracking.py:184
locale = (payload.options or {}).get("language") or "en"
```

```python
# modules/connectors/postnord/karrio/mappers/postnord/proxy.py:110 (create_shipment)
url=self._url(path),  # no locale param
```

### Desired State

```python
# Tracker persists the request's locale (merged over response options)
options=lib.to_dict(response.tracking.options) merged with request language

# Shipment-purchased trackers inherit the shipment's locale
options={
    shipment.tracking_number: dict(carrier=rate_provider),
    "language": shipment.options.get("language"),
}

# Poller partitions the batch by locale before building the request
for locale, group in group_by(batch, key=lambda t: (t.options or {}).get("language")):
    request = datatypes.TrackingRequest(
        tracking_numbers=[t.tracking_number for t in group],
        options={"language": locale} if locale else {},
    )
```

```python
# Mapper resolves booking locale with request > config > default precedence,
# threaded through Serializable.ctx into the proxy URL builder
locale = (
    (payload.options or {}).get("language")
    or settings.connection_config.language.state
    or "sv"
)
```

### Problems

1. **Locale dropped at persistence** — tracker stores response options (empty for PostNord) instead of request options; every scheduled poll thereafter uses `en`.
2. **Batch merge destroys per-tracker locale** — the reduce merges options dicts with last-wins semantics; mixed-locale batches cannot honor any tracker's locale, and even uniform batches only work if persistence is fixed first.
3. **Booking language never sent** — PostNord's documented SMS/Email language parameter is unused, so carrier-side notifications default to `sv` regardless of merchant intent.
4. **No notification additional-services** — `units.py` `ShippingOption` enum lists no notification codes; merchants cannot request PostNord-side notifications via karrio.
5. **Cross-layer default mismatch** — tracking defaults `en`, booking defaults `sv`; without a decision the localization story is internally inconsistent.

### Scope Matrix: where `options.language` applies today

| Scope | Language honored? | Evidence |
|---|---|---|
| Ad-hoc single fetch (POST /v1/track) | Yes | `tracking.py:184` |
| Tracker creation, first fetch | Yes | `serializers/tracking.py:61-73` |
| Scheduled polls (continuous tracking) | No — `en` fallback | `serializers/tracking.py:98` + parser never sets options |
| Shipment-purchased trackers | No | `shipment.py:974` keyed shape, no language |
| Label generation | No locale sent | proxy `create_shipment` builds URL without locale |
| PostNord-sent SMS/Email | Not wired | no notification codes in `units.py` |

## Goals & Success Criteria

### Goals

1. A locale assigned to `options.language` at shipment purchase (or tracker creation) is honored on every scheduled tracking poll for the life of the tracker.
2. A batch of trackers with mixed locales is fetched correctly per locale (partitioned requests), not last-wins merged.
3. PostNord booking requests carry a `locale` query parameter resolved via request > config > default precedence.
4. The external locale-assignment solution's authority extends from "single fetch" to the full lifecycle: purchase → tracker creation → continuous polls → persisted event text.
5. PostNord-side notification language becomes configurable at booking time.

### Success Criteria

1. A tracker whose `options.language = "sv"` shows Swedish event descriptions on poll N+1 without re-specifying the option.
2. A mixed batch (`sv` + `da` trackers) results in two `TrackingRequest`s, one per locale.
3. Booking request URLs contain the resolved `locale` on all six endpoints.
4. All existing postnord, manager, and events tests pass; new tests assert locale persistence, partitioning, and booking locale.

### Launch Criteria

- [ ] Q2 (options shape) resolved and implemented
- [ ] Q3 (default language) resolved and implemented
- [ ] PostNord developer docs checked for Q1/Q1b/Q1c — at minimum the check attempted and findings recorded
- [ ] All tests green; fresh-context review gate passed

## Alternatives Considered

### Alternative 1: Per-tracker HTTP requests in the poller

Drop batching; one request per tracker.

- Pros: locale trivially per-tracker; no partitioning logic.
- Cons: 10x request volume against PostNord; abandons the deliberate batching design (batch size 10, inter-batch delay); rate-limit exposure.

### Alternative 2: Locale stored in tracker `meta` instead of `options`

- Pros: avoids touching the options merge path entirely.
- Cons: `meta` already carries `carrier`/`request_id` and is response-derived; `options` is the request-semantics dict in the unified model, and the mapper already reads `options.language` — moving it to `meta` would fork the lookup.

### Alternative 3: Do nothing / accept `en` polls

- Pros: zero work.
- Cons: customer-facing event text in the wrong language; defeats the external locale-assignment solution's purpose for continuous tracking; default mismatch with booking (`sv`).

### Trade-off Analysis

The chosen design (persist + partition + booking param) keeps request volume unchanged, requires no schema migration, and reuses the unified `options.language` key end to end. Its cost is poller complexity (a group-by) and the open doc-verification items Q1/Q1b/Q1c.

## Technical Design

### Existing Code Analysis

What was studied and what is reused:

- `modules/connectors/postnord/karrio/providers/postnord/tracking.py` — `tracking_request` reads `options.language` (line 184) and emits `[{id, locale}]`; parse side never populates `TrackingDetails.options`. Reused as-is; the fix is upstream of it.
- `modules/connectors/postnord/karrio/mappers/postnord/proxy.py` — `_url(path, **params)` (line 90) already appends non-None params to the query string; `create_shipment` (line 102) threads `label_type` via `request.ctx` — the exact pattern `locale` will follow.
- `modules/connectors/postnord/karrio/providers/postnord/units.py` — `ConnectionConfig` (line 7) with `label_type`/`label_format` `OptionEnum`s establishes the config-field pattern; `shipping_options_initializer` (line 99) filters options to known `ShippingOption` codes, which is why `language` must ride the request ctx, not the options pipeline, for booking.
- `modules/events/karrio/server/events/task_definitions/base/tracking.py` — `process_carrier_trackers` batches by carrier (line 152); `_process_batch` merges options (line 218); `TRACKER_BATCH_SIZE = 10`.
- `modules/manager/karrio/server/manager/serializers/tracking.py` — `TrackingSerializer.create` (line 47) passes request options into the first `TrackingRequest` but persists `response.tracking.options` (line 98).
- `modules/manager/karrio/server/manager/serializers/shipment.py:943-995` — shipment-purchased tracker creation; options written in keyed shape (line 974).
- `modules/connectors/postnord/vendor/booking.swagger.json` — `locale` param on six endpoints (lines 397, 549, 827, and returns variants): "The SMS and Email is written in the defined language [sv | da | no | fi | en]", default `sv`.
- `modules/connectors/postnord/vendor/track-and-trace-v7-findbyidentifier.swagger.json:43-50` — `locale`: "Default is en. Allowed values are en, sv, no, da and fi".

### Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                            REQUEST PATHS                                │
│                                                                         │
│  ┌──────────────┐    options.language     ┌──────────────────────────┐  │
│  │ Merchant /   │────────────────────────▶│ Shipment purchase        │  │
│  │ external     │                         │ (manager/shipment.py)    │  │
│  │ locale       │                         │                          │  │
│  │ assignment   │                         │ 1. booking locale ───────┼──▶ POST /v3/edi/labels/{zpl,pdf}
│  └──────────────┘                         │    (NEW: ctx.locale)     │  │   ?locale=sv   ← SMS/Email language
│         │                                 │                          │  │
│         │                                 │ 2. tracker created with  │  │
│         ▼                                 │    options.language ─────┼──┐ (NEW: inherit)
│  ┌──────────────┐                         └──────────────────────────┘  │ │
│  │ Tracker      │    options.language                                   │ │
│  │ create API   │────────────────────────▶┌──────────────────────────┐ │ │
│  │ (manager/    │                         │ Tracking model           │◀┘
│  │  tracking.py)│                         │ options: {"language":sv} │
│  └──────────────┘                         │        (NEW: persist     │
│                                           │         request options) │
│                                           └────────────┬─────────────┘
│                                                        │
└────────────────────────────────────────────────────────┼────────────────┘
                                                         │
┌────────────────────────────────────────────────────────▼────────────────┐
│                          POLL PATH (Huey task)                           │
│                                                                          │
│  ┌────────────────────┐   group by options.language   ┌───────────────┐  │
│  │ Scheduled poller   │──────────────────────────────▶│ locale-group  │  │
│  │ (events/base/      │                               │ partitions    │  │
│  │  tracking.py)      │                               └───────┬───────┘  │
│  │                    │                                       │          │
│  │  batch of ≤10      │              one TrackingRequest per locale      │
│  │  trackers          │                                       ▼          │
│  │                    │                          GET /v7/trackandtrace   │
│  └────────────────────┘                              /{id}/public         │
│                                                      ?locale=sv           │
│                                                              │          │
│                                              persisted events, status,   │
│                                              estimated_delivery — all    │
│                                              in the tracker's locale     │
└──────────────────────────────────────────────────────────────────────────┘
```

### Sequence Diagram

```text
Merchant        Karrio API            PostNord
   │               │                      │
   │ buy label     │                      │
   │ opts.language=sv                    │
   ├──────────────▶│                      │
   │               │ resolve locale:      │
   │               │  req > config > sv   │
   │               ├─────────────────────▶│ POST /v3/edi/labels/pdf
   │               │                      │   ?locale=sv
   │               │◀─────────────────────┤ label + tracking_number
   │               │                      │
   │               │ create tracker       │
   │               │ options.language=sv  │
   │               │                      │
   │               │◀── poll cycle (Huey) │
   │               │ partition batch      │
   │               │  by locale           │
   │               ├─────────────────────▶│ GET /v7/trackandtrace/.../public
   │               │                      │   ?locale=sv
   │               │◀─────────────────────┤ events in Swedish
   │               │                      │
   │ track query   │                      │
   ├──────────────▶│                      │
   │◀──────────────┤ Swedish event text   │
```

### Data Flow Diagram

```text
  [shipment.options.language]     [tracker request options.language]
              │                                │
              ▼                                ▼
   (inherit at purchase)             (persist at create)
              │                                │
              └────────────┬───────────────────┘
                           ▼
              [Tracking.options = {"language": "sv"}]
                           │
                           ▼
              (poller: partition by language)
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
    [TrackingRequest           [TrackingRequest
     options={language:sv}]     options={language:da}]
              │                         │
              ▼                         ▼
    [?locale=sv responses]     [?locale=da responses]
              │                         │
              └────────────┬────────────┘
                           ▼
              [persisted events/status per tracker,
               each in its own locale]
```

### Data Models

No schema migration. `Tracking.options` is a `PlainDictField`; the change is to what gets written into it:

```python
# Canonical tracker options shape after this change (flat key alongside
# the existing keyed carrier entry written at purchase time):
{
    "<tracking_number>": {"carrier": "postnord"},  # existing keyed entry
    "language": "sv",                              # NEW: flat locale key
}
```

The mapper's `(t.options or {}).get("language")` reads the flat key; the keyed entry is untouched (it is not consumed by the poller merge today beyond pass-through).

### Field Mappings

| Karrio input | Resolved via | Carrier field | Endpoint | Spec wording |
|---|---|---|---|---|
| tracking `options.language` | direct | `locale` query | `GET /rest/shipment/v7/trackandtrace/id/{id}/public` | "Default is en. Allowed values are en, sv, no, da and fi" |
| shipment `options.language` | request > `config.language` > `sv` | `locale` query | `POST /rest/shipment/v3/edi/labels/pdf` | "The SMS and Email is written in the defined language [sv \| da \| no \| fi \| en]" |
| shipment `options.language` | same precedence | `locale` query | `POST /rest/shipment/v3/edi/labels/zpl` | same |
| shipment `options.language` | same precedence | `locale` query | `POST /rest/shipment/v3/edi` | same |
| `config.language` (new `ConnectionConfig` field) | — | — | — | connection-level default locale |

### API Changes

No karrio API surface changes. `options.language` on shipments and trackers is already accepted free-form via `PlainDictField`; this change makes the connector and lifecycle honor it.

## Edge Cases & Failure Modes

### Edge Cases

| Scenario | Expected Behavior | Handling |
|----------|-------------------|----------|
| Tracker with no `options.language` in a batch | Polled with locale unset → mapper default `en` | Partition key `None` forms its own group; no `language` key in options |
| Mixed-locale batch (`sv` + `da` + unset) | Three requests, one per partition | Group-by on the flat key |
| Locale value outside `[en, sv, no, da, fi]` (e.g., `de`) | Passed through; PostNord behavior unknown (Q-pending) | No client-side validation in v1; record finding from doc check |
| Shipment-purchased tracker whose shipment has no `options.language` | Keyed options entry only, as today | `shipment.options.get("language")` returns None → key omitted |
| Tracker update (PUT) that omits options | Locale must survive | Merge semantics per Q2b resolution; default to preserving existing keys |
| All ten trackers in a batch share one locale | One request, as today for uniform batches | Group-by degenerates to a single group |

### Failure Modes

| What Can Go Wrong | Impact | Mitigation |
|-------------------|--------|------------|
| Partitioning multiplies requests for fragmented locales (worst case 10 groups of 1) | More HTTP calls per poll cycle | Same order as unbatched worst case; inter-batch delay applies per carrier batch, not per partition; monitor request counts |
| Booking `locale` rejected by PostNord for a product where it does not apply | Shipment creation fails | `locale` is optional per spec; failure would indicate a spec/doc divergence — fall back to omitting the param on retry (documented, not automatic in v1) |
| Existing trackers in production already have `options: {}` | No locale until next explicit update; polls default `en` | Accepted; no data migration (backfill impossible — locale intent is not recoverable) |
| Other carriers' trackers pass through the same poller | Partition key inert (no other connector reads `options.language`); single group preserved | Group-by with uniform key produces one request — behavior identical to today |
| Poller exception mid-partition-loop | Partial batch saved | Existing per-batch try/except applies; partitions after the failure point are retried next cycle |

### Security Considerations

- [x] No new user-input surfaces; `options` remains a `PlainDictField` already validated by the serializer layer
- [x] Locale value flows only into a query parameter, never interpolated into URLs un-encoded (`_url` uses `to_query_string`)
- [x] No secrets involved; `locale` is non-sensitive display config

## Implementation Plan

All phases implemented on branch `postnord-locale-continuity`.

### Phase 1: Connector — booking locale (independent, shippable alone)

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Add `language` to `ConnectionConfig` | `modules/connectors/postnord/karrio/providers/postnord/units.py` | Done (1873f8c7d) | S |
| Add body `language` element to request schema + regenerate | `schemas/shipment_request.json` → `karrio/schemas/postnord/shipment_request.py` | Done (0c1caad03) | S |
| Resolve locale in `shipment_request`, thread via `Serializable.ctx`; body `language` uppercase | `modules/connectors/postnord/karrio/providers/postnord/shipment/create.py` | Done (1873f8c7d) | S |
| Append `locale` in `create_shipment` URL | `modules/connectors/postnord/karrio/mappers/postnord/proxy.py` | Done (1873f8c7d) | S |
| Tests: booking URL carries locale (request/config/default); body `language` present | `modules/connectors/postnord/tests/postnord/test_shipment.py` | Done | S |

### Phase 2: Persistence — locale onto trackers

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Carry persisted flat keys (incl. `language`) into update-path TrackingRequest | `modules/manager/karrio/server/manager/serializers/tracking.py` | Done (c1cfbc58b) | S |
| Inherit `shipment.options.language` into purchase-created tracker | `modules/manager/karrio/server/manager/serializers/shipment.py` | Done (c1cfbc58b) | S |
| API-created trackers persist request options | — | Already worked: the server gateway echoes request options into `response.tracking.options` (`modules/core/karrio/server/core/gateway.py:541-546`), which the create path persists | — |

### Phase 3: Poller — locale-partitioned batching

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Group each carrier batch by `options.language`; one `TrackingRequest` per group | `modules/events/karrio/server/events/task_definitions/base/tracking.py` | Done (721f7b625) | M |
| Tests: mixed batch → two requests; uniform batch → one | `modules/events/karrio/server/events/tests/test_tracking_tasks.py` | Done | M |

**Dependencies:** Phase 2 and Phase 3 are coupled (partitioning is pointless without persistence; persistence is invisible without partitioning). Phase 1 is independent. Landed in order 1 → 2 → 3, one commit each.

## Testing Strategy

### Unit Tests

| Test | File | Assertion |
|---|---|---|
| `test_create_shipment_request_locale` | `test_shipment.py` | URL contains `locale=sv` when `options.language=sv` |
| `test_create_shipment_request_locale_config_fallback` | `test_shipment.py` | `config.language=da` → `locale=da` when request omits it |
| `test_create_shipment_request_locale_default` | `test_shipment.py` | No language anywhere → `locale=sv` (PostNord default) |
| `test_create_shipment_request_locale_zpl` | `test_shipment.py` | ZPL endpoint URL also carries `locale` |
| `test_create_tracker_persists_request_language` | `test_trackers.py` | `tracker.options["language"] == "sv"` after create with options |
| `test_purchase_shipment_tracker_inherits_language` | `test_shipments.py` | Purchase with `options.language` → tracker has flat `language` key |
| `test_process_carrier_trackers_partitions_by_locale` | `test_tracking_tasks.py` | Mixed batch issues two fetches with distinct locale params |
| `test_process_carrier_trackers_uniform_locale` | `test_tracking_tasks.py` | Single fetch; behavior parity with today |

### Integration Tests

Follow-up poll (`test_trackers.py` style): tracker created with `language=sv`, simulate scheduler tick, assert the outgoing request URL had `locale=sv` (via fixture/gateway capture).

### Running Tests

```bash
source bin/activate-env
python -m unittest discover -v -f modules/connectors/postnord/tests
karrio test --failfast karrio.server.manager.tests.test_trackers
karrio test --failfast karrio.server.events.tests.test_tracking_tasks
```

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| PostNord rejects `locale` on booking in practice (spec/doc divergence) | Low | Medium | Phase 1 is isolated; revert is one commit |
| Partitioning changes request timing for other carriers | Low | Low | Uniform-key batches produce identical single-request behavior; covered by existing poller tests |
| Tracker options merge conflicts with keyed shape (Q2) | Medium | Medium | Flat key coexists with keyed entry; poller merge reads only the flat key |
| Locale silently wrong for existing trackers | Certain (accepted) | Low | No backfill possible; document that locale applies from next explicit update |

## Migration & Rollback

### Backward Compatibility

- No schema migration, no API surface change.
- Trackers without `language` behave exactly as today (`en` polls).
- Booking without any locale config sends `locale=sv` — a behavior change vs. today's omission, but matches PostNord's documented default; assess whether omitting when unset is preferable (ties to Q3).

### Data Migration

None. Locale intent is not recoverable for existing trackers; it applies from the next explicit shipment/tracker creation.

### Rollback Procedure

Each phase is one isolated commit range. Revert in reverse order (3 → 2 → 1). No data to unwind.

## Appendices

### Appendix A: PostNord locale parameters in vendor specs

| Spec | Endpoint(s) | Param | Default | Description (verbatim) |
|---|---|---|---|---|
| `track-and-trace-v7-findbyidentifier.swagger.json:43` | `GET /rest/shipment/v7/trackandtrace/id/{id}/public` | `locale` (query) | `en` | "Default is en. Allowed values are en, sv, no, da and fi" |
| `booking.swagger.json:397,549,827` | `POST /v3/edi`, `/v3/edi/labels/{zpl,pdf}`, `/v3/returns/edi*` | `locale` (query) | `sv` | "The SMS and Email is written in the defined language [sv \| da \| no \| fi \| en]" |

### Appendix B: Verification log

| Date | Check | Result |
|---|---|---|
| 2026-09-03 | Repo-wide grep for `options.language` consumers in connectors | PostNord only |
| 2026-09-03 | `ee/platform` submodule clone attempt | Inaccessible to both `Joaqim` SSH key and `gh` token; upstream `.gitmodules` unchanged — access gap, not a rename |
| 2026-09-03 | Booking spec enumeration of endpoints with `locale` | Six (incl. returns variants) |
| 2026-09-03 | Developer-portal check (portal is a JS shell; no static content fetchable) | In-repo swagger used as authority; found body `language` element answering Q1. Q1c (notification additionalServiceCodes) still needs the serviceguide. |
| 2026-09-03 | Test runs | postnord connector 44/44; manager trackers+shipments 48/48; events tracking tasks 8/8 |
