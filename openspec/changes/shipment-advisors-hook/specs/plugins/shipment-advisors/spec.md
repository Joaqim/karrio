# Spec Delta

## Purpose

Lets plugins contribute non-blocking advisory messages to rate and shipment responses, so that regional or organisational shipping conventions can ship as independently versioned plugins instead of living in carrier connectors or core.

## ADDED Requirements

### Requirement: Plugins declare shipment advisors in their metadata

A plugin SHALL be able to declare shipment advisors through an optional `shipment_advisors` field of its plugin metadata, and the SDK SHALL collect the advisors of every discovered plugin, including plugins that register neither a carrier nor an address validator.

#### Scenario: Advisor-only plugin is collected

- **WHEN** a plugin whose metadata declares only `shipment_advisors`, with no carrier mapper, proxy, settings, or address validator, is installed
- **THEN** its advisors are collected and the plugin is not reported as an unknown or invalid plugin

#### Scenario: Plugins without advisors are unaffected

- **WHEN** no installed plugin declares `shipment_advisors`
- **THEN** rate and shipment responses are identical to those produced before this capability existed

### Requirement: Advisors run during rating and shipment creation

The SDK SHALL invoke every collected advisor once per carrier gateway when rates are fetched and when a shipment is created, passing the unified request and a carrier context, and SHALL append the messages each advisor returns to the response messages.

#### Scenario: Advisor message appears on a shipment response

- **WHEN** a shipment is created through a carrier gateway and an installed advisor returns one warning message for that request
- **THEN** the shipment response carries that warning in its messages alongside the carrier's own messages, and the shipment details are unchanged

#### Scenario: Advisor runs per carrier when rating several carriers

- **WHEN** rates are fetched from two carrier gateways and an installed advisor returns a message that names the carrier from its context
- **THEN** the rate response carries one advisor message for each carrier

### Requirement: Advisors receive no credentials

The carrier context passed to advisors SHALL contain only the carrier name, carrier id, account country code, test mode flag, and the connection's non-credential configuration, and SHALL NOT contain API keys, secrets, passwords, tokens, or account numbers used for authentication.
Shipper identity and addresses SHALL be available to advisors only through the unified request.

#### Scenario: Credentials are absent from the advisor context

- **WHEN** an advisor inspects the carrier context for a connection configured with an API key and secret
- **THEN** neither value is reachable from the context

### Requirement: Advisor messages are advisory only

Advisor output SHALL NOT block the operation, alter the unified request sent to the carrier, or alter the carrier response; a message returned with a level above warning SHALL be reported with level warning.

#### Scenario: Error-level advisor message is downgraded

- **WHEN** an advisor returns a message with level error
- **THEN** the operation completes as it would without the advisor and the message is reported with level warning

#### Scenario: Advisor cannot change the request

- **WHEN** an advisor mutates the request object it receives
- **THEN** the request sent to the carrier is the one the caller supplied

### Requirement: Failing advisors are isolated

An advisor that raises SHALL NOT fail the operation; the SDK SHALL report the failure as a warning message identifying the plugin, and SHALL still run the remaining advisors.

#### Scenario: Raising advisor is reported and skipped

- **WHEN** one installed advisor raises an exception and another returns a warning
- **THEN** the operation succeeds, the response carries the other advisor's warning, and a warning names the plugin whose advisor failed
