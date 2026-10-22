## Purpose

Defines how the DHL Freight Sweden connector exposes destination address validation to operators and applies it during booking: the connection-config option, its three modes, pre-flight failure handling, and mode-value resolution.

## Requirements

### Requirement: Address validation option is visible in connection configuration

The connector's connection-config catalog SHALL publish an `address_validation` option as a string-type enumeration whose values are exactly `off`, `warn`, and `enforce`, so that generic connection-configuration UIs render it as a selectable control.

#### Scenario: References payload classification

- **WHEN** carrier references are generated for `dhl_freight_sweden`
- **THEN** the `address_validation` connection-config entry carries type `string` and enum values `["off", "warn", "enforce"]`

#### Scenario: Dashboard renders the option

- **WHEN** an operator opens the Connection configuration dialog for the carrier
- **THEN** the address validation option renders as a dropdown offering the three modes, and saving a selection persists that mode on the connection

#### Scenario: Stored values remain valid

- **WHEN** a connection already stores `off`, `warn`, or `enforce`
- **THEN** the stored value continues to resolve to the same mode, with no migration step

### Requirement: Booking pre-flight honors the configured mode

Shipment creation SHALL perform a destination route check before submitting the booking request when the mode is `warn` or `enforce`, and SHALL NOT perform it when the mode is `off` or the destination is ineligible: consignee country other than Sweden, missing postal code, or a product without home-delivery servability.

#### Scenario: Mode off skips the check

- **WHEN** a shipment is created with mode `off` for an otherwise eligible destination
- **THEN** no route-check request is sent and booking proceeds as before

#### Scenario: Mode warn reports without blocking

- **WHEN** a shipment is created with mode `warn` and the route check reports the destination as not servable
- **THEN** booking completes and the response carries the route-check findings as warning messages

#### Scenario: Mode enforce blocks unservable destinations

- **WHEN** a shipment is created with mode `enforce` and the route check definitively reports the destination as not servable
- **THEN** shipment creation fails with a field error on the recipient postal code and no booking request is sent

#### Scenario: Ineligible destinations skip the check regardless of mode

- **WHEN** the consignee is outside Sweden, lacks a postal code, or the product has no home-delivery servability flag
- **THEN** no route check is performed

### Requirement: Pre-flight fails open on upstream errors

When the route-check endpoint responds with a server error or a body that cannot be classified, shipment creation SHALL proceed without blocking and SHALL NOT report a definitive servability verdict from an inconclusive response.

#### Scenario: Outage during booking

- **WHEN** the route-check endpoint returns a 5xx or unparseable response during a booking with mode `enforce`
- **THEN** the shipment is booked and no postal-code field error is raised from that response

### Requirement: Unrecognized mode values resolve deterministically

A stored `address_validation` value SHALL resolve case-insensitively to the matching mode, and any value that still does not name a mode SHALL resolve to `off` rather than silently enabling pre-flight behavior.

#### Scenario: Case-insensitive match

- **WHEN** the connection stores `Warn`
- **THEN** the mode resolves to `warn`

#### Scenario: Unrecognized value disables the pre-flight

- **WHEN** the connection stores a value that names no mode, for example `true` or `strict`
- **THEN** the mode resolves to `off` and booking proceeds without a route check

### Requirement: Direct address validation is independent of the mode

The connector SHALL expose address validation as a standalone operation that remains callable regardless of the connection's `address_validation` mode; the mode SHALL gate only the booking pre-flight.

#### Scenario: Standalone validation with mode off

- **WHEN** a direct address validation request is issued for a connection whose mode is `off`
- **THEN** the request is executed and its route and servability result returned, unaffected by the mode
