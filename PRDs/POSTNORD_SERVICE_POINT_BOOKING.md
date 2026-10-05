# PostNord service point booking

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-10-05 |
| Status | In Progress |
| Owner | Joaqim Planstedt |
| Type | Enhancement |
| Reference | [AGENTS.md](../AGENTS.md); [PRD_POSTNORD_INTEGRATION.md](./PRD_POSTNORD_INTEGRATION.md) (Q5, D16) |

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

The PostNord connector can look up service points (`gateway.proxy.find_service_points`, Service Points v5) but cannot book a shipment to one the recipient chose.
This PRD adds six connector shipment options that carry a chosen service point into the Shipping v3 (EDI) booking as the `deliveryParty`, identified by the service point id with `partyIdType` `"156"`, and appends the Optional Service Point additional service (`A7`) and, when the consignee has a phone, SMS (`A3`).
The service point parse also exposes the point's visiting address beside the delivery address, because PostNord specifies the delivery address for the EDI and the label and the visiting address for guiding the customer.
It answers question Q5 of the integration PRD ("How should MyPack Collect (19) receive its delivery service point?").

### Key Architecture Decisions

1. **Connector-prefixed shipment options, one per field**: `postnord_service_point_id`, `_name`, `_street`, `_city`, `_postal_code`, `_country_code`, following the flat service-point option pattern of the `dhl_freight_sweden` connector; Karrio has no unified service-point option (integration PRD D16).
2. **The chosen point is the EDI `deliveryParty`**: `partyIdentification {partyId: <id>, partyIdType: "156"}` plus the point's name and address; the swagger defines `156` as "Service point ID in deliveryParty", and the consignee party stays the recipient.
3. **`A7` is implied by a chosen point**: the connector appends `A7` when a point is chosen and it is not already booked, and `A3` when the consignee has a phone number and it is not already booked, per the "MyPack Collect (19) + Addon: Optional Servicepoint" booking sample cited in the code.
4. **Incomplete point details fail locally**: an id without all five details raises a field error naming each missing option before any request is sent, since a `deliveryParty` requires a `party` with name and address.
5. **Detail options never become additional service codes**: `SERVICE_POINT_DETAIL_OPTIONS` excludes the six options from the `additionalServiceCode` list built from truthy options.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| Six `postnord_service_point_*` shipment options in `units.py` | A unified Karrio service-point option or contract |
| `deliveryParty` with `partyIdType` `"156"` in the booking request | Server, GraphQL, or dashboard surfaces for choosing a point |
| Automatic `A7`, and `A3` on a consignee phone | Product compatibility checks (which services accept `A7`) |
| Field error for incomplete point details | Collect In-Store (`E4`) and Early Collect (`F6`) point semantics |
| `visiting_address` in the service point parse | Deriving booking options from a lookup result inside the connector |
| README documentation of the options and the `A3` exception | Live sandbox capture of a service point booking |

---

## Open Questions & Decisions

### Pending Questions

| # | Question | Context | Options | Status |
|---|----------|---------|---------|--------|
| Q1 | Should `A7` be appended for every product, or only where PostNord accepts it? | The Service Points v5 description names MyPack Collect (19) as the main user of the point and says Parcel (18) and Expresspaket (42) need it for Collect In-Store (`E4`) or Early Collect (`F6`); the connector appends `A7` for any service, and the tests book it on `postnord_parcel` (18) | A) Keep, PostNord validates at booking; B) Append `A7` only for 19; C) Skip `A7` when `E4` or `F6` is booked | Pending |
| Q2 | Is the `deliveryParty` shape accepted live? | No sandbox or production booking with a chosen point has been captured; the shape follows the vendored booking swagger and the official booking sample named in the code comments, which is not part of the vendored swagger | A) Capture a sandbox booking and vendor the evidence; B) Accept on swagger and sample evidence | Pending |
| Q3 | Is overriding an explicit `sms_notification: false` with `A3` the intended policy? | Implemented and documented in the README so the recipient learns where to collect; it is the only case where the connector books a notification the caller declined | A) Keep; B) Respect the opt-out and rely on other channels; C) Field error | Pending owner confirmation |
| Q4 | Should detail options without `postnord_service_point_id` warn or fail? | They are silently ignored: no `deliveryParty`, no `A7`, no message | A) Keep silent; B) Warning message; C) Field error | Pending |
| Q5 | Should the connector check the point id against PostNord's limits? | `partyId` is 1 to 17 characters in the swagger, and Service Points v5 states that point ids are unique only in combination with the country code; the connector passes the id and `country_code` through unchecked | A) Leave validation to PostNord; B) Local length check | Pending |

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | Option shape | Six flat string options, `postnord_service_point_{id,name,street,city,postal_code,country_code}` | Mirrors the `dhl_freight_sweden` service-point options; each value maps to one EDI field | 2026-10-05 |
| D2 | Party identifier type | `"156"` | Booking swagger `partyIdType`: "156 = Service point ID in deliveryParty" | 2026-10-05 |
| D3 | `deliveryParty` carries no `issuerCode` | Omitted | The point is a collection agent, not a contract party; consignor and consignee keep theirs | 2026-10-05 |
| D4 | Address used for the booking | The lookup's `address` key, sourced from `deliveryAddress` | Service Points v5: "The delivery address should be used in the EDI and on the Label" | 2026-10-05 |
| D5 | Visiting address exposure | New `visiting_address` key; `address` keeps its existing `deliveryAddress`-then-`visitingAddress` precedence | Service Points v5: "The visiting address is used to guide the customers to the service point" | 2026-10-05 |
| D6 | Incomplete details | `FieldError` keyed `options.postnord_service_point_<key>` for each missing detail | The swagger requires `party` on `deliveryParty`; a local error names the option to fix | 2026-10-05 |
| D7 | Duplicate codes | `A7` and `A3` are appended only when absent | An explicit `postnord_optional_service_point` or `sms_notification: true` must not book a code twice | 2026-10-05 |

---

## Problem Statement

### Current State

The booking request built in `shipment/create.py` has only a consignor and a consignee party:

```python
parties=postnord_req.PartiesType(
    consignor=_party(shipper, with_consignor_id=True),
    consignee=_party(recipient, with_consignor_id=False),
),
```

`postnord_optional_service_point` (`A7`) can be booked as a boolean, but no option carries which point the recipient chose.
The service point parse returns one `address`, `deliveryAddress` with a `visitingAddress` fallback, so a caller cannot show the visiting address and book with the delivery address.

### Desired State

```python
models.ShipmentRequest(
    ...,
    service="postnord_mypack_collect",
    options={
        "postnord_service_point_id": "588462",
        "postnord_service_point_name": "Hemköp Sjövikshallen",
        "postnord_service_point_street": "17 Sjövikstorget",
        "postnord_service_point_city": "STOCKHOLM",
        "postnord_service_point_postal_code": "11758",
        "postnord_service_point_country_code": "SE",
    },
)
# -> parties.deliveryParty = {partyIdentification: {partyId: "588462", partyIdType: "156"},
#                             party: {nameIdentification: {name: ...}, address: {...}}}
# -> service.additionalServiceCode = ["A7", "A3"]
```

### Problems

| Problem | Impact |
|---------|--------|
| No input for a chosen point | MyPack Collect (19) cannot route a parcel to the point the recipient picked |
| One merged address in the parse | Callers cannot distinguish the EDI address from the customer-facing address |
| `A7` must be set by hand | A chosen point without `A7` books no optional service point |

---

## Goals & Success Criteria

### Goals

1. Book a shipment to a chosen service point in one `Shipment.create` call.
2. Keep bookings without a chosen point byte-identical to before.
3. Refuse incomplete point details before calling PostNord.

### Success Criteria

| Metric | Target |
|--------|--------|
| `deliveryParty` shape | Matches the swagger: `partyIdentification` with `partyIdType` `"156"`, `party` with name and address |
| Additional services with a point | `["A7", "A3"]` with a consignee phone, `["A7"]` without |
| Duplicate codes | None when `A3` or `A7` is also requested explicitly |
| Booking without point options | No `deliveryParty`, no `A7` |
| Incomplete details | One `SHIPPING_SDK_FIELD_ERROR` naming each missing option, no HTTP request |
| Postnord suite | All tests pass (126 at the time of writing) |

---

## Alternatives Considered

| Alternative | Pros | Cons | Decision |
|-------------|------|------|----------|
| Flat connector options (chosen) | No core change; matches `dhl_freight_sweden`; each value maps to one EDI field | Six options instead of one | Accepted |
| One structured option holding the lookup dict | One key per point | `lib.OptionEnum` types are scalar; nested validation and documentation are harder | Rejected |
| Book with the id alone and let PostNord resolve the address | Fewer inputs | The swagger requires `party` on `deliveryParty`; PostNord asks for the delivery address in the EDI | Rejected |
| Look the point up during booking | Caller passes only the id | Extra API call per booking, and needs the Service Points product on the key | Rejected |
| Unified Karrio service-point option | Cross-carrier | Shared-core decision; integration PRD D16 keeps service points connector-local | Out of scope |

---

## Technical Design

### Existing Code Analysis

| File | What exists | Reused |
|------|-------------|--------|
| `karrio/providers/postnord/units.py` | `ShippingOption` with `postnord_optional_service_point = OptionEnum("A7", bool)`, `postnord_notify_by_sms` (`A3`, unified `sms_notification`) | Codes `A7` and `A3` |
| `karrio/providers/postnord/shipment/create.py` | Truthy-state emission of `additionalServiceCode` from `options.items()`; `_party()` builds consignor and consignee | Emission list, `PartiesType` |
| `karrio/schemas/postnord/shipment_request.py` (generated) | `PartiesType.deliveryParty: ConsigneeType`, `PartyIdentificationType`, `PartyType`, `NameIdentificationType`, `AddressType`; `deliveryParty` was added to `schemas/shipment_request.json` and regenerated on `feat-postnord-connector` (`feat(postnord): add deliveryParty to the shipment request schema`) | All types, unchanged on this branch |
| `karrio/providers/postnord/service_points.py` | `_normalize_service_point` returning `id`, `name`, `type`, `address`, `coordinates`, `opening_hours`, `distance` | Address mapping, extracted into a local helper |
| `vendor/booking.swagger.json` (`docs-vendored-carrier-specs`) | `deliveryParty` requires `party`; `partyIdType` lists `156` | Field semantics |
| `vendor/servicepoints-v5.swagger.json` | Delivery address for EDI and label, visiting address for the customer; `A7`, `E4`, `F6` descriptions | D4, D5, Q1 |
| `dhl_freight_sweden` connector | Flat service-point options with a local completeness check | D1, D6 |

### Architecture

```
 caller
   │ 1. find_service_points(address)            ┌──────────────────────────┐
   ├───────────────────────────────────────────>│ Service Points v5        │
   │<──────── [{id, name, address,              │ nearest/byaddress        │
   │            visiting_address, ...}]         └──────────────────────────┘
   │
   │ 2. ShipmentRequest(options={postnord_service_point_*})
   ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │ shipment/create.py: shipment_request()                               │
 │                                                                      │
 │  options ──┬─> additionalServiceCode (minus SERVICE_POINT_DETAIL_    │
 │            │                          OPTIONS)                       │
 │            └─> _service_point_details(options)                       │
 │                  │ id unset ──────────────> None (no deliveryParty)  │
 │                  │ id set, detail missing ─> FieldError (no request) │
 │                  ▼ complete                                          │
 │               point ──┬─> append A7 if absent                        │
 │                       ├─> append A3 if recipient phone and absent    │
 │                       └─> _delivery_party(point)                     │
 │                             partyIdentification{id, "156"}           │
 │                             party{name, address}                     │
 └───────────────────────────────┬──────────────────────────────────────┘
                                 ▼
                    POST /rest/shipment/v3/edi/labels/{pdf,zpl}
```

### Request shape

```
shipment[0]
├── service
│   ├── basicServiceCode: "19"
│   └── additionalServiceCode: ["A7", "A3"]
└── parties
    ├── consignor      (customer number, partyIdType "160", issuerCode)
    ├── consignee      (recipient address and contacts)
    └── deliveryParty
        ├── partyIdentification: {partyId: "588462", partyIdType: "156"}
        └── party
            ├── nameIdentification: {name: "Hemköp Sjövikshallen"}
            └── address: {streets: ["17 Sjövikstorget"], postalCode: "11758",
                          city: "STOCKHOLM", countryCode: "SE"}
```

### Option to EDI field mapping

| Option | Option code (never emitted) | EDI field |
|--------|-----------------------------|-----------|
| `postnord_service_point_id` | `servicepoint` | `deliveryParty.partyIdentification.partyId` |
| `postnord_service_point_name` | `servicepointName` | `deliveryParty.party.nameIdentification.name` |
| `postnord_service_point_street` | `servicepointStreet` | `deliveryParty.party.address.streets[0]` |
| `postnord_service_point_city` | `servicepointCity` | `deliveryParty.party.address.city` |
| `postnord_service_point_postal_code` | `servicepointPostalCode` | `deliveryParty.party.address.postalCode` |
| `postnord_service_point_country_code` | `servicepointCountryCode` | `deliveryParty.party.address.countryCode` |

A lookup result maps as `id` to `_id`, `name` to `_name`, and the `address` key (the delivery address) to the street, city, postal code and country options.

### Service point parse

| Key | Source | Change |
|-----|--------|--------|
| `address` | `deliveryAddress`, else `visitingAddress` | Unchanged precedence |
| `visiting_address` | `visitingAddress` | New; omitted when the point has none |

---

## Edge Cases & Failure Modes

| Case | Behavior |
|------|----------|
| No point options | No `deliveryParty`, no implied `A7` or `A3`; request unchanged |
| Id with all five details | `deliveryParty` sent; `A7` appended; `A3` appended when the recipient has a phone |
| Id with one or more details missing | `FieldError` with one entry per missing option; no HTTP request |
| Details without an id | Ignored silently (Q4) |
| `sms_notification: false` with a point and a recipient phone | `A3` is still booked (Q3) |
| `sms_notification: true` or `postnord_optional_service_point: true` with a point | Each code appears once |
| Recipient without a phone | Only `A7` is implied |
| Product other than MyPack Collect (19) | `A7` is still appended; PostNord decides acceptance (Q1) |
| `E4` or `F6` booked with a point | `A7` is appended beside them (Q1) |
| Zero-leading postal code | Sent as a string; the generated `postalCode` type is not coerced |
| Point id from another country than `country_code` | Passed through unchecked (Q5) |

---

## Implementation Plan

| Phase | Commit | Files |
|-------|--------|-------|
| 1 | `docs(postnord): add service point booking PRD` | `PRDs/POSTNORD_SERVICE_POINT_BOOKING.md` |
| 2 | `feat(postnord): expose visiting address in service point parse` | `karrio/providers/postnord/service_points.py`, `tests/postnord/test_servicepoints.py` |
| 3 | `feat(postnord): book to a chosen service point via EDI deliveryParty` | `karrio/providers/postnord/units.py`, `karrio/providers/postnord/shipment/create.py`, `tests/postnord/test_service_point_booking.py`, `README.md` |

All paths are under `modules/connectors/postnord/` except the PRD.
No generated schema, mapper, server, or dashboard file changes on this branch; the `deliveryParty` schema member comes from the parent branch.

---

## Testing Strategy

Run from the worktree root inside the nix dev shell:

```bash
python -m unittest discover -v -f modules/connectors/postnord/tests
```

### `tests/postnord/test_service_point_booking.py` (`TestPostNordServicePointBooking`)

| Test | Asserts |
|------|---------|
| `test_delivery_party_is_booked_with_the_chosen_point` | `partyIdentification == {"partyId": "588462", "partyIdType": "156"}`, no `issuerCode`, name and address fields, `additionalServiceCode == ["A7", "A3"]` |
| `test_explicit_sms_opt_out_is_overridden_for_a_chosen_point` | `["A7", "A3"]` with `sms_notification: False` |
| `test_chosen_point_without_consignee_phone_books_only_a7` | `["A7"]` |
| `test_chosen_point_with_sms_opt_in_does_not_duplicate_a3` | One `A3`; codes are `A3` and `A7` |
| `test_without_options_no_delivery_party_and_no_a7` | No `deliveryParty`; `service == {"basicServiceCode": "18"}` |
| `test_incomplete_point_details_refuse_before_the_request` | Proxy not called; one `SHIPPING_SDK_FIELD_ERROR` with details `{"options.postnord_service_point_city": ...}` |

### `tests/postnord/test_servicepoints.py` (`TestPostNordServicePoints`)

| Test | Asserts |
|------|---------|
| `test_parse_service_points_response` (fixture extended) | A point with distinct `deliveryAddress` and `visitingAddress` maps them to `address` and `visiting_address` |
| `test_parse_service_points_exposes_visiting_and_delivery_addresses` | A visiting-only point yields both keys from `visitingAddress` |

The existing `test_shipment.py` cases without point options guard goal 2.

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| PostNord rejects the `deliveryParty` shape | Bookings with a point fail | Low | Shape follows the swagger; capture a sandbox booking (Q2) |
| `A7` rejected on a product | Booking fault from PostNord | Medium | PostNord's fault is surfaced as a message; Q1 decides whether to restrict |
| Caller passes the visiting address instead of the delivery address | Parcel routed with the wrong address | Low | README and D4 name the `address` key as the booking source |
| Unrequested `A3` | SMS sent despite `sms_notification: false` | Certain when configured so | Documented exception (Q3) |

---

## Migration & Rollback

The options are additive and default to unset, so existing bookings are unchanged.
The parse adds one key and keeps `address` as before.
Rollback is reverting the two feature commits; no data or schema migration is involved.

---

## Appendices

### Sources

| Source | Content used |
|--------|--------------|
| `modules/connectors/postnord/vendor/booking.swagger.json` (`docs-vendored-carrier-specs`) | `deliveryParty` (required `party`), `partyIdentification`, `partyIdType` code list including `156`, `partyId` length 1 to 17 |
| `modules/connectors/postnord/vendor/servicepoints-v5.swagger.json` | Delivery versus visiting address usage; `A7`, `E4`, `F6`; point ids unique only with the country code |
| `PRDs/PRD_POSTNORD_INTEGRATION.md` | Q5 (service point party for MyPack Collect), D16 (connector-local service points) |
| `modules/connectors/postnord/README.md` | Shipment options table and the Service points section |
