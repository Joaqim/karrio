# Proposal

## Why

A connector can declare a connection config whose value is an ordered list of enum values, such as the PostNord connector's preference order of notification channels (`lib.OptionEnum("postnord_default_notification", typing.List[NotificationChannel])` with members `sms`, `email` and `letter`).
The SDK publishes no allowed values for such a config, because `references` only publishes `enum` for single-value enum types (`modules/sdk/karrio/references.py`, `collect_references`).
`OptionEnum.__call__` passes typing generics through unchanged and turns a string stored for a bare `list` config into a list of characters (`modules/sdk/karrio/core/utils/enum.py`).
Both places detect enums with `"enum" in str(type)`, which matches a `typing.List[X]` whose item type lives in a module path containing `enum`.
The carrier connection dialog renders no field for a list config without nested `fields` (`packages/ui/components/carrier-connection-dialog.tsx`, `renderConfigFields`).

## What Changes

- `OptionEnum` coerces values of every list connection config, bare `list` and `typing.List[...]` alike: `None` stays `None`, a list or tuple is copied, and any other value, a string included, becomes a one-item list.
  This changes how a string stored for `shipping_options` or `shipping_services` reads: one item instead of characters.
- The SDK does not validate list items; unknown names reach the connector.
- `references` publishes `type: "list"` and the item enum's member names as `enum` for connection configs and shipping options typed `typing.List[SomeEnum]`, reports list types as `list` before the enum substring check, and never iterates a typing generic for enum names.
- The carrier connection dialog renders every list connection config that publishes `enum` as ordered pills: add-pills for unselected values, native drag and drop plus move-earlier and move-later buttons for reordering, and a remove control per pill.
- An empty selection saves as `null`, which the server's config merge drops, and a published `default` pre-fills new connections.

Out of scope: the Django admin `SystemConnection` form, the legacy `connect-provider-modal`, `apps/www`, the built elements bundle, and the PostNord connector change that declares the first such config (it lives in `PrimePack-AB/karrio-postnord`).

## Capabilities

### New Capabilities

- `plugins/connection-configs`: how list connection configs are coerced and how their enum choices are published.
- `dashboard/connection-config-fields`: how the carrier connection dialog edits enum list connection configs.

### Modified Capabilities

None.

## Impact

- `modules/sdk/karrio/core/utils/enum.py`, `modules/sdk/karrio/references.py`, two SDK test modules, `packages/ui/components/ordered-enum-pills.tsx` (new) and `packages/ui/components/carrier-connection-dialog.tsx`; no generated files, connectors or server code change.
- Public API: list connection configs and list shipping options with an enum item type gain an `enum` key in references.
- Delivered on the upstream-bound branch `feat-connection-config-enum-list` off `upstream/main` with `PRDs/CONNECTION_CONFIG_ENUM_LIST.md` as its first commit, registered in the develop assembly.
