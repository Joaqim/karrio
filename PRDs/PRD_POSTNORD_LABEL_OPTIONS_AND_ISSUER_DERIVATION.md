# PostNord label options and issuer derivation

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-07-27 |
| Status | Draft |
| Owner | PostNord connector |
| Type | Enhancement |
| Reference | [PRD_POSTNORD_INTEGRATION.md](./PRD_POSTNORD_INTEGRATION.md) (D3, D9), [AGENTS.md](../AGENTS.md) |

---

## Executive Summary

This PRD scopes two related PostNord connector enhancements against the vendored `vendor/booking.swagger.json`.
The first replaces the user-facing `issuer_code` setting (today an optional string defaulting to `"Z12"`) with a value derived from the shipment origin country, and rejects non-Nordic origins with a clear error because PostNord domestic serves only SE/DK/NO/FI.
The second honors the unified `payload.label_type` (PDF/ZPL) — which PostNord selects by *endpoint path*, not a body field — and adds an enum-constrained per-connection `label_size` option carrying PostNord's physical-size `labelType` query parameter (`standard`/`small`/`ste`).

Both features are SDK-connector-only, touching `modules/connectors/postnord/`; no core, Django, or GraphQL change is required.
The generated files `karrio/mappers/postnord/mapper.py` and `karrio/schemas/postnord/*` are off-limits to this work.

### Key Architecture Decisions

1. **Origin-derived issuer (D12)**: `issuerCode` is computed from `payload.shipper.country_code` via `{SE: Z12, DK: Z11, NO: Z13, FI: Z14}`, dropping `issuer_code` as a settings field. Both consignor and consignee receive the same origin-bound issuer, matching today's single-value behavior.
2. **Non-Nordic origin rejected (D13)**: a non-SE/DK/NO/FI origin raises a clear carrier error at request-build time, pointing users to PostNord International — no silent Z12/ZDL fallback.
3. **Label file format via `payload.label_type` (D14)**: PDF/ZPL is resolved (`payload.label_type` → connection `label_type` default → PDF) and threaded through `Serializable.ctx`; the proxy routes to `/v3/edi/labels/pdf` vs `/v3/edi/labels/zpl` accordingly.
4. **Enum-constrained label size (D15)**: a new `label_size` connection option (`standard`/`small`/`ste`, default `standard`) is validated by Karrio and sent as the PostNord `labelType` query parameter; the dead `label_format` option is retired.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| Derive `issuerCode` from origin country; drop `issuer_code` setting (D12) | Per-party (mixed) issuer codes — issuer stays origin-bound and single-valued |
| Reject non-Nordic origins with a clear error (D13) | PostNord International routing / non-Nordic origin support |
| Honor `payload.label_type` (PDF/ZPL) via endpoint routing (D14) | Two-step label retrieval (`/v3/labels/ids/*`); SVG/QR label formats |
| Enum-constrained `label_size` → `labelType` query param (D15) | PDF-only `paperSize` (A4/A5/A6/LETTER/LABEL) exposure — deferred future item |
| Retire dead `label_format` connection option (D15) | Any core/Django/GraphQL/dashboard change |
| Wire the dead `LabelType` enum live (D14) | Edits to `mapper.py` or `karrio/schemas/postnord/*` (generated) |

---

## Open Questions & Decisions

### Pending Questions

None open.
Q1 (pickup issuer origin) is resolved below.

### Resolved Decisions

These mirror the D-item format of `PRD_POSTNORD_INTEGRATION.md`; D11 is that document's current highest, so this PRD introduces D12–D16.

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| Q1 | Pickup path origin for issuer derivation (D12) and the non-Nordic guard (D13) | Derive from `payload.address.country_code` (the collection-location country); the D13 guard also keys on it | `pickup/create.py` has no `payload.shipper`; `pickup_request` builds from `payload.address` (the collection location), mapped to both `consignor.party` and `pickupParty.party` (`pickup/create.py:77,95-112,150`). The collection-location country is the natural origin analog — a Swedish collection derives `Z12`. The consignor `issuerCode` (`pickup/create.py:139`) is the *only* issuer injection site in the pickup path (`PickupPartyType` carries no issuer), so pickup has one issuer site, not two. The D13 non-Nordic reject also applies to pickups, keyed on the same `payload.address.country_code`. | 2026-07-27 |
| D12 | `issuerCode` source | Derive from origin country via `{SE: Z12, DK: Z11, NO: Z13, FI: Z14}`; drop `issuer_code` as a settings field. Origin is `payload.shipper.country_code` on shipment-create and `payload.address.country_code` on pickup-create | `issuer_code` is a hand-entered setting defaulting to `"Z12"` (`utils.py:24`, `settings.py:18`) injected onto both parties (`shipment/create.py:125`) and the pickup consignor (`pickup/create.py:139`). The issuer is the agreement/market code, which is origin-bound, so deriving it from origin removes a redundant, error-prone field. Scope covers both paths: shipment-create derives from `payload.shipper.country_code` and injects the same origin-derived issuer onto *both* consignor and consignee (two sites), preserving today's single-value behavior; pickup-create derives from `payload.address.country_code` (the collection location) and injects at its *single* issuer site — the consignor `issuerCode` at `pickup/create.py:139` — because `PickupPartyType` carries no issuer (pickup has one site, not two). The existing `IssuerCode` enum (`utils.py:5-12`) maps code→country-*name* (the inverse of what is needed) and is inverted/replaced to map country_code→issuer code. | 2026-07-27 |
| D13 | Non-Nordic origin | Reject with a clear carrier error at request-build time, on both paths | PostNord (domestic, not PostNord International) supports only Nordic origins (SE/DK/NO/FI). An origin outside that set has no valid issuer, so the connector raises an explicit validation error pointing users to PostNord International rather than silently defaulting to Z12/ZDL and booking against the wrong market. The guard keys on `payload.shipper.country_code` for shipment-create and on `payload.address.country_code` for pickup-create (per Q1). The allow-list is a single shared `NORDIC_ORIGIN_COUNTRIES` constant used by both guards (see D16 for the mechanism/membership rationale). | 2026-07-27 |
| D14 | Label file format | Honor unified `payload.label_type` (PDF/ZPL, default PDF) via endpoint routing, threaded through `Serializable.ctx` | Format is hardwired to PDF today (`proxy.py:104` always POSTs `/v3/edi/labels/pdf`); `payload.label_type` is not read. The swagger's `/v3/edi/labels/pdf` and `/v3/edi/labels/zpl` take the identical `ediInstruction` body and return the identical `ediLabelResponse` — format is selected by *endpoint path*. The dead `LabelType` enum (`units.py:23-31`) is wired live. Resolution order: `payload.label_type` → connection `label_type` default (existing `OptionEnum` default `"PDF"`) → PDF. Mirrors SEKO's precedent (`seko/.../shipment/create.py:120-122` reads `payload.label_type` via `LabelType.map(...)` and threads format via `Serializable.ctx`); PostNord already uses `ctx` for `shipment_id` (`shipment/create.py:223`). | 2026-07-27 |
| D15 | Label physical size | New enum-constrained `label_size` connection option (`standard`/`small`/`ste`, default `standard`) sent as the `labelType` query param; retire dead `label_format` | The swagger `labelType` *query* parameter documents `standard` (190×105mm), `small` (75×105mm), and `ste` (190×105mm, special alignment; PDF endpoint only — the ZPL endpoint omits it); unset defaults to `standard`. Karrio validates `label_size` against these tokens (the user rejected a free-form field) and passes it through the proxy `_url(path, **params)` helper, which already drops `None` values (`proxy.py:90-100`). `102x192mm` (the motivating example) *is* the `standard` label, so the default requires zero configuration for the common case. The connector's two dead `ConnectionConfig` options (`units.py:10-11`) are resolved: `label_type` becomes live as the per-connection default file format (D14); `label_format` (intended for the PDF-only `paperSize` enum) has no consumer and is retired. `paperSize` exposure is a deferred future item, not part of this PRD. | 2026-07-27 |
| D16 | Pickup-origin allow-list mechanism (refines D13) | Fixed shared Nordic constant `SE/DK/NO/FI`, identical membership to the shipment-origin set; a single `NORDIC_ORIGIN_COUNTRIES` set backs BOTH guards (DRY). No per-connection `pickup_countries` option is added | The pickup-allowed origin set is *not* a documented closed set in the vendored specs. The `/v3/pickups` endpoint the connector calls (`proxy.py:137`) says availability varies by pickup/consignor country and package type but enumerates nothing; `general-descriptions.pdf` defers availability to per-country price lists/fact sheets and notes pickup fields apply "only if stated in the agreement." The only hard list — `SE/DK/FI` (Norway excluded) — is on the sibling `/v3/pickups/ids` endpoint, which the connector does *not* call, so it is a documentary counter-signal, not an adopted constraint. A fixed shared constant is chosen over a per-connection `pickup_countries` option for simplicity: both the shipment guard (keyed on `payload.shipper.country_code`) and the pickup guard (keyed on `payload.address.country_code`) reference the one `NORDIC_ORIGIN_COUNTRIES` set rather than duplicating the literal; membership is a one-line code change if PostNord's per-country pickup offering later diverges. Pickup remains a separate concept in code but shares this constant. | 2026-07-27 |

### Naming-collision note

Karrio's unified `payload.label_type` means **file format** (PDF/ZPL).
PostNord's API `labelType` query parameter means **physical size token** (`standard`/`small`/`ste`).
The same word denotes two different concepts.
The new connection option is therefore named `label_size` — not `label_type` — to avoid the collision; the connection `label_type` option remains the per-connection *file-format* default (D14).

### Edge Cases Requiring Input

| Edge Case | Impact | Proposed Handling | Needs Input? |
|-----------|--------|-------------------|--------------|
| Pickup path origin for issuer/guard | Pickup has no `payload.shipper` | Use `payload.address.country_code` (Q1 resolved) | ❌ No (resolved) |
| `payload.shipper.country_code` (or pickup `payload.address.country_code`) missing/None | No derivable issuer | Treat as a non-Nordic origin → D13 clear error (None ∉ {SE,DK,NO,FI}) | ❌ No |
| `label_size=ste` with `payload.label_type=ZPL` | `ste` is PDF-only | Send `labelType=ste`; PostNord ignores/defaults it on the ZPL endpoint; document the interaction | ❌ No |

---

## Problem Statement

### Current State

```python
# utils.py:24 / settings.py:18 — issuer is a hand-entered setting defaulting to Z12.
issuer_code: str = "Z12"

# shipment/create.py:124-125 — the setting is injected onto BOTH parties, unconditionally.
def _party(address, *, with_consignor_id: bool) -> postnord_req.ConsignType:
    return postnord_req.ConsignType(
        issuerCode=settings.issuer_code,   # same value on consignor and consignee
        ...
    )

# proxy.py:102-104 — file format is hardwired to PDF; payload.label_type is never read.
def create_shipment(self, request):
    response = lib.request(
        url=self._url("/rest/shipment/v3/edi/labels/pdf"),  # always PDF
        ...
    )

# units.py:10-11 — two dead ConnectionConfig options; neither is consumed today.
label_type = lib.OptionEnum("label_type", str, "PDF")
label_format = lib.OptionEnum("label_format", str, "A4")
```

### Desired State

```python
# utils.py — issuer derived from origin country; the setting is gone.
class IssuerCode(lib.Enum):
    """Maps a Nordic origin country_code to its PostNord issuer code."""
    SE = "Z12"
    DK = "Z11"
    NO = "Z13"
    FI = "Z14"

# shipment/create.py — derive once from origin; non-Nordic origin rejected (D13).
issuer = _issuer_for_origin(shipper.country_code)  # raises on non-Nordic origin
# both parties receive the origin-derived issuer:
consignor=_party(shipper, issuer=issuer, with_consignor_id=True)
consignee=_party(recipient, issuer=issuer, with_consignor_id=False)

# proxy.py — format chosen from ctx; endpoint routes pdf vs zpl; label_size query param.
label_path = "/rest/shipment/v3/edi/labels/zpl" if ctx.get("label_type") == "ZPL" \
    else "/rest/shipment/v3/edi/labels/pdf"
url = self._url(label_path, labelType=self.settings.connection_config.label_size.state)
```

### Problems

1. **Redundant, error-prone issuer setting**: `issuer_code` is manually entered and defaults to Swedish `Z12` regardless of the actual origin, so a Danish or Norwegian shipment silently books against the Swedish market unless the operator remembers to set it.
2. **No format choice**: label format is hardwired to PDF; a ZPL-native warehouse cannot get a ZPL label even though PostNord exposes the identical booking at `/v3/edi/labels/zpl`.
3. **No size choice + dead config**: PostNord's `standard`/`small`/`ste` sizes are unreachable, and two dead `ConnectionConfig` options (`label_type`, `label_format`) sit unused, one of which is a misleading duplicate of the unified `payload.label_type` name.

---

## Goals & Success Criteria

### Goals

1. Derive `issuerCode` from the origin country and remove the `issuer_code` setting, with a clear error for non-Nordic origins.
2. Honor `payload.label_type` (PDF/ZPL) by routing to the matching PostNord label endpoint.
3. Expose an enum-constrained `label_size` and pass it as PostNord's `labelType` query param, retiring the dead `label_format` option.

### Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Issuer derived correctly for each of SE/DK/NO/FI | Verified by test | Must-have |
| Non-Nordic origin raises the expected error | Verified by test | Must-have |
| `payload.label_type=ZPL` hits `/v3/edi/labels/zpl`; default hits `/labels/pdf` | Verified by test | Must-have |
| `label_size=small` emits `labelType=small`; default `standard` behavior | Verified by test | Must-have |
| SDK suite regressions | 0 | Must-have |

### Launch Criteria

**Must-have (P0):**
- [ ] `issuer_code` removed from settings; issuer derived from origin (D12)
- [ ] Non-Nordic origin guard (D13) with a clear error message
- [ ] `payload.label_type` PDF/ZPL routing via `ctx` (D14)
- [ ] `label_size` enum option → `labelType` query param; `label_format` retired (D15)
- [ ] `python -m unittest discover -v -f modules/connectors/postnord/tests` passes
- [ ] `./bin/run-sdk-tests` passes

**Nice-to-have (P1):**
- [ ] README documents `label_type`/`label_size` and origin-derived issuer
- [ ] `paperSize` exposure captured as a deferred future item

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Derive issuer from origin (D12) | Removes redundant field; correct market by construction | Breaking config change (drops `issuer_code`) | **Selected** |
| Keep `issuer_code` setting | No config break | Error-prone Z12 default; duplicates origin | Rejected |
| Non-Nordic → error (D13) | Honest; no wrong-market bookings | Rejects at build time | **Selected** |
| Non-Nordic → Z12/ZDL fallback | "Just works" | Silent wrong-market booking; masks misuse | Rejected |
| Route pdf/zpl by endpoint path via `ctx` (D14) | Matches swagger (format = path); mirrors SEKO precedent | Threads a second `ctx` key | **Selected** |
| Body/query field for format | One endpoint | Not how PostNord's API works — format is the path | Rejected |
| Enum-constrained `label_size` (D15) | Validated; rejects typos | Must maintain the token set | **Selected** |
| Free-form `label_size` string | No enum maintenance | User explicitly rejected free-form | Rejected |
| Pickup-origin gate: fixed shared constant (D16) | DRY — one `NORDIC_ORIGIN_COUNTRIES` set backs both guards; simplest | Membership is code, not config | **Selected** |
| Pickup-origin gate: per-connection `pickup_countries` option | Honors agreement-specific pickup setup | Extra config surface; membership not documented as a closed set anyway | Rejected |
| Pickup-origin gate: passthrough (no pickup guard) | No gate to maintain | Lets non-Nordic collections through with no valid issuer | Rejected |
| Pickup membership `SE/DK/FI` (Norway excluded) | Matches the `/v3/pickups/ids` hard list | That list is a *different* endpoint the connector never calls | Rejected (counter-signal noted) |
| Pickup membership `SE/DK/NO/FI` | Identical to the shipment-origin set; one shared constant | May over-permit if `/v3/pickups` truly excludes NO in practice (see Risk) | **Selected** |

### Trade-off Analysis

Deriving the issuer from origin (D12) trades a one-time breaking config change for structural correctness: the market code can no longer disagree with the shipment's origin.
Rejecting non-Nordic origins (D13) is chosen over a silent fallback because a wrong-market booking is worse than a clear, actionable error that points to PostNord International.
Routing PDF/ZPL by endpoint path (D14) follows the swagger faithfully — the two endpoints share the body and response, differing only in path — and reuses the connector's existing `ctx` threading rather than inventing a new mechanism.
The enum constraint on `label_size` (D15) matches the user's explicit rejection of a free-form field and lets Karrio reject typos before they reach PostNord.

---

## Technical Design

> Studied before designing: `utils.py` (`IssuerCode` enum + `Settings`), `settings.py` (`issuer_code` field), `units.py` (`ConnectionConfig`, `LabelType`), `shipment/create.py` (`_party`, `shipment_request`, `ctx`), `pickup/create.py` (consignor issuer site), `proxy.py` (`_url`, `create_shipment`), and the SEKO precedent (`seko/.../shipment/create.py`). Facts confirmed against `vendor/booking.swagger.json`.

### Existing Code Analysis

| Component | Location | Reuse / Change |
|-----------|----------|----------------|
| `IssuerCode` enum (code→country-name) | `providers/postnord/utils.py:5-12` | Invert/replace to map country_code→issuer code (D12) |
| `issuer_code` field (provider settings) | `providers/postnord/utils.py:24` | Remove (D12) |
| `issuer_code` field (mapper settings) | `mappers/postnord/settings.py:18` | Remove (D12) |
| `_party(..., issuerCode=settings.issuer_code)` | `providers/postnord/shipment/create.py:124-126` | Pass origin-derived issuer to both parties (D12) |
| Origin address already in scope | `providers/postnord/shipment/create.py:105` (`shipper = lib.to_address(payload.shipper)`) | Source of `country_code` for derivation + guard (D12/D13) |
| Consignor issuer site (pickup) | `providers/postnord/pickup/create.py:139` | Origin source is Q1 (pickup has no `payload.shipper`) |
| `LabelType` enum (dead) | `providers/postnord/units.py:23-31` | Wire live for PDF/ZPL resolution (D14) |
| `ConnectionConfig.label_type` (dead) | `providers/postnord/units.py:10` | Becomes the per-connection default file format (D14) |
| `ConnectionConfig.label_format` (dead) | `providers/postnord/units.py:11` | Retire — no consumer (D15) |
| Hardwired PDF endpoint | `mappers/postnord/proxy.py:102-111` | Route pdf/zpl from `ctx`; add `labelType` query param (D14/D15) |
| `_url(path, **params)` (drops `None`) | `mappers/postnord/proxy.py:90-100` | Carries `labelType=<label_size>` (D15) |
| `Serializable.ctx` threading (`shipment_id`) | `providers/postnord/shipment/create.py:223`, `proxy.py:111` | Add resolved `label_type` to the same ctx (D14) |
| SEKO `payload.label_type` + `ctx` precedent | `seko/karrio/providers/seko/shipment/create.py:120-122` | Canonical pattern for format resolution + ctx threading |
| README settings/config tables | `modules/connectors/postnord/README.md:28,50,54-61` | Remove `issuer_code`; document `label_type`/`label_size` |
| Fixture settings | `tests/postnord/fixture.py:11` | Drop `issuer_code` |

### Architecture Overview

```
┌──────────────┐     ┌───────────────────────┐     ┌────────────────────────────┐
│  Unified     │     │   PostNord provider    │     │   PostNord proxy (apikey)  │
│  Shipment    │────>│  shipment_request      │────>│   create_shipment          │
│  Request     │     │                        │     │                            │
└──────────────┘     │  ┌──────────────────┐  │     │  ┌──────────────────────┐  │
                     │  │ origin issuer    │  │     │  │ ctx.label_type ──►    │  │
                     │  │ (D12) + guard    │  │     │  │  /labels/pdf | /zpl   │  │
                     │  │ (D13)            │  │     │  │  ?labelType=<size>    │  │
                     │  └──────────────────┘  │     │  └──────────────────────┘  │
                     │  ┌──────────────────┐  │     └────────────────────────────┘
                     │  │ resolve format   │  │                  │
                     │  │ (D14) ──► ctx    │──┼──────────────────┘
                     │  └──────────────────┘  │      label_size (D15) from
                     └───────────────────────┘      connection_config
```

### Sequence Diagram

```
┌────────┐   ┌──────────┐   ┌──────────┐        ┌──────────┐
│ Client │   │ provider │   │  proxy   │        │ PostNord │
└───┬────┘   └────┬─────┘   └────┬─────┘        └────┬─────┘
    │ Shipment.create            │                   │
    │────────────>│              │                   │
    │             │ derive issuer (origin) [D12]     │
    │             │ guard non-Nordic [D13]           │
    │             │ resolve label_type -> ctx [D14]  │
    │             │─────────────>│                   │
    │             │              │ pick endpoint:    │
    │             │              │  ctx.label_type   │
    │             │              │  == "ZPL" ?       │
    │             │              │   /labels/zpl     │
    │             │              │   : /labels/pdf   │
    │             │              │ +?labelType=<size>│
    │             │              │──────────────────>│
    │             │              │  ediLabelResponse │
    │             │              │<──────────────────│
    │             │ parse_shipment_response          │
    │             │<─────────────│                   │
    │ ShipmentDetails (label_type from response)     │
    │<────────────│              │                   │
```

### Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                   ISSUER DERIVATION (D12/D13)                     │
├──────────────────────────────────────────────────────────────────┤
│  payload.shipper.country_code                                     │
│         │                                                         │
│         ▼                                                         │
│  IssuerCode.map(country_code)  ── not in {SE,DK,NO,FI} ─► ERROR   │
│         │                                          (D13)          │
│         ▼                                                         │
│  issuer  ──►  consignor.issuerCode  AND  consignee.issuerCode     │
│              (single origin-bound value on both parties)          │
├──────────────────────────────────────────────────────────────────┤
│                   LABEL FORMAT + SIZE (D14/D15)                   │
├──────────────────────────────────────────────────────────────────┤
│  payload.label_type ─► connection label_type ─► "PDF"            │
│         │  (LabelType.map, default)                              │
│         ▼                                                         │
│  ctx["label_type"] ("PDF"|"ZPL")                                 │
│         │                                                         │
│         ▼   proxy                                                 │
│  path = /v3/edi/labels/{pdf|zpl}                                 │
│  query labelType = connection label_size ("standard"|"small"|    │
│                    "ste")   [dropped if None by _url]            │
└──────────────────────────────────────────────────────────────────┘
```

A single shared `NORDIC_ORIGIN_COUNTRIES` set (`{SE, DK, NO, FI}`, defined once in `units.py`/`utils.py`) backs both non-Nordic guards (D13/D16), keyed on `payload.shipper.country_code` for shipment-create and `payload.address.country_code` for pickup-create — the membership literal is not duplicated across the two call sites (DRY).
No `pickup_countries` config option is introduced (D16): `ConnectionConfig` gains only `label_size` (D15), `label_type` becomes live as the file-format default (D14), and `label_format` is retired (D15), unchanged from the D14/D15 scope.

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `payload.shipper.country_code` | string | Yes | Origin; drives issuer (D12) and the Nordic guard (D13). Must be SE/DK/NO/FI |
| `payload.label_type` | string | No | Unified file format PDF/ZPL; default PDF (D14) |
| `label_type` (connection config) | enum(PDF/ZPL) | No | Per-connection default file format; default `PDF` (D14) |
| `label_size` (connection config) | enum(standard/small/ste) | No | PostNord physical size → `labelType` query param; default `standard` (D15) |
| `issuer_code` (setting) | — | — | Removed (D12) |
| `label_format` (connection config) | — | — | Retired, no consumer (D15) |

### Issuer map (D12)

| Origin `country_code` | PostNord `issuerCode` | Market |
|-----------------------|-----------------------|--------|
| `SE` | `Z12` | Sweden |
| `DK` | `Z11` | Denmark |
| `NO` | `Z13` | Norway |
| `FI` | `Z14` | Finland |
| any other / missing | — | Rejected with a clear error (D13) |

### Label endpoint + size matrix (D14/D15)

| `payload.label_type` (resolved) | Endpoint path | `labelType` query values | Notes |
|---------------------------------|---------------|--------------------------|-------|
| PDF (default) | `/rest/shipment/v3/edi/labels/pdf` | `standard`, `small`, `ste` | `ste` valid only here |
| ZPL | `/rest/shipment/v3/edi/labels/zpl` | `standard`, `small` | `ste` sent but ignored/defaulted by PostNord |

Both endpoints take the identical `ediInstruction` body and return the identical `ediLabelResponse`; format is selected by the path, size by the `labelType` query parameter (unset ⇒ PostNord defaults to `standard`).

---

## Edge Cases & Failure Modes

### Edge Cases

| Scenario | Expected Behavior | Handling |
|----------|-------------------|----------|
| Shipment origin SE/DK/NO/FI | Correct issuer on both parties | `IssuerCode.map(shipper.country_code)` (D12) |
| Pickup collection SE/DK/NO/FI | Correct issuer on the single consignor site | `IssuerCode.map(address.country_code)` (D12, `pickup/create.py:139`) |
| Origin non-Nordic (e.g. `US`) — shipment or pickup | Clear error, no booking | D13 guard raises at request-build time on both paths |
| `payload.shipper.country_code` missing/None (shipment) | Clear error (None ∉ Nordic set) | Same D13 path |
| `payload.address.country_code` missing/None (pickup) | Clear error (None ∉ Nordic set) | Same D13 path, keyed on the collection address |
| `payload.label_type` unset | PDF label | Resolution falls through to connection default → PDF (D14) |
| `payload.label_type=ZPL` | ZPL label from `/labels/zpl` | `ctx["label_type"]="ZPL"` routes the endpoint (D14) |
| `label_size` unset | `standard` label | `_url` drops `None`; PostNord defaults to `standard` (D15) |
| `label_size=ste` with ZPL | `labelType=ste` sent; PostNord defaults to `standard` | `ste` is PDF-only; documented (D15) |
| Invalid `label_size` token | Rejected before request | Enum-constrained option (D15) |

### Failure Modes

| What Can Go Wrong | Impact | Mitigation |
|-------------------|--------|------------|
| Existing connection still carries `issuer_code` | Field silently ignored (unknown setting) | Behavior becomes origin-derived; documented as a breaking config change |
| Operator expects non-Nordic origin to "just work" | Error instead of a booking | Error message names PostNord International as the path |
| `label_format` still referenced somewhere | Import/attr error | Confirm no consumer before removal (only `enable_transit_times` is read, `proxy.py:36`) |

---

## Implementation Plan

### Phase 1: Issuer derivation (D12/D13)

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Invert/replace `IssuerCode` to country_code→issuer; define the single shared `NORDIC_ORIGIN_COUNTRIES` set (D16); add a small derivation+guard helper reading that set | `providers/postnord/utils.py` (or `units.py`) | Pending | S |
| Remove `issuer_code` field | `providers/postnord/utils.py`, `mappers/postnord/settings.py` | Pending | S |
| Derive issuer from `shipper.country_code`; pass to both parties; add non-Nordic guard referencing the shared `NORDIC_ORIGIN_COUNTRIES` | `providers/postnord/shipment/create.py` | Pending | M |
| Replace the `settings.issuer_code` injection at `pickup/create.py:139` with the address-derived issuer (`payload.address.country_code`); add the non-Nordic guard on `payload.address.country_code`, referencing the SAME shared `NORDIC_ORIGIN_COUNTRIES` (no `pickup_countries` config option) | `providers/postnord/pickup/create.py` | Pending | S |
| Drop `issuer_code` from fixture | `tests/postnord/fixture.py` | Pending | S |

### Phase 2: Label format + size (D14/D15)

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Wire `LabelType` live; resolve `payload.label_type` → connection `label_type` → PDF; thread via `ctx` | `providers/postnord/shipment/create.py`, `providers/postnord/units.py` | Pending | M |
| Add `label_size` enum-constrained `ConnectionConfig` option; retire `label_format` | `providers/postnord/units.py` | Pending | S |
| Route `/labels/pdf` vs `/labels/zpl` from `ctx`; add `labelType=<label_size>` query param | `mappers/postnord/proxy.py` | Pending | M |

### Phase 3: Docs & tests

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Remove `issuer_code`; document `label_type`/`label_size`; note origin-derived issuer | `README.md` | Pending | S |
| Tests: shipper-origin issuer per SE/DK/NO/FI; non-Nordic error; pdf/zpl routing; `label_size` query | `tests/postnord/test_shipment.py` | Pending | M |
| Tests: collection-address issuer per SE/DK/NO/FI; non-Nordic collection error | `tests/postnord/test_pickup.py` | Pending | S |

**Dependencies:** Phase 3 depends on Phases 1–2.

---

## Testing Strategy

> `unittest` only (never pytest), run from repo root after `source bin/activate-env`, following the connector 4-method pattern. `test_create_shipment` in `tests/postnord/test_shipment.py` already asserts the proxy URL by exact-match against `f"{gateway.settings.server_url}/rest/shipment/v3/edi/labels/pdf?apikey=TEST_API_KEY"` (`test_shipment.py:59-62`); the new endpoint/query assertions follow that same `mock.call_args[1]["url"]` style.

### Test Categories

| Category | Location | Coverage Target |
|----------|----------|-----------------|
| Shipment tests | `modules/connectors/postnord/tests/postnord/test_shipment.py` | Shipper-origin issuer, guard, format routing, size |
| Pickup tests | `modules/connectors/postnord/tests/postnord/test_pickup.py` | Collection-address issuer, guard |
| SDK regression | `./bin/run-sdk-tests` | No regressions |

### Test Cases

- Issuer derived correctly for each origin: `SE→Z12`, `DK→Z11`, `NO→Z13`, `FI→Z14`, asserted on both `consignor.issuerCode` and `consignee.issuerCode` in the serialized request (extends `test_create_shipment_request`).
- Non-Nordic origin (e.g. `US`) raises the expected clear error at request build (parsed to a `Message` on the shipment parse path, or asserted via `assertRaises` at `create_shipment_request`).
- `payload.label_type=ZPL` ⇒ `mock.call_args[1]["url"]` contains `/rest/shipment/v3/edi/labels/zpl`; default (unset) ⇒ contains `/rest/shipment/v3/edi/labels/pdf`.
- `label_size=small` ⇒ the request URL query contains `labelType=small`; default (`standard`, or unset) ⇒ no non-`standard` `labelType` override leaks (matching the `_url` `None`-drop behavior).

Pickup (`tests/postnord/test_pickup.py`), extending `test_create_pickup_request`:

- Pickup issuer derived from the collection-address country for each of `SE→Z12`, `DK→Z11`, `NO→Z13`, `FI→Z14`, asserted on the single `consignor.issuerCode` in the serialized pickup request.
- A non-Nordic collection address (e.g. `US`) is rejected with the same clear error at pickup request build.

```python
"""tests/postnord/test_shipment.py — extends the existing 4-method suite."""

import unittest
from unittest.mock import patch, ANY
import karrio.sdk as karrio
import karrio.lib as lib
from .fixture import gateway


class TestPostNordLabelOptions(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_create_shipment_zpl_routes_zpl_endpoint(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(ZplShipmentRequest).from_(gateway)
            self.assertIn("/rest/shipment/v3/edi/labels/zpl", mock.call_args[1]["url"])

    def test_create_shipment_defaults_pdf_endpoint(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(ShipmentRequest).from_(gateway)
            self.assertIn("/rest/shipment/v3/edi/labels/pdf", mock.call_args[1]["url"])

    def test_create_shipment_label_size_query(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            karrio.Shipment.create(ShipmentRequest).from_(gateway_small_label)
            self.assertIn("labelType=small", mock.call_args[1]["url"])
```

### Running Tests

```bash
# From repository root
source bin/activate-env

python -m unittest discover -v -f modules/connectors/postnord/tests
./bin/run-sdk-tests
```

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Dropping `issuer_code` breaks stored connections | Medium | High (by design) | Field silently ignored; behavior becomes origin-derived; documented breaking change |
| Non-Nordic origin now errors where it "worked" before | Medium | Low | Only ever booked wrong-market as Z12 before; error is more correct and actionable |
| `label_format` still referenced | Low | Low | Grep confirms only `enable_transit_times` is consumed (`proxy.py:36`); remove after check |
| `payload.label_type` / connection `label_type` name confusion | Low | Medium | Naming-collision note; `label_size` chosen for the physical-size option |
| PostNord may restrict `/v3/pickups` collections to SE/DK/FI (Norway excluded) in practice, per the sibling `/v3/pickups/ids` hard list | Low | Medium | Forward-looking only; the shared `NORDIC_ORIGIN_COUNTRIES` constant (D16) is a one-line change if confirmed — not a current guard change, since `/v3/pickups/ids` is a different endpoint the connector never calls |
| SDK suite regression | Medium | Low | Run `./bin/run-sdk-tests` before merge |

---

## Migration & Rollback

### Backward Compatibility

- **Config compatibility (D12, breaking)**: dropping `issuer_code` is a breaking config change. Existing stored connections that still carry `issuer_code` silently ignore the now-unknown field, and issuer behavior becomes origin-derived from `payload.shipper.country_code`. Connections whose origin matched their configured `issuer_code` (the common SE→Z12 case) are unaffected in output; connections that relied on an origin/issuer mismatch change behavior by design.
- **Config compatibility (D15, safe)**: retiring the dead `label_format` option removes a `ConnectionConfig` entry with no consumer, so no runtime behavior changes.
- **API compatibility**: additive within the connector — no core model, endpoint, or database change. `payload.label_type` is an existing unified field; the new `label_size` is an optional connection config with a `standard` default (zero-config for the common case).

### Rollback Procedure

1. **Identify issue**: errors isolated to `postnord` shipment create (issuer or label routing).
2. **Revert changes**: restore the `issuer_code` field and the hardwired PDF endpoint; re-add `label_format` if any external config depended on it.
3. **Verify recovery**: `python -m unittest discover -v -f modules/connectors/postnord/tests` and `./bin/run-sdk-tests` green; other carriers unaffected.

---

## Appendices

### Appendix A: Deferred future item

`paperSize` (the PDF-only page-size enum `A4`/`A5`/`A6`/`LETTER`/`LABEL`, present on the swagger label endpoints) is intentionally out of scope.
The dead `label_format` option originally hinted at it; that option is retired here (D15), and exposing `paperSize` as a validated connection option is left as a separate future enhancement.

### Appendix B: Generated files (off-limits)

The implementation this PRD describes must not edit `karrio/mappers/postnord/mapper.py` or any file under `karrio/schemas/postnord/` — these are auto-generated.
Schema changes, if ever needed, go through `schemas/*.json` + `./bin/run-generate-on modules/connectors/postnord`; none are required for D12–D16.
