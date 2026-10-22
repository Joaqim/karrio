# Spec Delta

## Purpose

Defines how the carrier connection dialog edits list connection configs that publish enum choices, so that users pick and order the values a connector accepts.

## ADDED Requirements

### Requirement: Enum list configs are edited as ordered pills

The carrier connection dialog SHALL render every connection config published with `type` `list`, an `enum` array and no nested `fields` as ordered pills: the selected values in their stored order, each with controls to move it earlier, move it later and remove it, and the unselected enum values as pills that append the value when chosen.
Selected pills SHALL also be reorderable by dragging.
A value SHALL appear at most once, and stored values outside the published enum SHALL be shown as selected pills.

#### Scenario: Reorder with buttons

- **WHEN** a user's selection is `sms`, `email` and the user activates "move later" on `sms`
- **THEN** the selection becomes `email`, `sms`

#### Scenario: Add an unselected value

- **WHEN** the selection is `email` and the user chooses the `letter` add-pill
- **THEN** the selection becomes `email`, `letter` and `letter` is no longer offered as an add-pill

### Requirement: Empty selection saves as unset

When the user removes every selected value, the dialog SHALL submit the config as `null`, so the stored connection no longer carries the key.

#### Scenario: Remove the last value

- **WHEN** an existing connection stores `["sms"]` and the user removes `sms` and saves
- **THEN** the saved connection config has no `postnord_default_notification` key

### Requirement: Published default pre-fills new connections

When a carrier is picked for a new connection and an enum list config publishes a non-empty `default`, the dialog SHALL start that config's selection as the default.

#### Scenario: New connection with a default

- **WHEN** a user adds a connection for a carrier whose enum list config publishes `default` `["sms", "email"]`
- **THEN** the dialog shows `sms` and `email` selected in that order before any edit
