# Tracker Locale Persistence

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-09-24 |
| Status | Completed |
| Owner | Joaqim Planstedt |
| Type | Enhancement |
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
10. [Migration & Rollback](#migration--rollback)

---

## Executive Summary

`options.language` on a tracking request selects the language of carrier-provided event text, but only for the fetch that carries it.
The locale is lost at three lifecycle boundaries: shipment-purchased trackers never record it, tracker updates rebuild the request without it, and the scheduled poller merges options across a batch with last-wins semantics.
This change persists the locale on the tracker, carries it through every refresh, partitions poller batches by locale, and adds a carrier hook for deriving a purchase locale from the recipient address.

### Key Architecture Decisions

1. **Flat `options.language` key on `Tracking.options`**: the unified-model key connectors already read; `options` is a `PlainDictField`, so no migration.
2. **Locale-partitioned poller batches**: one `TrackingRequest` per distinct locale inside a carrier batch, keeping batching instead of per-tracker requests.
3. **`Settings.recipient_locale` hook**: carriers opt in to recipient-derived locales without carrier-specific code in the manager; the default returns `None`.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| Tracker locale persistence (purchase, create, update) | Connector-side locale handling (per carrier) |
| Locale-partitioned scheduled polling | Validating locale values against a carrier's allowed set |
| Carrier hook for a recipient-derived purchase locale | Backfilling locales for existing trackers |
| Draining tracer records between partition saves | Dashboard display of tracker locale |

---

## Open Questions & Decisions

### Resolved Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Persist the locale as a flat `language` key beside the keyed `{tracking_number: {...}}` entry | Connectors read the flat key; the keyed entry keeps its existing consumers (e.g. smartkargo prefix/air waybill). |
| D2 | Purchase-created trackers inherit `shipment.options.language` | Purchase is where the merchant's locale is assigned; inheritance carries it into continuous tracking. |
| D3 | Partition batches by locale rather than issuing per-tracker requests | A request carries one language; partitioning preserves the batch-of-10 design. |
| D4 | Explicit `options.language` outranks `recipient_locale`, which is not called when a language is set | The hook fills only the unset slot; explicit merchant intent always wins. |
| D5 | Coerce a non-string persisted `language` to a string partition key | `PlainDictField` does not enforce inner types; a `TypeError` in the partition sort would stall the batch. |

### Pending Questions

| # | Question | Impact if unresolved |
|---|----------|---------------------|
| Q1 | Should an API-created tracker's explicit locale win over a later shipment purchase with a different locale for the same tracking number? | The purchase-created tracker takes the shipment's locale; precedence between the two records is not defined by this change. |

---

## Problem Statement

### Current State

```python
# modules/manager/karrio/server/manager/serializers/shipment.py (create_shipment_tracker)
options={shipment.tracking_number: dict(carrier=rate_provider)},  # no language

# modules/events/karrio/server/events/task_definitions/base/tracking.py (_process_batch)
options: dict = functools.reduce(
    lambda acc, t: {**acc, **(t.options or {})}, batch, {}
)  # mixed locales collapse to the last tracker's language
```

### Problems

| Scope | Language honored before | After |
|-------|------------------------|-------|
| Ad-hoc fetch (`POST /v1/trackers` first fetch) | Yes | Yes |
| API-created tracker, scheduled polls | Only if batch is uniform | Yes |
| Shipment-purchased tracker | No | Yes |
| Tracker update (manual refresh) | No | Yes |
| Mixed-locale poller batch | Last-wins | One request per locale |

---

## Goals & Success Criteria

| Goal | Success criterion |
|------|-------------------|
| A tracker's locale survives its lifetime | A tracker with `options.language = "sv"` is polled with `language = "sv"` without re-specifying it |
| Mixed batches honor each locale | A batch with `sv` and `da` trackers issues two fetches, one per locale |
| No regression for locale-less carriers | A uniform or unset batch issues exactly one fetch, as before |
| Carriers can derive a locale at purchase | A carrier returning a locale from `recipient_locale` gets it on the shipment and its tracker |

---

## Alternatives Considered

| Alternative | Rejected because |
|-------------|------------------|
| Per-tracker poller requests | Up to 10x request volume; abandons batching and inter-batch delay. |
| Store the locale in tracker `meta` | `meta` is response-derived; connectors read request `options.language`, so the lookup would fork. |
| Carrier-name check in the manager for recipient-derived locales | Couples the carrier-neutral manager to one connector's config and units. |

---

## Technical Design

### Existing Code Analysis

| Location | Reuse |
|----------|-------|
| `modules/core/karrio/server/core/gateway.py` (`Shipments.track`) | Echoes request options into `response.tracking.options`, so API-created trackers already persist the request locale. |
| `modules/manager/.../serializers/tracking.py` (`TrackingSerializer.update`) | Builds the refresh request; extended to carry flat keys. |
| `modules/manager/.../serializers/shipment.py` (`create_shipment_tracker`, `buy_shipment_label`) | Tracker inheritance and the purchase-time hook call. |
| `modules/events/.../base/tracking.py` (`_process_batch`) | Batching by carrier retained; partitioning added inside each batch. |
| `modules/sdk/karrio/core/settings.py` (`Settings`) | Existing carrier-overridable surface (`tracking_url`, `connection_config`); the hook follows it. |

### Architecture Overview

```text
 purchase (buy_shipment_label)             tracker create / update
 ┌──────────────────────────────┐          ┌──────────────────────────┐
 │ options.language set?        │          │ request options.language │
 │  no → settings               │          │ (create: gateway echo;   │
 │   .recipient_locale(recip.)  │          │  update: flat keys kept) │
 │  → shipment.options.language │          └────────────┬─────────────┘
 └──────────────┬───────────────┘                       │
                │ inherit                               │ persist
                ▼                                       ▼
        ┌────────────────────────────────────────────────────┐
        │ Tracking.options = {"<tn>": {...}, "language": "sv"}│
        └──────────────────────────┬─────────────────────────┘
                                   │ scheduled poll
                                   ▼
        ┌────────────────────────────────────────────────────┐
        │ _process_batch: group by options.language          │
        │   "sv" → TrackingRequest(options.language="sv")    │
        │   "da" → TrackingRequest(options.language="da")    │
        │   ""   → TrackingRequest(no language)              │
        │ each partition fetched, traced, saved in turn      │
        └────────────────────────────────────────────────────┘
```

### Data Models

No schema change; `Tracking.options` gains a flat key:

```python
{
    "<tracking_number>": {"carrier": "<rate_provider>"},  # existing keyed entry
    "language": "sv",                                      # persisted locale
}
```

### API Changes

No REST or GraphQL surface change.
SDK: `Settings.recipient_locale(recipient: Optional[dict]) -> Optional[str]`, default `None`.
SDK: `Tracer.drain_records()` returns buffered records and clears the buffer; `bulk_save_tracing_records` uses it so per-partition saves do not duplicate records.

---

## Edge Cases & Failure Modes

| Scenario | Behavior |
|----------|----------|
| Tracker without `options.language` | Own partition with no `language` key; carrier default applies. |
| All trackers in a batch share a locale | One request, identical to prior behavior. |
| Non-string `language` (e.g. `5`) | Coerced to `"5"` for partitioning. |
| Locale value the carrier does not support | Passed through; the connector decides. |
| Fragmented locales (worst case 10 partitions of 1) | Up to 10 requests per batch, the per-tracker worst case; inter-batch delay still applies per batch. |
| Failure mid-batch | Partitions already saved are kept; the rest are retried next cycle. |
| Existing trackers without a locale | Unchanged until a new purchase or explicit tracker update supplies one. |

---

## Implementation Plan

| Change | Files |
|--------|-------|
| Drain tracer records on bulk save | `modules/sdk/karrio/core/utils/tracing.py`, `modules/core/karrio/server/tracing/utils.py` |
| Persist locale on purchase and update paths | `modules/manager/.../serializers/shipment.py`, `modules/manager/.../serializers/tracking.py` |
| Locale-partitioned poller | `modules/events/.../task_definitions/base/tracking.py` |
| Recipient-locale carrier hook | `modules/sdk/karrio/core/settings.py`, `modules/manager/.../serializers/shipment.py` |

---

## Testing Strategy

| Test | File |
|------|------|
| `TestTracerDrainRecords` (drain returns and clears; `records` does not drain) | `modules/sdk/tests/core/test_tracing.py` |
| `test_create_tracker_persists_request_language` | `modules/manager/.../tests/test_trackers.py` |
| `test_purchase_shipment_tracker_inherits_language` | `modules/manager/.../tests/test_shipments.py` |
| `test_purchase_shipment_locale_from_carrier_recipient_locale`, `test_purchase_shipment_explicit_language_skips_recipient_locale` | `modules/manager/.../tests/test_shipments.py` |
| Partitioning: mixed, uniform, keyed options kept, non-string coerced | `modules/events/.../tests/test_tracking_tasks.py` |

```bash
source bin/activate-env
python -m unittest discover -v -f modules/sdk/tests
karrio test --failfast karrio.server.manager.tests karrio.server.events.tests
```

---

## Migration & Rollback

No data migration; locale intent for existing trackers is not recoverable and applies from the next purchase or explicit update.
Trackers without a locale behave exactly as before.
Each change is an isolated commit and can be reverted in reverse order.
