## Purpose

Defines how the server stores the state or province of a submitted address, and the SDK resolver that carrier connectors use to derive a subdivision code from it when a carrier requires one.

## Requirements

### Requirement: Submitted state is stored as entered

The server SHALL store an address `state_code` exactly as submitted, for addresses created or updated through REST or GraphQL and for addresses copied onto a shipment, without converting names to codes.
Adapting the state to a carrier's field format SHALL happen only in the carrier connector when it builds a request.

#### Scenario: Region name is kept on create

- **WHEN** an address with `country_code` `SE` and `state_code` "Västra Götaland" is created
- **THEN** the stored and returned `state_code` is "Västra Götaland"

#### Scenario: State name is kept on update

- **WHEN** a stored address is updated with `country_code` `US` and `state_code` "California"
- **THEN** the stored and returned `state_code` is "California"

#### Scenario: Shipment addresses keep the state as entered

- **WHEN** a shipment is created with a shipper whose `state_code` is "Västra Götaland"
- **THEN** the shipment's shipper `state_code` is "Västra Götaland"

### Requirement: SDK resolves subdivision names to codes

The SDK SHALL provide a resolver that, given a state value and a country code, returns the subdivision code for that country using only the subdivisions the SDK already publishes per country (AE, AU, CA, CN, IN, MX, US).
A value that is already a known code for the country SHALL be returned as that code, with or without an ISO 3166-2 `CC-` prefix.
Otherwise the value SHALL be matched against subdivision names ignoring case, accents and a trailing `state`, `province`, `county` or `region` word.
A value that matches no subdivision or more than one subdivision, a country without published subdivisions, and an empty value SHALL be returned unchanged.

#### Scenario: Name resolves to code

- **WHEN** "California" is resolved for country `US`
- **THEN** the result is `CA`

#### Scenario: Name matching ignores case and accents

- **WHEN** "quebec" and "Québec" are resolved for country `CA`
- **THEN** both results are `QC`

#### Scenario: Known code and prefixed code resolve to the code

- **WHEN** "ny" and "US-NY" are resolved for country `US`
- **THEN** both results are `NY`

#### Scenario: Country without published subdivisions is unchanged

- **WHEN** "Västra Götaland" is resolved for country `SE`
- **THEN** the result is "Västra Götaland"

#### Scenario: Unmatched value is unchanged

- **WHEN** "Atlantis" is resolved for country `US`
- **THEN** the result is "Atlantis"

#### Scenario: Missing value stays missing

- **WHEN** no state is resolved for country `US`
- **THEN** the result is empty
