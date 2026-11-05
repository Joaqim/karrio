# Design

## Context

See proposal.md for motivation and the two spec deltas for required behaviour.
The implementation branch is based on `upstream/main` at deea10f85.

`ConnectionConfigOptions` calls `OptionEnum.__call__` once per stored key (`modules/sdk/karrio/core/units.py`, `Options.__init__`), so coercion there covers every connector.
`OptionEnum.__call__` branches on `bool`, then on `"enum" in str(self.type)`, then on `__origin__`, then calls the type; a bare `list` therefore reaches `list(value)`.
`collect_references` publishes `enum` for options and connection configs from the same substring check and `parse_type` checks the substring before list names.
The server merges a connection's stored config with the submitted one and strips `None` values (`process_dictionaries_mutations` in `modules/core/karrio/server/serializers/abstract.py`), so a key submitted as `null` is removed and an omitted key keeps its old value.

## Decisions

### Coerce before the enum check

A list branch runs before the enum substring check and handles `type is list` and `typing.get_origin(type) is list`.
Only `list` and `tuple` count as list values; any other value, including a `dict` or `set`, becomes a one-item list, because `list()` of those yields keys or an unstable order.

### Publish enum through one helper

`extract_enum_names(type)` returns the item enum's member names for list types (via `extract_list_item_enum`, which requires an `enum.Enum` subclass), and otherwise keeps the existing substring rule for single-value types.
Options and connection configs both use it; no upstream shipping option is typed `typing.List[Enum]`, so their published output is unchanged.
`default` is published as declared, so connectors declare list defaults as member names.

### Reuse the `enum` key

A list config with `enum` means "the allowed items"; a separate `item_enum` key was rejected because the dashboard would read two keys for one concept.

### Pills widget

`OrderedEnumPills` is built from the existing `badgeVariants`, `Button` and lucide icons, with native HTML5 drag events and move buttons for keyboard and assistive-technology users; no dependency is added.
It renders stored values outside the published enum as selected pills, de-duplicates by first occurrence, and emits `null` for an empty selection.
The dialog routes `type === "list"` configs with an `enum` array and no `fields` to it and pre-fills a published non-empty `default` when the carrier is picked for a new connection.

## Risks

A consumer that relied on a string splitting into characters sees a one-item list instead; no upstream connector reads strings from these configs.
