# Spec Delta

## Purpose

Defines how the SDK reads list connection config values and publishes the enum choices of list connection configs, so that dashboards can offer the allowed values and connectors always receive a list.

## ADDED Requirements

### Requirement: List connection config values are coerced to lists

For a connection config typed as a bare `list` or as `typing.List[...]`, the SDK SHALL read a missing value as `None`, a list or tuple as a new list with the same items in the same order, and any other value, including a string, as a one-item list containing that value.
The SDK SHALL NOT validate or drop list items.

#### Scenario: String stored for an enum list config

- **WHEN** a connection stores `"sms"` for a config typed `typing.List[NotificationChannel]`
- **THEN** the connector reads `["sms"]`

#### Scenario: String stored for a bare list config

- **WHEN** a connection stores `"signature"` for `shipping_options`
- **THEN** the connector reads `["signature"]`, not a list of characters

#### Scenario: Unknown item passes through

- **WHEN** a connection stores `["sms", "pigeon"]` for a config typed `typing.List[NotificationChannel]`
- **THEN** the connector reads `["sms", "pigeon"]`

#### Scenario: Declared default

- **WHEN** a config declares `default=["email"]` and the connection stores no value
- **THEN** the connector reads `["email"]`

### Requirement: Enum choices of list configs are published

For a connection config or shipping option typed `typing.List[E]` where `E` is an enum, the published references SHALL report `type` as `list` and `enum` as the member names of `E` in declaration order, and SHALL include a declared `default`.
List configs whose item type is not an enum SHALL be published without `enum`, and existing single-value enum configs SHALL be published unchanged.

#### Scenario: Enum list connection config

- **WHEN** a connector declares `lib.OptionEnum("postnord_default_notification", typing.List[NotificationChannel])` with members `sms`, `email` and `letter`
- **THEN** its connection config reference is `{"name": "postnord_default_notification", "code": "postnord_default_notification", "required": false, "type": "list", "enum": ["sms", "email", "letter"]}`

#### Scenario: Plain list config

- **WHEN** a connector declares `lib.OptionEnum("shipping_options", list)`
- **THEN** its reference has `type` `list` and no `enum`
