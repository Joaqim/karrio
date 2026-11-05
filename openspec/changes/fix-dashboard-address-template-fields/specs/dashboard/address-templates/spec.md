## Purpose

Defines how the dashboard copies saved address and parcel templates into shipment and manifest addresses and parcels, so that only address or parcel data is copied and template record metadata stays on the template.

## ADDED Requirements

### Requirement: Picking an address template copies address fields only

When a user picks an address template from an address name field's suggestions, the dashboard SHALL copy only the template's address fields into the address being edited.
The template's `id`, `object_type`, `meta`, `label`, `is_default`, `validate_location` and timestamps SHALL NOT be copied, and the edited address SHALL keep its own `id`.

#### Scenario: Template picked on a saved draft shipper

- **WHEN** a user edits the shipper of a saved shipment draft, picks the address template "Hisingen" from the name suggestions, and saves
- **THEN** the shipment update succeeds, the shipper carries the template's address fields, and the shipper `id` is the shipment's own shipper id

#### Scenario: Template picked on other address editors

- **WHEN** a user picks an address template in the recipient or return address editor of the shipment, order or bulk label pages, or in the manifest address editor
- **THEN** the saved address carries no `object_type`, `meta` or template `id`

### Requirement: Default templates seed address and parcel fields only

When a new shipment draft is seeded from the workspace's default address and parcel templates, the dashboard SHALL copy only their address and parcel fields, and SHALL NOT modify the template data it read.

#### Scenario: New draft from default templates

- **WHEN** a user opens the create label page with a default address template and a default parcel template, and saves the draft
- **THEN** the stored shipper and parcel carry the templates' address and parcel fields, and no template `id` or `meta`

#### Scenario: Workspace tax ids do not alter the template

- **WHEN** the workspace has a federal or state tax id and the default address template has none
- **THEN** the seeded shipper carries the workspace tax ids and the default address template shown elsewhere in the dashboard does not
