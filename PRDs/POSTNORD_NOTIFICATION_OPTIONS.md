# PostNord Notification Options: Opt-in Consignee Notification Channels

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-09-07 |
| Status | Planning |
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

PostNord has no "do not notify" flag: consignee notifications are an opt-in menu of additionalServiceCodes — `A2` letter, `A3` SMS, `A4` e-mail, `A9` phone (voice), `B8` driver call — each bound to a contact slot on the consignee party.
This PRD makes those channels bookable per shipment via the Create Shipment API's `options` parameter, mapping karrio's existing unified `sms_notification`/`email_notification` options to `A3`/`A4` and adding carrier-scoped options for the channels without unified equivalents.
It also fixes a latent emission bug this work exposed: an explicitly `False` bool option currently still emits its `additionalServiceCode`, which would break opt-out semantics.

### Key Architecture Decisions

1. **Opt-in via the existing additionalServiceCode channel** — notification codes are plain `ShippingOption` bools serialized by the existing options machinery; no request-structure changes beyond a state check.
2. **Unified names where they exist** — `sms_notification` → `A3`, `email_notification` → `A4` (karrio core defines both, `modules/sdk/karrio/core/units.py:1206-1207`); carrier-scoped names for `A2`/`A9`/`B8`.
3. **Additive model, no cross-exclusion logic** — booking `A3` alone is SMS-only and excludes letter, e-mail, voice, and driver contact by construction; karrio enforces no mutual exclusion (user requirement: SMS is the least intrusive channel, chosen explicitly).
4. **Truthy-state emission fix** — `additionalServiceCode` entries are emitted only when an option's state is truthy, so `{"sms_notification": false}` means opt-out rather than booking `A3` (today it emits the code).
5. **No per-service mandatory-rule enforcement** — PostNord's rules (below) are documented, not validated karrio-side; PostNord governs acceptance, consistent with the entry-code PRD's pass-through decision.
6. **Notification language rides the existing locale chain** — the booking `locale` query parameter (from `options.language`, wired in the locale-continuity work) already controls SMS/Email language; no change.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| `units.py` `ShippingOption` entries + unified aliases | `email_notification_to` address override (future) |
| `create.py` truthy-state emission fix | Per-service mandatory-rule validation |
| `test_shipment.py` notification option tests | Notification content templating |
| README options documentation | Tracking-side notifications (locale already handled) |

## Open Questions & Decisions

### Pending Questions

None — all decisions resolved during design (see below).

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | Surface | `options` on the Create Shipment API: unified `sms_notification`/`email_notification` bools + carrier-scoped `postnord_notify_by_letter`/`postnord_notify_by_phone`/`postnord_driver_notification` | `options` is a free-form `PlainDictField`; unified names give cross-carrier consistency, scoped names cover the rest | 2026-09-07 |
| D2 | Opt-in default | Absent = no notification codes booked (today's behavior) | PostNord's model is additive; no suppress flag exists | 2026-09-07 |
| D3 | Falsy emission | Emit `additionalServiceCode` only for truthy option states | Verified: `{"postnord_optional_service_point": False}` currently emits `A7`; explicit False must mean opt-out | 2026-09-07 |
| D4 | Cross-exclusion | None — additive codes; SMS-only is "set only `sms_notification`" | Matches user requirement; no invented gating | 2026-09-07 |
| D5 | Service rules | Document, do not enforce (17/18/20/24 mandatory rules) | PostNord validates at booking; consistent with entry-code D4 | 2026-09-07 |
| D6 | Contact data | Unchanged — `_party` already fills `emailAddress`/`phoneNo`/`smsNo` | Data slots are not triggers; codes are | 2026-09-07 |
| D7 | `email_notification_to` | Out of scope | Unified override exists in core but adds consignee-contact rewriting; separate change if wanted | 2026-09-07 |

## Problem Statement

### Current State

```python
# modules/connectors/postnord/karrio/providers/postnord/units.py:163-175
class ShippingOption(lib.Enum):
    """PostNord additionalServiceCode values."""

    postnord_cod = lib.OptionEnum("A1", float, meta=dict(category="COD"))
    postnord_insurance = lib.OptionEnum("A5", float, meta=dict(category="INSURANCE"))
    postnord_optional_service_point = lib.OptionEnum("A7", bool)
    postnord_flexchange = lib.OptionEnum("C7", bool)
    postnord_collect_in_store = lib.OptionEnum("E4", bool)
    postnord_early_collect = lib.OptionEnum("F6", bool)
    postnord_pallet_groupage = lib.OptionEnum("65", bool, ...)
    # No A2/A3/A4/A9/B8: no notification channel is bookable.
```

```python
# modules/connectors/postnord/karrio/providers/postnord/shipment/create.py:145-151
options = lib.to_shipping_options(
    payload.options,
    package_options=packages.options,
    initializer=provider_units.shipping_options_initializer,
)

additional_service_codes = [option.code for _, option in options.items()]
# State never checked: {"option": False} still emits the code (verified live).
```

```python
# create.py _party(): consignee contact always fully populated —
# emailAddress=email, phoneNo=phone_number, smsNo=phone_number.
# Channel data present, but nothing can trigger a notification.
```

### Desired State

```python
class ShippingOption(lib.Enum):
    """PostNord additionalServiceCode values."""

    postnord_cod = lib.OptionEnum("A1", float, meta=dict(category="COD"))
    postnord_insurance = lib.OptionEnum("A5", float, meta=dict(category="INSURANCE"))
    postnord_optional_service_point = lib.OptionEnum("A7", bool)
    postnord_flexchange = lib.OptionEnum("C7", bool)
    postnord_collect_in_store = lib.OptionEnum("E4", bool)
    postnord_early_collect = lib.OptionEnum("F6", bool)
    postnord_pallet_groupage = lib.OptionEnum("65", bool, ...)

    # Consignee notification channels (general-descriptions.pdf;
    # codes current per Read This First v22.7). All bound to the
    # consignee party's contact slots; language follows the booking
    # `locale` query parameter.
    postnord_notify_by_letter = lib.OptionEnum("A2", bool)
    postnord_notify_by_sms = lib.OptionEnum("A3", bool)
    postnord_notify_by_email = lib.OptionEnum("A4", bool)
    postnord_notify_by_phone = lib.OptionEnum("A9", bool)
    postnord_driver_notification = lib.OptionEnum("B8", bool)

    """ Unified Option type mapping """
    cash_on_delivery = postnord_cod
    insurance = postnord_insurance
    sms_notification = postnord_notify_by_sms
    email_notification = postnord_notify_by_email
```

```python
additional_service_codes = [
    option.code for _, option in options.items() if option.state
]
```

### Problems

1. **No channel is bookable**: a merchant cannot ask PostNord to notify the consignee at all, let alone choose SMS-only.
2. **Opt-out semantics are broken**: explicit `False` on a bool option still emits its code, so even future opt-in flags could not be reliably declined.
3. **Undocumented rules**: PostNord's per-service notification requirements are invisible to integrators using the connector.

## Goals & Success Criteria

### Goals

1. A merchant can opt in per channel via Create Shipment `options` — e.g. `{"sms_notification": true}` books exactly `A3` and nothing else.
2. Explicit `False` (or omission) books nothing.
3. Existing shipments without notification options produce byte-identical requests.
4. Per-service mandatory rules and channel semantics are documented in the README.

### Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Notification option tests (unified, scoped, multi, falsy, dedupe) | 6 passing | Must-have |
| Falsy-emission regression test (`A7` with `False`) | Passing | Must-have |
| Existing postnord suite | All green | Must-have |
| README notification documentation | Merged | Must-have |

### Launch Criteria

**Must-have (P0):**
- [ ] Unified `sms_notification`/`email_notification` map to `A3`/`A4`
- [ ] Carrier-scoped `A2`/`A9`/`B8` bookable
- [ ] Truthy-state emission in effect, with regression test
- [ ] Full postnord connector suite green

**Nice-to-have (P1):**
- [ ] Live test-environment booking confirming a service rule (e.g. Parcel 18 rejecting no-notification)

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| `ShippingOption` codes via existing channel (selected) | Zero request-structure changes; unified aliases for free; matches `cash_on_delivery` pattern | None identified | **Selected** |
| Raw-read options like `entry_code` | Bypasses enum | Unnecessary — these are pure codes with no payload value; the enum channel is exactly right | Rejected |
| Suppress by clearing consignee contact slots | Enables "no data" on services where allowed | Breaks mandatory-data rules (17/20/24); karrio `Address` has one phone field feeding both slots | Rejected |
| Enforce per-service rules karrio-side | Early errors | Duplicates PostNord validation; rules are 2021-era PDF text of unverified live enforcement | Rejected |

## Technical Design

### Existing Code Analysis

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| Options → codes channel | `shipment/create.py:145-151`, `units.py:182-194` | Carries the new options unchanged; add state check |
| Unified notification options | `modules/sdk/karrio/core/units.py:1206-1208` | `sms_notification`, `email_notification` mapped as aliases (like `cash_on_delivery`) |
| Alias canonicalization | `modules/sdk/karrio/core/units.py:1126-1130` | Unified and scoped names for the same code parse to one canonical member — duplicate emission impossible |
| Bool state semantics | `modules/sdk/karrio/core/utils/enum.py:148-150` | `state = value is not False`; emission must check state (D3) |
| Booking `locale` param | `mappers/postnord/proxy.py:119`, locale chain in `create.py` | Notification language, already wired |
| Consignee contact population | `create.py` `_party()` | Unchanged (D6) |
| Pallet-groupage option test | `tests/postnord/test_shipment.py:45-62` | Template for code-emission assertions |

### Option Flow

```
                Create Shipment API  (POST /api/v1/shipments/)
                        │  options: {"sms_notification": true}
                        ▼
              shipment payload options (PlainDictField, free-form;
              also mergeable via selected_rate.meta, gateway.py:293-298)
                        │
                        ▼
        lib.to_shipping_options(... shipping_options_initializer)
                        │  key recognized in postnord ShippingOption
                        │  (unified name → canonical member "A3")
                        ▼
        additional_service_codes = [option.code
                                    for _, option in options.items()
                                    if option.state]          ← D3 fix
                        │
                        ▼
        service.additionalServiceCode: ["A3"]
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│ PostNord (booking v3)                                   │
│ A2 letter   → consignee address                         │
│ A3 SMS      → consignee smsNo      (language: locale)   │
│ A4 e-mail   → consignee emailAddress (language: locale)  │
│ A9 phone    → consignee phoneNo    (voice)               │
│ B8 driver   → consignee phoneNo    (driver call)         │
│ no code    → no notification                            │
└─────────────────────────────────────────────────────────┘
```

### Field Reference

| Karrio option (Create Shipment `options`) | Code | Channel | Unified |
|-------------------------------------------|------|---------|---------|
| `sms_notification` / `postnord_notify_by_sms` | `A3` | SMS to consignee `smsNo` | Yes |
| `email_notification` / `postnord_notify_by_email` | `A4` | E-mail to consignee `emailAddress` | Yes |
| `postnord_notify_by_letter` | `A2` | Letter to consignee address | No |
| `postnord_notify_by_phone` | `A9` | Voice call to consignee `phoneNo` | No |
| `postnord_driver_notification` | `B8` | Driver call to consignee `phoneNo` | No |

No other API changes: `options` is schema-free per shipment, so the Create Shipment endpoint exposes the new keys without serializer modifications.

## Edge Cases & Failure Modes

### Edge Cases

| Scenario | Expected Behavior | Handling |
|----------|-------------------|----------|
| Option absent | No code; payload unchanged | Default |
| Explicit `False` | No code | D3 state check |
| Unified and scoped name both set (e.g. `sms_notification` + `postnord_notify_by_sms`) | Single `A3` | Alias canonicalization to one member |
| Multiple channels (`sms_notification` + `email_notification`) | `["A3", "A4"]` | Additive model |
| Float option with `0` (e.g. `postnord_cod: 0`) | Code dropped | D3 truthy check; a zero-value COD is meaningless |
| Service requiring a channel (Parcel 18: one of A2/A3/A4) | PostNord validates; karrio sends as booked | D5 documented pass-through |
| MyPack Home (17) | Consignee SMS-or-email data already mandatory in `_party` | D6 unchanged |

### Failure Modes

| What Can Go Wrong | Impact | Mitigation |
|-------------------|--------|------------|
| PostNord rejects a booking violating a service rule | Booking fails with carrier message | Existing error parser surfaces it |
| PostNord ignores a code on an unsupported service | Notification silently absent | D5; README documents rules |
| Emission fix drops a previously-emitted falsy code | Behavior change for `False`-valued bools | That emission was wrong; regression test pins new semantics |

## Implementation Plan

### Phase 1: Options, emission fix, tests, docs

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Add five `ShippingOption` entries + unified aliases | `modules/connectors/postnord/karrio/providers/postnord/units.py` | Pending | S |
| Truthy-state emission (`if option.state`) | `modules/connectors/postnord/karrio/providers/postnord/shipment/create.py` | Pending | S |
| Six notification tests + falsy regression test | `modules/connectors/postnord/tests/postnord/test_shipment.py` | Pending | S |
| Document notification options and service rules | `modules/connectors/postnord/README.md` | Pending | S |

**Dependencies:** none.

## Testing Strategy

> `unittest` only, from repository root, inline-payload style matching the locale and pallet-groupage tests.

### Test Cases

```python
def test_create_shipment_notification_sms_option(self):
    # Unified name books exactly A3.
    payload = {**ShipmentPayload, "options": {"sms_notification": True}}
    request = gateway.mapper.create_shipment_request(
        models.ShipmentRequest(**payload)
    )
    codes = lib.to_dict(request.serialize())["shipment"][0]["service"][
        "additionalServiceCode"
    ]
    self.assertIn("A3", codes)

def test_create_shipment_notification_email_option(self):
    # Unified email_notification -> A4.

def test_create_shipment_notification_multiple_channels(self):
    # sms + email -> A3 and A4 present.

def test_create_shipment_notification_carrier_scoped_names(self):
    # letter/phone/driver -> A2/A9/B8 present.

def test_create_shipment_notification_explicit_false_opts_out(self):
    # {"sms_notification": False} -> "A3" not in codes (D3).

def test_create_shipment_notification_aliases_dedupe(self):
    # Both unified and scoped names set -> exactly one "A3".

def test_create_shipment_option_false_not_emitted(self):
    # Pre-existing bug regression: {"postnord_optional_service_point": False}
    # -> "A7" not in codes.
```

### Running Tests

```bash
source bin/activate-env
python -m unittest discover -v -f modules/connectors/postnord/tests
./bin/run-sdk-tests   # pre-merge sweep
```

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Falsy-emission fix changes existing behavior | Medium | Low | Only affects falsy-valued options, which were booking unwanted codes; regression tests |
| Service rules enforced differently than the 2021-era PDF | Low | Medium | D5 pass-through; P1 live check; error parser surfaces rejections |
| Dual alias confusion (unified vs scoped) | Low | Low | Canonical-member dedupe tested; README shows both |
| Scope creep into `email_notification_to` | Low | Low | Explicitly out of scope (D7) |

## Migration & Rollback

### Backward Compatibility

- **API compatibility**: additive; absent options produce identical requests (insurance fixture equality unchanged — its state is truthy).
- **Behavior change**: falsy-valued bool options no longer emit codes — the prior emission was incorrect; documented here as D3.
- **Data compatibility**: no schema or persistence changes.

### Rollback Procedure

1. Revert the implementation commit(s).
2. Re-run the postnord connector suite.
3. No data cleanup required.

## Appendices

### Appendix A: Notification Code Evidence

| Source | Location | Statement |
|--------|----------|-----------|
| General descriptions PDF | `vendor/docs/general-descriptions.pdf` | "A2 Notification by letter … A3 Notification by SMS (SMS number placed in the consignee party) … A4 Notification by E-mail … A9 Notification by Phone (Telephone number placed in the consignee party) … B8 Driver Notification" |
| General descriptions PDF, service rules | same | MyPack Home (17): "SMS or Email is mandatory in Consignee party", C7 mandatory unless A6/F1; Parcel (18): "Either of these additional services must be used" (A2/A3/A4); Return Pickup (20): SMS mandatory both parties; Return (24): email and SMS mandatory on return part |
| Current implementation guidelines | Read This First v22.7 (PostNord API portal) | "Notification by SMS (A3)" still documented |
| Booking swagger | `vendor/booking.swagger.json:6139+` | `additionalServiceCode` free-form code list; `locale` param "The SMS and Email is written in the defined language" |
| Falsy emission (live probe) | this session | `shipping_options_initializer({"postnord_optional_service_point": False})` → `['A7']` |
| Unified options | `modules/sdk/karrio/core/units.py:1206-1208` | `sms_notification`, `email_notification`, `email_notification_to` exist in core |

### Appendix B: README Documentation Text

```markdown
### Notification options (optional, per shipment)

PostNord notifies the consignee only when a notification additional service
is booked; there is no suppress flag. Book channels via the shipment
`options` — setting one excludes the others by construction:

| Option | Code | Channel |
|--------|------|---------|
| `sms_notification` | A3 | SMS to the consignee's phone (least intrusive) |
| `email_notification` | A4 | E-mail to the consignee's address |
| `postnord_notify_by_letter` | A2 | Letter to the consignee's address |
| `postnord_notify_by_phone` | A9 | Voice call to the consignee's phone |
| `postnord_driver_notification` | B8 | Driver call to the consignee's phone |

Notification language follows the booking locale (`options.language` chain).
`false` or omitted books nothing. Note per-service rules: PostNord documents
Parcel (18) as requiring one of A2/A3/A4 and MyPack Home (17) as requiring
consignee SMS-or-email contact data; PostNord validates these at booking.
```

### Appendix C: Carrier-Specific Reference

**API Documentation:**
- Implementation Guidelines "Read This First" v22.7: https://pn-api-portal-files.s3-eu-west-1.amazonaws.com/Read_This_First_v22.7.pdf
- PostNord Customer API Guides: https://guide.developer.postnord.com/
- Booking APIs 3.5.29.1 spec: https://developer.postnord.com/apis/details?systemName=shipment-v3-booking-sao

**Field Mappings:**

| Karrio Field | Carrier Field | Notes |
|--------------|---------------|-------|
| `options.sms_notification` | `additionalServiceCode` `A3` | Unified alias of `postnord_notify_by_sms` |
| `options.email_notification` | `additionalServiceCode` `A4` | Unified alias of `postnord_notify_by_email` |
| `options.postnord_notify_by_letter` | `additionalServiceCode` `A2` | Carrier-scoped |
| `options.postnord_notify_by_phone` | `additionalServiceCode` `A9` | Voice, carrier-scoped |
| `options.postnord_driver_notification` | `additionalServiceCode` `B8` | Carrier-scoped |
