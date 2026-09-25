# Design

## Context

See proposal.md for motivation and specs/plugins/shipment-advisors/spec.md for required behaviour.
Line references below are to `upstream/main` at deea10f85, the base of the implementation branch.

`PluginMetadata` is an attrs class whose fields end with `system_config` (`modules/sdk/karrio/core/metadata.py:19-66`); a plugin without Mapper, Proxy, and Settings is typed `unknown` (`:113`, `:130`) but is still kept in `references.PLUGIN_METADATA`.
`import_extensions` resets and fills module-level registries and already collects `SYSTEM_CONFIGS` from every plugin regardless of type (`modules/sdk/karrio/references.py:27-39, 59-69, 190-194`).
`Rating.fetch` builds one shared payload, runs each gateway in a thread, and merges messages in `flatten()` (`modules/sdk/karrio/api/interface.py:315-380`, merge at `:375`); `Shipment.create` builds the payload, swaps shipper and recipient for returns (`:457-469`), and produces `(details, messages)` inside its deserialize closures (`:485`, `:502`).
Settings carry generic non-secret fields `carrier_id`, `account_country_code`, `test_mode`, `config`, and a `carrier_name` property, while credentials are connector-specific attrs fields with no generic marker (`modules/sdk/karrio/core/settings.py:13-24`).
`Message.level` is a free-form string (`modules/sdk/karrio/core/models.py:325`).
The server calls the SDK directly for rates and shipments (`modules/core/karrio/server/core/gateway.py:309-310, 747-750`), persists rate messages on the shipment (`modules/manager/karrio/server/manager/serializers/shipment.py:131, 654`), and does not persist messages returned at purchase.
`Rates.fetch` raises 424 when a response has no rates but has messages (`gateway.py:752`).
The fork's `feat-document-stamping` adds `stamp_seeds` to `PluginMetadata` directly after `connection_configs` and changes `core/settings.py` near `connection_cache`.

## Goals / Non-Goals

Goals: one metadata field, one registry, one runner used by both rating and shipment creation, a context built from an allowlist, and a server change limited to persisting purchase-time messages.
Non-goals: advisor ordering or priorities, advisor configuration, per-rate (rather than per-response) messages, and advisors for tracking, pickups, manifests, or document operations.

## Decisions

### Advisor shape

An advisor is a callable `(request, context) -> Iterable[Message]`, where `request` is the unified `RateRequest` or `ShipmentRequest` and `context` is an immutable `AdvisorContext` attrs instance with `carrier_name`, `carrier_id`, `account_country_code`, `test_mode`, `operation` (`rating` or `shipping`), and `config`.
A single signature for both operations lets an advisor branch on `context.operation` or on the request type.
Alternative considered: separate `rate_advisors` and `shipment_advisors` fields; rejected because conventions usually apply at both moments and two lists double the registration surface.

### Context from an allowlist

`AdvisorContext.from_settings(settings, operation)` copies the five base fields and `dict(settings.config or {})`, deep-copied; nothing else on the settings object is read.
Alternative considered: stripping known credential names per connector; rejected because credentials are arbitrary connector-specific fields with no marker, so any denylist leaks new ones.

### Placement to avoid conflicts

The metadata field `shipment_advisors: List[Callable] = []` (attrs `factory=list`) is added after `system_config`, not beside `connection_configs`, so it does not textually conflict with the fork's `stamp_seeds` addition.
`AdvisorContext` and the runner live in a new module `modules/sdk/karrio/core/advisors.py`, keeping `core/settings.py` untouched.
Plugin typing adds `advisor` to `plugin_types` when `shipment_advisors` is non-empty, and `plugin_type` becomes `advisor` for a plugin that is neither carrier nor LSP.

### Registry

`references.ADVISORS` is a list of `(plugin_id, advisor)` pairs, reset and filled in `import_extensions` next to `SYSTEM_CONFIGS`, and read through `get_advisors()` without `lru_cache`, because the cached accessors pin the first registry object and would miss a later `import_extensions`.

### Runner and isolation

`run_advisors(request, settings, operation) -> List[Message]` builds the context, passes each advisor a deep copy of the request, collects messages, sets `carrier_name` and `carrier_id` from the context when absent, downgrades any level other than `info` or `warning` to `warning`, and prefixes nothing.
Each advisor call is wrapped in a single `except Exception` that converts the failure into a warning with code `shipment_advisor_failed` and details `{plugin, error}`.
This is a deliberate exception to the repository rule against catching bare `Exception`: advisors are third-party code whose failure modes are unknown, and the spec guarantees that a broken plugin never fails rating or shipping; the handler is confined to this one call site and the reason is stated in its docstring.
`lib.failsafe` is not used because it discards the error, and the spec requires the failure to be reported.
Codes avoid the `SHIPPING_SDK_` prefix that the server's `is_sdk_message` treats specially.
Validation of the advisor's returned value sits inside the same handler, so a malformed return is reported as a failure rather than breaking the operation.
`models.Message` requires `carrier_name` and `carrier_id`, so advisors construct messages with those arguments (possibly `None`) and the runner fills them from the context; the plugin documentation states this.

### Invocation points

In `Rating.fetch`, advisors run inside `flatten()` per gateway after parsing, and only when rates remain after the connection's `filter_rates`, which keeps the server's 424 rule unchanged for gateways whose rates are all filtered out.
In `Shipment.create`, advisors run inside the deserialize closure after parsing, only when shipment details are present, with the request as sent to the carrier (the swapped copy for returns).
Advisors never see the carrier response, so they cannot alter it.
Alternative considered: running advisors before the carrier call; rejected because advice about an operation that then aborts is noise and the spec skips aborted gateways.

### Server persistence

In `buy_shipment_label`, messages returned by shipment creation are merged into `shipment.messages` alongside the stored rate messages, de-duplicated by `(carrier_id, code, message)`.
Only this merge changes on the server; serializers already expose `messages` on the shipment.

## Risks / Trade-offs

- [A slow advisor delays every rate and shipment call] → accepted for now and documented; advisors are expected to be pure functions of the request; timeouts are a possible follow-up.
- [An advisor holds a reference to the deep-copied request] → harmless, since the carrier receives the original payload.
- [Merge conflict with feat-document-stamping in `metadata.py`] → field placed after `system_config`; the develop rebuild verifies a clean merge.
- [Upstream reviewers object to the broad exception handler] → rationale stated in the docstring and the PRD; the handler scope is one call.
- [Purchase-time messages previously dropped now appear on shipments] → this includes non-blocking carrier warnings such as `customs_omitted_intra_eu` from the PostNord and DHL Freight Sweden connectors, which API consumers could not see before; covered by a Django test and listed in the changelog.

## Migration Plan

Work lands on `feat-shipment-advisors` branched from `upstream/main` and registered in the develop assembly's BRANCHES; `develop` is regenerated with `rebuild-develop.sh`.
No data migration is involved; rollback is removing the branch from BRANCHES and regenerating develop.
Upstream submission to karrioapi/karrio adds a PRD in `PRDs/` derived from this proposal and design.

## Open Questions

None.
