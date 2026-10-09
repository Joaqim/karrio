# Proposal

## Why

Karrio plugins can register carriers (Mapper, Proxy, Settings) or address validators, but nothing lets a plugin contribute to a rate or shipment request while it is processed (`modules/sdk/karrio/core/metadata.py`, `modules/sdk/karrio/api/interface.py`).
Regional or organisational conventions, such as "a Swedish shipper sending a PostNord parcel to Norway must also email the commercial invoice", therefore have nowhere to live except inside carrier connectors or core, where they do not belong.
No connector or SDK component emits karrio-authored advisories today; every warning message is parsed from a carrier response (`docs/notes/customs/nordic-trade-documents-facts.md`, cross-connector survey).
A single, region-neutral extension point lets such conventions ship as independently versioned plugins, following the precedent of the data-only `stamp_seeds` metadata field.

## What Changes

- Add a `shipment_advisors` field to `PluginMetadata`: a list of advisor callables, each receiving the unified request and a non-secret carrier context (carrier name, carrier id, account country code, test mode, and the connection's non-credential configuration) and returning a list of unified `Message` objects.
- Advisors never receive connection credentials; shipper identity and addresses come from the unified request itself.
- Collect advisors from every discovered plugin, including plugins that register no carrier or address validator, alongside the existing metadata collection in `modules/sdk/karrio/references.py`.
- Run the collected advisors in the SDK when rates are fetched and when a shipment is created, and append their messages to the response messages for each carrier gateway involved.
- Advisors are advisory only: their messages cannot block the operation, cannot alter the request or the carrier response, and any level above warning is reported as warning.
- An advisor that raises is isolated: the operation proceeds and the failure is reported as a warning message naming the plugin.
- Plugins declaring advisors report the plugin type `advisor` (alongside `carrier` or `lsp` when they are also integrations) instead of `unknown`.
- Advisors run only for gateways that produced a result: gateways that were aborted or failed, and rate gateways that returned no rates, receive no advisor messages.
- The server persists advisor messages returned when a label is purchased onto the shipment's messages, so API consumers see purchase-time advisories.
- Plugins without advisors, and deployments without advisor plugins, behave exactly as before.

Out of scope: the Nordic trade-document conventions themselves (a separate plugin in `karrio-community-plugins`), advisors for operations other than rating and shipment creation, advisor configuration in the server or dashboard, and any change to carrier connectors.

## Capabilities

### New Capabilities

- `plugins/shipment-advisors`: how plugins declare shipment advisors, when the SDK runs them during rating and shipment creation, the non-blocking, failure-isolated contract of their messages, and their persistence on purchased shipments.

### Modified Capabilities

None.

## Impact

- `modules/sdk/karrio/core/metadata.py` (new `PluginMetadata` field), `modules/sdk/karrio/references.py` (collection), `modules/sdk/karrio/api/interface.py` (invocation in rating and shipment creation), and SDK tests; `modules/manager/karrio/server/manager/serializers/shipment.py` (persist purchase-time messages) with a Django test; no generated files or connectors change.
- Public API: one new optional plugin metadata field and additional warning messages in rate and shipment responses when advisor plugins are installed; no breaking change.
- Delivered on an upstream-bound branch `feat-shipment-advisors` off `upstream/main`, registered in the develop assembly; upstream submission to karrioapi/karrio needs a PRD in `PRDs/` derived from this proposal and its design.
- Unblocks the Nordic conventions plugin in `~/projects/karrio-community-plugins`, specified separately in that repository.
