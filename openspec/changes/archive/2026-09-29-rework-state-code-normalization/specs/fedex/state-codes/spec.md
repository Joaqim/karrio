## Purpose

Defines which countries FedEx requests carry `stateOrProvinceCode` for, and how the value sent is derived from the address state without altering the stored address.

## ADDED Requirements

### Requirement: State code is sent only for countries FedEx uses

FedEx rate, shipment and pickup requests SHALL include `stateOrProvinceCode` for an address only when its country is US, CA, PR, MX, IN or AE and the address has a state, and SHALL leave the field out otherwise.

#### Scenario: Swedish shipper has no state code

- **WHEN** a rate or shipment request is built for a shipper with `country_code` `SE` and `state_code` "Västra Götaland"
- **THEN** the shipper address in the request has no `stateOrProvinceCode`

#### Scenario: Swedish pickup address has no state code

- **WHEN** a pickup create or update request is built for an address with `country_code` `SE` and a `state_code`
- **THEN** the pickup address in the request has no `stateOrProvinceCode`

### Requirement: State names are sent as subdivision codes

For addresses in the countries listed above, the FedEx connector SHALL send the state resolved to its subdivision code by the SDK resolver, and SHALL then apply the FedEx-specific mapping of Canadian `QC` to `PQ`.
A state the resolver leaves unchanged SHALL be sent as entered.

#### Scenario: US state entered by name

- **WHEN** a rate or shipment request is built for a recipient with `country_code` `US` and `state_code` "New York"
- **THEN** the recipient address in the request has `stateOrProvinceCode` `NY`

#### Scenario: Quebec entered by name

- **WHEN** a rate, shipment or pickup request is built for an address with `country_code` `CA` and `state_code` "Québec"
- **THEN** the address in the request has `stateOrProvinceCode` `PQ`

#### Scenario: Code entered is unchanged

- **WHEN** a rate request is built for a recipient with `country_code` `US` and `state_code` `NY`
- **THEN** the recipient address in the request has `stateOrProvinceCode` `NY`
