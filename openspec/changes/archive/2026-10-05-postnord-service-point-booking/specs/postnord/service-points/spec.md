## Purpose

Defines how the PostNord connector exposes Service Points v5 lookup results and routes a booking to a service point the recipient chose, through the Shipping v3 (EDI) `deliveryParty`.

## ADDED Requirements

### Requirement: Service point lookups expose delivery and visiting addresses

A parsed service point SHALL carry `address` from PostNord's `deliveryAddress`, falling back to `visitingAddress` when the point has no delivery address, and SHALL carry `visiting_address` from `visitingAddress` when the point has one, because PostNord specifies the delivery address for the EDI and the label and the visiting address for guiding the customer.

#### Scenario: Distinct delivery and visiting addresses

- **WHEN** a lookup returns a point with a `deliveryAddress` and a different `visitingAddress`
- **THEN** the parsed point's `address` is the delivery address and its `visiting_address` is the visiting address

#### Scenario: Visiting address only

- **WHEN** a lookup returns a point with a `visitingAddress` and no `deliveryAddress`
- **THEN** the parsed point's `address` and `visiting_address` are both the visiting address

### Requirement: A chosen service point is booked as the EDI delivery party

When `postnord_service_point_id` is set together with `postnord_service_point_name`, `postnord_service_point_street`, `postnord_service_point_city`, `postnord_service_point_postal_code` and `postnord_service_point_country_code`, the booking request SHALL carry `parties.deliveryParty` with `partyIdentification` holding the point id as `partyId` and `"156"` as `partyIdType`, and `party` holding the point name and its street, postal code, city and country code, without an `issuerCode`.
The consignee party SHALL remain the recipient.
The six options SHALL NOT appear as `additionalServiceCode` values.
Without `postnord_service_point_id`, the request SHALL carry no `deliveryParty`.

#### Scenario: Complete point details

- **WHEN** a shipment is booked with all six service point options
- **THEN** `deliveryParty.partyIdentification` is `{partyId: <id>, partyIdType: "156"}`, `deliveryParty.party` carries the name and address, `deliveryParty` has no `issuerCode`, and no option code of the six appears in `additionalServiceCode`

#### Scenario: No point options

- **WHEN** a shipment is booked without service point options
- **THEN** the request has no `deliveryParty` and no implied `A7`

### Requirement: A chosen service point implies optional service point and SMS

A booking with a chosen service point SHALL include additional service `A7`, and SHALL include `A3` when the recipient has a phone number, appending each only when it is not already booked, and SHALL book `A3` even when `sms_notification` is explicitly false.

#### Scenario: Recipient with a phone

- **WHEN** a chosen point is booked and the recipient has a phone number
- **THEN** `additionalServiceCode` is `["A7", "A3"]`

#### Scenario: Recipient without a phone

- **WHEN** a chosen point is booked and the recipient has no phone number
- **THEN** `additionalServiceCode` is `["A7"]`

#### Scenario: Explicit SMS opt-out

- **WHEN** a chosen point is booked with `sms_notification: false` and the recipient has a phone number
- **THEN** `additionalServiceCode` is `["A7", "A3"]`

#### Scenario: Explicit SMS opt-in

- **WHEN** a chosen point is booked with `sms_notification: true`
- **THEN** `additionalServiceCode` contains `A3` once and `A7` once

### Requirement: Incomplete service point details fail before the request

When `postnord_service_point_id` is set and any of the five detail options is missing, the operation SHALL fail with a field error keyed `options.postnord_service_point_<key>` for each missing detail, and no request SHALL be sent to PostNord.

#### Scenario: Missing city

- **WHEN** a shipment is booked with every service point option except `postnord_service_point_city`
- **THEN** the operation returns one `SHIPPING_SDK_FIELD_ERROR` whose details name `options.postnord_service_point_city`, and no request is sent
