# PostNord Recipient-Country Locale Conformance

## Table of Contents

- [Executive Summary](#executive-summary)
- [Decisions](#decisions)
- [Problem Statement](#problem-statement)
- [Goals & Success Criteria](#goals--success-criteria)
- [Technical Design](#technical-design)
- [Edge Cases & Failure Modes](#edge-cases--failure-modes)
- [Implementation Plan](#implementation-plan)
- [Testing Strategy](#testing-strategy)
- [Migration & Rollback](#migration--rollback)

## Executive Summary

This PRD specifies an opt-in locale default derived from the recipient's country for PostNord shipments.
When enabled per connection, a shipment whose explicit `options.language` and connection `config.language` are both unset resolves its locale from `recipient.country_code` via a Nordic mapping (`SE→sv`, `DK→da`, `NO→no`, `FI→fi`), falling back to `en` for everything else.

The derived locale follows the same path the locale-continuity branch established: it reaches the booking `locale` query param (SMS/Email language) and the body `language` element (label text), and it is persisted into the purchase-created tracker's `options.language` so scheduled polls keep it.

### Scope

In scope: postnord connector (`modules/connectors/postnord/`), purchase-time tracker creation in manager serializers.

Out of scope: changing precedence for explicitly set locales, non-PostNord carriers, dashboard UI, the karrio-native notification pipeline.

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| C1 | Country mapping fills the *default* slot only: `request options.language` > `config.language` > country-derived > `"en"` | An explicitly assigned locale always wins; the mapping replaces the hardcoded `en` fallback, not caller intent |
| C2 | The derived locale applies at booking AND is persisted into the tracker at purchase | Without persistence, scheduled polls revert to `en` — the exact gap the locale-continuity branch closed |
| C3 | Enabled by a connection-config flag: `config.locale_by_recipient` (bool, default `false`) | One toggle per merchant connection; no per-shipment payload change; opt-in so existing behavior is untouched |
| C4 | `recipient.country_code` is the source of truth | Confirmed during design; the party the shipment is delivered to determines the language of its notifications |
| C5 | Mapping table: `SE→sv`, `DK→da`, `NO→no`, `FI→fi`; all other countries → `en` | PostNord's five supported locales minus `en` itself; `AX` (Åland) is Swedish-speaking but left out of v1 pending a call on coverage |
| C6 | Implementation in `units.py` as a `CountryLocale` lookup beside the existing enums, not inline in `create.py` | Keeps the mapping testable and next to `ConnectionConfig` |

Note the country-code trap this decision record exists partly to prevent: `DK` (Denmark's country code) maps to `da` (the Danish language).
`DA` is not a country code; `SV`, `NO`, `FI` are likewise language codes, not country codes.
Any code that conflates the two will silently fall through to `en` for every Nordic shipment.

## Problem Statement

Today the locale chain ends at a hardcoded `"en"`.
A merchant shipping from anywhere into Sweden, Denmark, Norway, or Finland gets English SMS/Email notifications, English label text elements, and English tracking events unless every request or the connection explicitly sets a language.
The merchant's external locale-assignment solution handles the explicit case; the implicit "match the destination" case has no support.

### Current State

```python
# modules/connectors/postnord/karrio/providers/postnord/shipment/create.py
locale = (
    (payload.options or {}).get("language")
    or settings.connection_config.language.state
    or "en"
)
```

## Goals & Success Criteria

### Goals

1. A Nordic recipient receives carrier notifications, label text, and tracking in their country's language when no explicit locale is set and the connection opts in.
2. Explicit locales are never overridden by the mapping.
3. The derived locale persists into the tracker so the entire lifecycle (booking → polls → event text) stays in one language.
4. Connections that do not opt in see byte-identical behavior to today.

### Success Criteria

1. `options.language=da` on a shipment to Sweden still yields `da` (explicit wins).
2. No options, no `config.language`, flag on, recipient in `SE` → booking `locale=sv`, body `language=SV`, tracker `options.language=sv`.
3. Flag off → `locale=en` regardless of recipient (current behavior).
4. All postnord, manager, and events suites pass; new tests cover each precedence tier.

## Technical Design

### Locale Resolution Chain

```text
┌──────────────────────────────────────────────────────────────┐
│                    shipment purchase                          │
│                                                              │
│  1. options.language ──────────────────────────── set? ──▶ it│
│  2. config.language ───────────────────────────── set? ──▶ it│
│  3. config.locale_by_recipient = true AND                    │
│     recipient.country_code ∈ {SE, DK, NO, FI} ──▶ mapped     │
│  4. otherwise ──────────────────────────────────────▶ "en"   │
│                                                              │
│  resolved locale                                             │
│    ├──▶ booking ?locale=xx        (SMS/Email language)       │
│    ├──▶ body language=XX          (label text)               │
│    └──▶ tracker options.language  (scheduled polls)          │
└──────────────────────────────────────────────────────────────┘
```

### Existing Code Analysis

What is reused from the locale-continuity branch (`postnord-locale-continuity`, commits 0c1caad03..bcf59d83f):

- `create.py` locale resolution block (shown above) gains one tier; the ctx threading into the proxy and the body `language` element are unchanged.
- `create_shipment_tracker` in `modules/manager/karrio/server/manager/serializers/shipment.py` already persists `shipment.options.language` into the tracker. The country-derived locale must be folded into the *shipment's effective options* before that point (see Implementation Plan), so the existing inheritance code needs no change.
- `ConnectionConfig` in `units.py` gains the `locale_by_recipient` flag beside `language`.
- The poller needs no change: it reads the persisted flat key.

### Key design point: where the derivation runs

The tracker persists `shipment.options.get("language")`, so the country-derived locale must be materialized onto the shipment's effective options during purchase, not computed independently in two places.
The clean seam is the purchase path in the manager serializer (`buy_shipment_label`), where the shipment, its options, and the carrier connection are all in hand: when the flag is on and no explicit language exists, set `options.language = CountryLocale[recipient.country_code]` before the request is built and the tracker is created.
The connector's `create.py` then sees an ordinary `options.language` and needs no knowledge of country codes.

An alternative — resolving the country inside the connector only — was rejected because the tracker would never learn the derived locale and polls would revert to `en` (violates C2).

### Data Models

No schema migration.
`Shipper/recipient.country_code` is existing address data; `options.language` is an existing free-form key; `locale_by_recipient` is a new `ConnectionConfig` option (connection credentials JSON, no column).

## Edge Cases & Failure Modes

| Scenario | Expected behavior |
|----------|-------------------|
| Recipient country not in the mapping (e.g. `DE`, `US`, `AX`) | `en` — mapping miss falls to the default |
| `recipient.country_code` missing or empty | `en` — no source of truth to read |
| Both `config.language` and the flag set | `config.language` wins (tier 2 before tier 3) |
| Explicit `options.language` that PostNord rejects (e.g. `de`) | Passed through, as today; unchanged behavior |
| Flag on, shipment later re-booked to a different destination | Locale re-derives at each purchase from that purchase's recipient; caveat: a failed purchase that already materialized `options.language` pins the stale value on retries until the option is cleared |
| Lowercase country code (`se`) | Normalized via `.upper()` before lookup |

## Implementation Plan

Implemented on branch `postnord-country-locale` (stacked on `postnord-locale-continuity`).

| # | Task | Files | Status |
|---|------|-------|--------|
| 1 | `CountryLocale` mapping + `locale_by_recipient` `OptionEnum`; connector country tier | `modules/connectors/postnord/karrio/providers/postnord/units.py`, `shipment/create.py` | Done (557749c) |
| 2 | Derive `options.language` at purchase when flag on and unset | `modules/manager/karrio/server/manager/serializers/shipment.py` (`_recipient_country_locale` + `buy_shipment_label`) | Done (fedc482) |
| 3 | Connector tests: flag on/off × mapped/unmapped country, explicit/config wins | `modules/connectors/postnord/tests/postnord/` | Done (e04f1c1) |
| 4 | Manager test: purchase with Nordic recipient persists derived locale into tracker | `modules/manager/karrio/server/manager/tests/test_shipments.py` | Done (e04f1c1) |

Dependencies: requires the `postnord-locale-continuity` branch (tracker inheritance and booking locale threading) to land first — satisfied by the stack.

Implementation note (task 2): the purchase-path derivation also skips when `config.language` is set.
Materializing `options.language` would otherwise promote the country tier above `config.language` in the connector chain, violating precedence rule C1.
The manager test suite exercises derivation through the real server gateway (`CarrierConnection` with `config=dict(locale_by_recipient=True)`), covering the flag's transport from connection credentials JSON to `settings.connection_config`.

## Verification

| Date | Suite | Result |
|---|---|---|
| 2026-09-03 | postnord connector (`python -m unittest discover -f modules/connectors/postnord/tests`) | 49/49 OK |
| 2026-09-04 | postnord connector (re-verified after rebase onto develop + country-locale) | 56/56 OK |
| 2026-09-03 | manager shipments (`karrio test karrio.server.manager.tests.test_shipments`) | 45/45 OK |
| 2026-09-03 | manager trackers (`karrio test karrio.server.manager.tests.test_trackers`) | 6/6 OK |
| 2026-09-04 | events tracking tasks (`karrio test karrio.server.events.tests.test_tracking_tasks`) | 9/9 OK (fresh-context review gate) |

## Testing Strategy

| Test | Assertion |
|------|-----------|
| explicit `options.language` + Nordic recipient + flag on | explicit value used end to end |
| no options, flag on, `SE` recipient | booking `locale=sv`, body `language=SV` |
| no options, flag on, `DE` recipient | `locale=en` |
| flag off, `SE` recipient | `locale=en` (today's behavior) |
| purchase with flag on, `DK` recipient | tracker `options.language == "da"` |
| `config.language=sv` + flag on + `NO` recipient | `sv` (config tier wins over country tier) |

## Migration & Rollback

Opt-in flag, default off: existing connections are unaffected until an operator enables it.
Rollback is reverting the commits; no data written by the feature needs unwinding (options keys are additive).
