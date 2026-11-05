# Changelog entry (draft for the next release)

CHANGELOG.md is compiled by release commits from the git log, so this draft stages the entry here for the release step rather than inserting an unreleased section into a file whose sections are all releases.
Commits are on `feat-shipment-advisors` (base `upstream/main` deea10f85); each entry names the commits that implement it.

## Features

- feat(sdk): add the optional `shipment_advisors` field to `PluginMetadata`, a list of callables `(request, context) -> Iterable[Message]` that contribute advisory messages to rate and shipment responses (dc2369fb3).
- feat(sdk): collect shipment advisors from every discovered plugin, including plugins that register neither a carrier nor an address validator, through `karrio.references.get_advisors()` (c69e60f99).
- feat(sdk): pass advisors an immutable `AdvisorContext` built from an allowlist of connection settings (`carrier_name`, `carrier_id`, `account_country_code`, `test_mode`, `operation`, and a deep copy of `config`), so connection credentials are never reachable (6d39092dd).
- feat(sdk): run advisors on their own deep copy of the request, fill missing message carrier identity from the context, report any level other than `info` or `warning` as `warning`, and report a raising or malformed advisor as a `shipment_advisor_failed` warning naming the plugin while the remaining advisors still run (37cc990a0, 5d7ff38a2).
- feat(sdk): run advisors in `Rating.fetch` once per gateway that still has rates after the connection's rate filtering (9c68b3967).
- feat(sdk): run advisors in `Shipment.create` once a shipment was created, on the request as sent to the carrier, which is the swapped request for return shipments (823460f84).
- test(sdk): verify rate, shipment, and return shipment responses are unchanged when no advisor plugin is installed (a6dab1739).
- feat(server): persist the messages returned by shipment creation on the purchased shipment (53d5e45df).
- docs(sdk): document the shipment advisor contract with an example advisor-only plugin verified by a unit test (a91cc9995).
- docs(prd): add the shipment advisors PRD (73e555ac0).

## Behaviour changes

- Purchasing a label now stores the messages returned by shipment creation in the shipment's `messages`, merged with the messages stored at rating and de-duplicated by carrier id, code, and message (53d5e45df).
  This includes advisor messages and non-blocking carrier warnings that were previously dropped, such as `customs_omitted_intra_eu` from the PostNord and DHL Freight Sweden connectors, so API consumers may see additional warnings on purchased shipments.
- Plugins that declare shipment advisors report the plugin type `advisor`: an advisor-only plugin reports `advisor` instead of `unknown`, and a carrier or LSP plugin with advisors lists `advisor` among its `plugin_types` (dc2369fb3, c69e60f99).
