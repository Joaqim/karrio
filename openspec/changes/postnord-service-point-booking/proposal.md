# Proposal

## Why

The postnord connector looks up service points through `gateway.proxy.find_service_points` (Service Points v5), but a booking cannot name the point the recipient chose.
MyPack Collect (19) routes a parcel to an optional service point only when the Shipping v3 (EDI) request carries that point as the `deliveryParty`, identified by the point id with `partyIdType` `"156"`; the connector sends only consignor and consignee parties, which leaves question Q5 of `PRDs/PRD_POSTNORD_INTEGRATION.md` open.
The lookup parse also folds the delivery and visiting addresses into one `address`, while PostNord specifies the delivery address for the EDI and the label and the visiting address for guiding the customer.

This change documents an implementation that already exists on `postnord-service-point-booking` (PRD `PRDs/POSTNORD_SERVICE_POINT_BOOKING.md`).

## What Changes

- Six string shipment options, `postnord_service_point_id`, `postnord_service_point_name`, `postnord_service_point_street`, `postnord_service_point_city`, `postnord_service_point_postal_code` and `postnord_service_point_country_code`, carry a chosen point into the booking.
- A chosen point is sent as `parties.deliveryParty`: `partyIdentification {partyId: <id>, partyIdType: "156"}` plus `party` with the point's name and address, and no `issuerCode`.
- A chosen point appends additional service `A7` when absent, and `A3` when the consignee has a phone number and `A3` is absent; `A3` is booked even when `sms_notification` is explicitly false.
- A point id without all five details fails with a field error naming each missing option, before any request is sent.
- The six options never appear in `additionalServiceCode`.
- The service point parse adds `visiting_address` from `visitingAddress`; `address` keeps its `deliveryAddress`-then-`visitingAddress` source.
- The connector README documents the options, the `deliveryParty` mapping and the `A3` exception to opt-in notifications.

## Capabilities

### New Capabilities

- `postnord/service-points`: service point lookup results expose delivery and visiting addresses, and a booking can be routed to a chosen service point through the EDI `deliveryParty`.

### Modified Capabilities

## Impact

- Code: `modules/connectors/postnord/karrio/providers/postnord/units.py` (options, `SERVICE_POINT_DETAIL_OPTIONS`), `modules/connectors/postnord/karrio/providers/postnord/shipment/create.py` (`_service_point_details`, `_delivery_party`, code list), `modules/connectors/postnord/karrio/providers/postnord/service_points.py` (`visiting_address`), `modules/connectors/postnord/README.md`.
- Tests: new `modules/connectors/postnord/tests/postnord/test_service_point_booking.py`; `test_servicepoints.py` gains a visiting-address case and a fixture point with distinct addresses.
- Schema: no change on this branch; `deliveryParty` was added to the request schema on `feat-postnord-connector`.
- No server, GraphQL or dashboard changes: the options are connector-prefixed and pass through the free-form shipment options.
- Branch: `postnord-service-point-booking`, based on `feat-postnord-connector`, registered in `BRANCHES` in `docs/notes/workflow/assemble-develop.sh`.
