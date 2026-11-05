# Design

## Context

See proposal.md for motivation and `PRDs/POSTNORD_SERVICE_POINT_BOOKING.md` on `postnord-service-point-booking` for the full design, alternatives and open questions.
State on `feat-postnord-connector` (the base):

- `ShippingOption` in `units.py` already books `A7` as `postnord_optional_service_point` (bool) and `A3` as `postnord_notify_by_sms`, mapped to the unified `sms_notification`.
- `shipment_request()` in `shipment/create.py` builds `additionalServiceCode` from every truthy option code, and `PartiesType` with only `consignor` and `consignee`.
- The generated `PartiesType` has a `deliveryParty: ConsigneeType` member, added by the base branch's `feat(postnord): add deliveryParty to the shipment request schema`.
- `_normalize_service_point()` in `service_points.py` returns one `address` from `deliveryAddress or visitingAddress`.

Evidence:

- Booking swagger (`docs-vendored-carrier-specs`, `modules/connectors/postnord/vendor/booking.swagger.json`): `deliveryParty` requires `party`; `partyIdType` "156 = Service point ID in deliveryParty"; `partyId` is 1 to 17 characters.
- Service Points v5 swagger: "The delivery address should be used in the EDI and on the Label", "The visiting address is used to guide the customers to the service point", and point ids are unique only together with the country code.
- The code cites PostNord's "MyPack Collect (19) + Addon: Optional Servicepoint" booking sample for the `A7` and `A3` pairing; the sample is not part of the vendored swagger.

## Goals / Non-Goals

**Goals:**

- Book to a chosen point in one `Shipment.create` call, with the point as the EDI `deliveryParty`.
- Leave bookings without point options unchanged.
- Refuse incomplete point details locally, naming the missing options.
- Expose both lookup addresses so a caller can show the visiting address and book with the delivery address.

**Non-Goals:**

- A unified Karrio service-point option or server, GraphQL or dashboard surfaces.
- Product compatibility checks for `A7`, and Collect In-Store (`E4`) or Early Collect (`F6`) point semantics.
- Looking up the point during booking or deriving options from a lookup result inside the connector.

## Decisions

**Six flat connector options.**
Each value maps to one EDI field and follows the flat service-point options of the `dhl_freight_sweden` connector.
Alternative considered: one structured option holding the lookup dict, rejected because `lib.OptionEnum` types are scalar.

**The point is `deliveryParty`, the recipient stays `consignee`.**
`_delivery_party()` builds a `ConsigneeType` with `partyIdentification {partyId, partyIdType: "156"}` and `party {nameIdentification.name, address {streets: [street], postalCode, city, countryCode}}`, without `issuerCode`, since the point is not a contract party.

**`A7` and `A3` are implied, never duplicated.**
After collecting truthy option codes, a chosen point appends `A7` if absent and `A3` if the recipient has a phone number and `A3` is absent.
The `A3` pairing ignores an explicit `sms_notification: false`; the README documents this as the one exception to opt-in notifications.

**Detail options are excluded from the code list.**
`SERVICE_POINT_DETAIL_OPTIONS` holds the six option names, and the code list comprehension skips them, so their placeholder codes (`servicepoint`, `servicepointName`, ...) never reach `additionalServiceCode`.

**Completeness is checked before the request.**
`_service_point_details()` returns `None` when the id is unset, and raises `lib.exceptions.FieldError` keyed `options.postnord_service_point_<key>` for each missing detail when it is set.

**The parse keeps `address` and adds `visiting_address`.**
A local `_address()` helper maps either source, `address` keeps its existing precedence, and `visiting_address` is present only when the point has a `visitingAddress`.

## Risks / Trade-offs

- [No live booking with a chosen point has been captured] → the shape follows the swagger and the cited sample; live verification is PRD question Q2.
- [`A7` is appended for every product] → PostNord rejects unsupported combinations at booking and the fault is surfaced; whether to restrict is PRD question Q1.
- [`A3` booked against an explicit opt-out] → documented policy; owner confirmation is PRD question Q3.
- [Detail options without an id are ignored silently] → PRD question Q4.
- [Point id and country are not cross-checked] → PostNord validates; PRD question Q5.

## Migration Plan

Additive connector options defaulting to unset, and one added parse key; no data or API migration.
Rollback is a revert of the two feature commits.
