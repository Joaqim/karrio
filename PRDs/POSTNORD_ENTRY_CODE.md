# PostNord Entry Code: options.entry_code via Booking freeText ZDC

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-09-07 |
| Status | Implemented (review gate pending) |
| Owner | Joaqim Planstedt |
| Type | Integration |
| Reference | [AGENTS.md](../AGENTS.md) |

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

PostNord's Booking API has no dedicated entry-code field; the door code travels as a shipment-level `freeText` entry with usage code `ZDC`, which PostNord maps to the consignee reference (EDIFACT RFF) and prints as Ref 2 on the label.
This PRD adds a per-shipment string option, `options.entry_code`, that flows into that freeText slot at booking time, following the raw-read pattern already used by `options.language`.
PostNord publishes no per-service documentation for ZDC, so the option is an optional pass-through with no karrio-side verification of service or endpoint applicability; its potential usage is documented in the connector README.

### Key Architecture Decisions

1. **Surface: `options.entry_code` (string), read raw from `payload.options`** — mirrors `options.language` (`shipment/create.py:159-168`); it must not be a `ShippingOption` enum member because that channel serializes to `additionalServiceCode` (`create.py:145-151`), which is the wrong transport.
2. **Transport: `shipment[].freeText[] = {usageCode: "ZDC", text}`** — `FreeTextType` is already generated (`karrio/schemas/postnord/shipment_request.py:32`), so no schema regeneration is needed.
3. **50-character maximum** (user decision, 2026-09-07) — generous for door codes and within the practical limits of address lines and full names; the swagger itself allows 1000.
4. **No service gating, no endpoint verification** (user decision, 2026-09-07) — no PostNord documentation enumerates which services accept ZDC; karrio sends the freeText whenever the option is provided and PostNord governs acceptance.
5. **freeText built as a composable list** — the request builder assembles `freeText` entries functionally so future usage codes (e.g. `DEL` delivery instructions) can append without restructuring.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| `shipment/create.py` entry-code read, coercion, limit check, freeText wiring | `ShippingOption` / `additionalServiceCode` changes |
| `units.py` constants (usage code, max length) | Connection-config default (`config.entry_code`) |
| `test_shipment.py` create-request tests | Generic `options.instructions` → `DEL` freeText |
| Connector README documentation of `options.entry_code` | Rate path, proxy, settings, manager serializers |

## Open Questions & Decisions

### Pending Questions

None — all questions resolved.

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | Option surface | `options.entry_code`, per-shipment string | Matches the user's options-not-config channel; mirrors `options.language` handling | 2026-09-07 |
| D2 | API transport | `freeText` with `usageCode: "ZDC"` | Only value-carrying free-text mechanism in booking v3; printed as Ref 2 (see Appendix A) | 2026-09-07 |
| D3 | Maximum length | 50 characters | User decision; generous vs typical codes, within address/name limits; swagger allows 1000 | 2026-09-07 |
| D4 | Service/endpoint verification | None — optional pass-through, documented | No PostNord documentation enumerates ZDC-capable services; PostNord governs acceptance | 2026-09-07 |
| D5 | Type coercion | `str()` + `strip()` before send | `PlainDictField` does not enforce inner types; numeric codes (e.g. `1442`) must not raise (locale precedent, `create.py:156-158`) | 2026-09-07 |
| D6 | Over-limit behavior (Q1) | Reject: booking not sent, caller receives a message | User decision; a truncated door code is a wrong door code. Implemented via ctx flag + proxy short-circuit (see D6a), because raising from the request builder cannot produce a message — see Appendix A, SDK error-channel analysis | 2026-09-07 |
| D6a | Rejection mechanism | `create.py` sets a ctx flag; `proxy._create_shipment` skips the HTTP call and returns a synthesized PostNord fault body; the existing error parser turns it into a `Message`; the server's `shipment is None` path returns 424 with messages | Request building runs outside `@fail_safe` (`modules/sdk/karrio/api/interface.py:498-505`), so an exception would surface as an HTTP 500, not a carrier message. ctx-driven proxy branching is house pattern (canadapost `ctx["retrieve_shipments"]`, mydhl `is_paperless`); `error.py:35-41,60-91` already parses `compositeFault` bodies | 2026-09-07 |

### Edge Cases Requiring Input

None remaining.

## Problem Statement

### Current State

```python
# modules/connectors/postnord/karrio/providers/postnord/shipment/create.py:145-151
options = lib.to_shipping_options(
    payload.options,
    package_options=packages.options,
    initializer=provider_units.shipping_options_initializer,
)

additional_service_codes = [option.code for _, option in options.items()]
```

```python
# create.py:159-160 — the only raw option read; entry code has no equivalent
locale = str(
    (payload.options or {}).get("language")
    ...
)
```

```python
# create.py:220-276 — ShipmentType constructed without freeText;
# generated FreeTextType (shipment_request.py:32, fields :33-34) is unused
postnord_req.ShipmentType(
    shipmentIdentification=...,
    service=postnord_req.ServiceType(...),
    parties=...,
    goodsItem=[...],
)
```

No entry-code handling exists anywhere in the connector, PRDs, or notes (swept `entry`, `ingångskod`, `portkod`, `door`, `access`, `flexdelivery` — zero hits).

### Desired State

```python
entry_code = lib.identity(
    str((payload.options or {}).get("entry_code") or "").strip() or None
)

# Over limit: reject without sending (D6) — flag via ctx, omit freeText,
# and let the proxy short-circuit into a synthesized fault response.
entry_code_error = lib.identity(
    f"options.entry_code exceeds {provider_units.ENTRY_CODE_MAX_LENGTH} characters"
    if entry_code and len(entry_code) > provider_units.ENTRY_CODE_MAX_LENGTH
    else None
)

free_texts = lib.identity(
    [
        postnord_req.FreeTextType(
            usageCode=provider_units.ENTRY_CODE_USAGE_CODE,
            text=entry_code,
        ),
    ]
    if entry_code and not entry_code_error
    else None
)

return lib.Serializable(
    request,
    lib.to_dict,
    dict(
        shipment_id=shipment_id,
        label_type=label_type,
        locale=locale,
        entry_code_error=entry_code_error,
    ),
)
```

```python
# mappers/postnord/proxy.py — _create_shipment, before the HTTP call
if request.ctx.get("entry_code_error"):
    return lib.Deserializable(
        dict(
            compositeFault=dict(
                faults=[
                    dict(
                        faultCode="ENTRY_CODE_LENGTH",
                        explanationText=request.ctx["entry_code_error"],
                    )
                ]
            )
        )
    )
```

### Problems

1. **No path exists for an entry code**: a merchant's door code cannot reach PostNord, so the driver arrives without building access and the delivery fails or degrades to a pickup point.
2. **The only option channel is additionalServiceCode**: `ShippingOption` membership serializes to parameterless service codes, so the value needs the raw-read path `options.language` already established.
3. **Undocumented capability**: the ZDC mechanism exists in PostNord's PDF/guides but not in the swagger's usage-code list, so its potential usage must be documented for future maintainers.

## Goals & Success Criteria

### Goals

1. A merchant can pass `options.entry_code` on shipment creation and the value reaches PostNord as `freeText` ZDC, printed as Ref 2.
2. Requests without `options.entry_code` remain byte-identical to today's output.
3. Over-limit and non-string inputs behave deterministically per D3/D5/D6.
4. The option and its ZDC/Ref 2 semantics, including the no-verification caveat, are documented in the connector README.

### Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Create-request tests covering present/absent/coerced/over-limit | 4 passing tests | Must-have |
| Existing postnord suite | All pass, no regressions | Must-have |
| README documents `options.entry_code` | Merged section | Must-have |
| Absent-option request payload unchanged | assertDictEqual against existing fixture | Must-have |

### Launch Criteria

**Must-have (P0):**
- [ ] `options.entry_code` → `shipment[0].freeText[0] == {usageCode: "ZDC", text: <value>}`
- [ ] Over-limit rejection implemented per D6/D6a
- [ ] Full postnord connector suite green

**Nice-to-have (P1):**
- [ ] Live test-environment booking confirming Ref 2 printing (deferred; D4 makes this optional)

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| `freeText` ZDC (selected) | Only value-carrying mechanism; no schema changes; label Ref 2 per PostNord guides | Usage code absent from swagger's documented list | **Selected** |
| `additionalServiceCode` parameter | None | Codes are parameterless strings; cannot carry a value | Rejected |
| Dedicated API field | Direct | Does not exist in booking v3.5.29.1 (current published version) | Rejected |
| `options.instructions` → freeText `DEL` | General delivery instructions | Different semantics (driver instruction vs printed Ref 2 code); out of scope, future candidate | Deferred |
| `config.entry_code` connection default | Set-once convenience | Per-shipment value by nature (each recipient has a different code) | Rejected |

## Technical Design

### Existing Code Analysis

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| Raw option read | `providers/postnord/shipment/create.py:159-168` | Pattern for reading `payload.options` directly, incl. `str()` coercion rationale |
| `FreeTextType` | `karrio/schemas/postnord/shipment_request.py:32-34` | Already generated; `usageCode`/`text` fields; instantiate directly |
| `ShipmentType.freeText` slot | `shipment_request.py:170` | Populate during request assembly |
| Options → service codes | `create.py:145-151`, `units.py:163-175` | Explicitly not used; documents why entry_code bypasses this channel |
| `lib.identity` | `karrio.lib` | Conditional expression helper used throughout create.py |
| Booking proxy call | `mappers/postnord/proxy.py:108-119` | Unchanged; freeText is body-only, no query param |
| Locale test naming | `tests/postnord/test_shipment.py:142-240` | Template for `test_create_shipment_entry_code_*` tests |

### Option Channel Separation

```
                        payload.options
                              │
          ┌───────────────────┼─────────────────────────┐
          ▼                   ▼                         ▼
     "language"          "entry_code"           ShippingOption keys
     (raw read)          (raw read)             (to_shipping_options)
          │                   │                         │
          ▼                   ▼                         ▼
   query `locale`      shipment.freeText       service.additionalServiceCode
   + body language     [{usageCode: "ZDC",     ["A1", "A5", "65", ...]
   (SMS/Email +         text: "1442"}]
   label text)          (label "Ref 2")
```

### Architecture Overview

```
┌─────────────────────────────┐
│ karrio shipment request     │
│ options.entry_code: "1442"  │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────────────────────┐
│ providers/postnord/shipment/create.py       │
│ str() coercion, strip(), 50-char check      │
│ violation → ctx["entry_code_error"] flag    │
└──────────────┬──────────────────────────────┘
               ▼
┌─────────────────────────────────────────────┐
│ ShipmentRequestType.shipment[0].freeText =  │
│   [{usageCode: "ZDC", text: "1442"}]        │
└──────────────┬──────────────────────────────┘
               ▼
┌─────────────────────────────────────────────┐
│ mappers/postnord/proxy.py                   │
│ ctx flag → synthesized fault, no HTTP call  │
│ else POST /rest/shipment/v3/edi/labels/…    │
│ (body-only; no query-param or path change)  │
└──────────────┬──────────────────────────────┘
               ▼
┌─────────────────────────────────────────────┐
│ PostNord                                    │
│ EDIFACT RFF (consignee reference)           │
│ label: printed as "Ref 2"                   │
└─────────────────────────────────────────────┘
```

### Sequence Diagram

```
Client             create.py              Proxy                 PostNord
  │ options.entry_code │                    │                      │
  │───────────────────>│                    │                      │
  │                    │ coerce/strip/check │                      │
  │                    │ build freeText ZDC │                      │
  │                    │───────────────────>│ ediInstruction body  │
  │                    │                    │─────────────────────>│
  │                    │                    │   bookingResponse   │
  │                    │                    │<────────────────────│
  │                    │ parse label/ids    │                      │
  │<───────────────────│                    │                      │
```

### Field Reference

| Karrio field | PostNord field | Type | Required | Notes |
|--------------|----------------|------|----------|-------|
| `options.entry_code` | `shipment[].freeText[].text` | string | No | Stripped, coerced; max 50 chars (D3) |
| — (fixed) | `shipment[].freeText[].usageCode` | string | Yes | Constant `"ZDC"` (door code, consignee Ref 2) |
| absent | `freeText` omitted (`None`) | — | — | Request payload unchanged |

### API Changes

No karrio API surface changes; the unified `options` object already accepts arbitrary keys (`PlainDictField`).

**Outbound booking body (excerpt):**

```json
{
  "shipment": [{
    "service": {"basicServiceCode": "17", "additionalServiceCode": []},
    "freeText": [{"usageCode": "ZDC", "text": "1442"}],
    "parties": {"consignee": {"party": {"address": {...}}}}
  }]
}
```

## Edge Cases & Failure Modes

### Edge Cases

| Scenario | Expected Behavior | Handling |
|----------|-------------------|----------|
| Option absent | `freeText` omitted; payload byte-identical | `None` default |
| Empty or whitespace-only value | Treated as absent | `str(...).strip() or None` |
| Numeric value (e.g. `1442` as int) | Coerced to `"1442"`, sent | `str()` (D5) |
| Exactly 50 characters | Sent | Boundary inclusive |
| More than 50 characters | Booking not sent; `Message` (code `ENTRY_CODE_LENGTH`) returned; server responds 424 with messages | ctx flag + proxy short-circuit (D6/D6a) |
| Combined with `options.language` | Both applied; independent channels | Channel separation above |
| Service without ZDC support | Sent anyway; PostNord ignores or errors | D4 pass-through, documented |
| Non-ASCII characters | Sent as-is (swagger allows free text) | No karrio-side charset filter |

### Failure Modes

| What Can Go Wrong | Impact | Mitigation |
|-------------------|--------|------------|
| PostNord silently drops ZDC on an unsupported service | Label lacks Ref 2; driver without code | Accepted per D4; README documents caveat; P1 live check optional |
| PostNord rejects the booking due to freeText | Booking fails with carrier message | Existing `error.parse_error_response` surfaces it; no code path changes |
| Over-limit value silently truncated by us | Wrong code delivered | Avoided by design; D6 rejects before send |

## Implementation Plan

### Phase 1: Option wiring and documentation

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Add `ENTRY_CODE_USAGE_CODE = "ZDC"` and `ENTRY_CODE_MAX_LENGTH = 50` constants | `modules/connectors/postnord/karrio/providers/postnord/units.py` | Done | S |
| Read, coerce, check, and wire `entry_code` → `freeText`; flag over-limit via ctx | `modules/connectors/postnord/karrio/providers/postnord/shipment/create.py` | Done | S |
| Short-circuit `_create_shipment` on the ctx flag; return synthesized `compositeFault` body without HTTP | `modules/connectors/postnord/karrio/mappers/postnord/proxy.py` | Done | S |
| Six create-request tests (present, absent, coerced, at-limit, over-limit rejection, plus URL routing) | `modules/connectors/postnord/tests/postnord/test_shipment.py` | Done | S |
| Document `options.entry_code` usage and caveats | `modules/connectors/postnord/README.md` | Done | S |

Implementation note: an absent entry code passes `freeText=[]` rather than `None` — the `JList` converter wraps an explicit `None` into `[None]`, which survives `to_dict` as a bogus entry (plain `Optional[List[str]]` fields like `additionalServiceCode` do not have this behavior).

**Dependencies:** none — Q1 is resolved (D6/D6a).

## Testing Strategy

> All tests use `unittest` (never pytest), run from repository root, following the 4-method carrier pattern and the locale tests' inline-payload style.

### Test Cases

```python
def test_create_shipment_entry_code_request(self):
    """options.entry_code maps to freeText ZDC on the booking body."""
    payload = ShipmentPayloadWithOptions(options={"entry_code": "1442"})
    request = self.gateway.mapper.create_shipment_request(payload)

    self.assertDictEqual(
        lib.to_dict(request.serialized)["shipment"][0]["freeText"],
        [{"usageCode": "ZDC", "text": "1442"}],
    )

def test_create_shipment_entry_code_absent(self):
    """No option: freeText omitted, payload otherwise unchanged."""

def test_create_shipment_entry_code_coerced(self):
    """Numeric option value is stringified and sent."""

def test_create_shipment_entry_code_over_limit(self):
    """51-char value: proxy returns a synthesized fault without an HTTP call;
    parse yields Message(code="ENTRY_CODE_LENGTH") and no shipment details."""
```

### Running Tests

```bash
source bin/activate-env
python -m unittest discover -v -f modules/connectors/postnord/tests
./bin/run-sdk-tests   # pre-merge regression sweep
```

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| ZDC not honored on services merchants use | Medium | Medium | D4 pass-through plus README documentation; P1 live check |
| Swagger usage-code list omits ZDC (undocumented behavior) | Low | Certain (already true) | Appendix A evidence trail; PRD records provenance |
| Regression in existing create path | Medium | Low | Absent-option assertDictEqual against existing fixture; full suite |
| D6 semantics chosen wrong | Low | Low | Single build-time branch; trivially changeable |

## Migration & Rollback

### Backward Compatibility

- **API compatibility**: purely additive; the option is absent by default and `freeText` is omitted, leaving the outbound body unchanged.
- **Data compatibility**: no schema, migration, or persistence changes.
- **Feature flags**: none needed; absence is the off state.

### Rollback Procedure

1. Revert the single implementation commit.
2. Re-run the postnord connector suite.
3. No data cleanup required.

## Appendices

### Appendix A: ZDC Evidence Trail

| Source | Location | Statement |
|--------|----------|-----------|
| Booking swagger v3.5.29.1 | `vendor/booking.swagger.json:6261-6284` | `freeText` object: `usageCode` (free-form 3-char; documents DEL/ICN/INS/ZRE/ZTG/ZHD/ZOI/ZUL, not ZDC), `text` (1–1000) — "Text which may be written freely and without restrictions" |
| General descriptions PDF | `vendor/docs/general-descriptions.pdf` | "ZDC … Door code", "Used in RFF for Consignee" (EDIFACT consignee reference segment) |
| PostNord Customer API Guides | guide.developer.postnord.com | `freeText` with ZDC-consignee: "the Doorcode is printed as Ref 2" |
| Spec currency | developer.postnord.com | Published Booking APIs version is 3.5.29.1 — identical to the vendored spec |
| Service applicability | all of the above | No source enumerates which services accept ZDC; hence D4 |
| SDK error-channel analysis | `modules/sdk/karrio/api/interface.py:498-505` | `create_shipment_request` runs outside `@fail_safe` (only parse is guarded), so a raised exception cannot become a carrier `Message` — hence the ctx/proxy short-circuit in D6a |
| ctx-branching precedent | `canadapost` proxy (`ctx["retrieve_shipments"]`), `mydhl` proxy (`is_paperless`) | Reading `request.ctx` to alter proxy behavior is established house pattern |
| Server 424 path | `modules/core/karrio/server/core/gateway.py:309-317` | `shipment is None` + messages → `APIException` 424 with message detail — the rejection UX for D6 |

### Appendix B: README Documentation Text

```markdown
### options.entry_code (optional, string, max 50 characters)

PostNord entry code (door code) for the recipient's building, e.g. an
apartment entrance code. Sent as a shipment `freeText` with usage code
`ZDC`; PostNord prints it as "Ref 2" on the label and maps it to the
consignee reference. PostNord does not document which services accept
it: the value is passed through unverified and is ignored by services
without door-code support.
```

### Appendix C: Carrier-Specific Reference

**API Documentation:**
- Booking APIs 3.5.29.1 spec (vendored: `vendor/booking.swagger.json`)
- PostNord Customer API Guides: https://guide.developer.postnord.com/
- Booking API product page: https://www.postnord.se/en/partners-and-integrations/create-order/booking-api/

**Field Mappings:**

| Karrio Field | Carrier Field | Notes |
|--------------|---------------|-------|
| `options.entry_code` | `shipment[].freeText[].text` with `usageCode "ZDC"` | Printed as label Ref 2 |
| `options.language` | query `locale` + body `language` | Pre-existing (locale continuity work) |
