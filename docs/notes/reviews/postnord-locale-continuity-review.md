# PostNord locale continuity — review gate

Reviewed commit range `1f945d44a..HEAD` on `postnord-locale-continuity` (six commits, 12 files, +196/−43) against `PRDs/POSTNORD_LOCALE_CONTINUITY.md`.

## Status: NEEDS CHANGES → remediated in-line (see "Remediation")

Original gate verdict: NEEDS CHANGES. All required actions were subsequently applied on the branch; the findings below are the original record.

Provenance caveat: subagent dispatch was unavailable in this session ("Not logged in" on three attempts), so the review ran inline in the same session lineage that produced the implementation. It is not the fresh-context gate the PRD launch criteria call for; re-run `/review-implementation` from a clean session if that property is required.

## Findings

1. [FAIL] Cross-carrier regression: `_merged_options` drops keyed per-number options (`modules/events/karrio/server/events/task_definitions/base/tracking.py:208`). The old `functools.reduce` merge forwarded keyed entries like `{"<tracking_number>": {...}}` into the `TrackingRequest`; the new helper drops them, and smartkargo's mapper reads exactly that shape (`modules/connectors/smartkargo/karrio/providers/smartkargo/tracking.py:152` — `options.get(tracking_number)` for `smartkargo_prefix`/`smartkargo_air_waybill`). Those keys are round-tripped by smartkargo's parse into `TrackingDetails.meta`, which `_save_results` writes back into the tracker's keyed slot — so scheduled polls previously did an exact prefix/Airwaybill lookup. After this change they fall back to the AWB regex or the `packageReference` search endpoint, a different query path. Mitigations: AWB-pattern numbers recover the same values from the regex; non-AWB refs still get the documented packageReference fallback. The PRD's inertness claim ("behavior identical to today" for other carriers, risk table and Q4) does not hold for keyed-shape consumers. Suggested fix: merge each group's options with the old reduce semantics (keep keyed entries) instead of filtering them out; per-group scoping means each request only carries its own members' keyed entries, which is exactly what the mappers read. No test guards keyed passthrough today — add one alongside the fix.
2. [FAIL] Missing PRD-promised tests: the Testing Strategy table lists `test_create_tracker_persists_request_language` (`test_trackers.py`) and `test_purchase_shipment_tracker_inherits_language` (`test_shipments.py`); neither exists (no `language`/`locale` occurrence in either manager test file). Phase 2 persistence — the inheritance in `create_shipment_tracker` and the update-path carry in `TrackingSerializer.update` — has zero direct test coverage; a regression there would silently revert scheduled polls to `en`. The remaining six promised tests exist, some under slightly different names (`test_create_shipment_locale_from_request` vs the PRD's `test_create_shipment_request_locale`, etc.), and the zpl/default cases are covered by updated URL assertions.
3. [WARN] PRD internal contradiction on the booking default: Q3 resolves the default to `en` and the code sends `locale=en` (verified by `test_create_shipment_pdf_url_by_default`), but the Resolved Decisions D3 row, the Field Mappings table, and the Backward Compatibility section still describe a `sv` default. The docs commit (4ccc720e1) updated the plan tables but left these three places stale.
4. [WARN] Failure-mode deviation from the PRD: the partition loop materializes all responses (`responses = [...]`) before any `_save_results` call, so an exception in partition 2 discards partition 1's successful fetch. The PRD's failure-mode table says "partial batch saved"; the implementation is all-or-nothing per batch. The direction is safe (trackers retry next cycle, no data corruption) but contradicts the PRD and wastes successful API calls. Fetching and saving per group would match the documented semantics and localize the blast radius of a single partition failure.
5. [WARN] Inaccurate docstring on `_merged_options`: it claims dropping keyed entries "avoids last-wins clobbering when several trackers share flat keys", but the dict comprehension still last-wins on flat-key conflicts within a group (same as the old reduce). If finding 1's fix removes the helper, this resolves itself.
6. [WARN] Style nits: `_key = lambda t: ...` assigns a lambda to a name (PEP 8 E731); a `def` one-liner or `operator.itemgetter`-style helper reads better. Cosmetic only.
7. [PASS] Connector booking locale (Phase 1): precedence `request options.language > config.language > "en"` is implemented in `create.py` with the `ConnectionConfig.language` option (`"en"` third-positional default matches the existing `label_type` pattern); query `locale` is lowercase, body `language` is uppercase; both zpl and pdf endpoints carry it via `request.ctx`; the request fixture asserts the body `"language": "EN"` element and the URL tests cover request/config/default precedence. The `or "en"` tail in `create.py` is redundant (the option default already yields `en`) but harmless.
8. [PASS] Poller partitioning for the target carrier: groups are keyed on the flat `options.language` (empty-string sentinel for unset), tracking numbers stay within their group, unset-language groups send no `language` key so the postnord mapper default applies, and uniform batches produce exactly one request — verified by the two new events tests. `_save_results` matches details to trackers within the group only; no cross-group misattribution.
9. [PASS] Manager persistence wiring: `create_shipment_tracker` adds the flat `language` key only when the shipment's value is truthy and leaves the keyed carrier entry untouched; `TrackingSerializer.update` carries persisted flat keys (excluding the tracker's own number) into the outgoing request without disturbing the keyed merge. Note (pre-existing, not a regression): caller-supplied flat keys on a tracker PUT are ignored, so a tracker's language cannot be changed via update — only at creation.
10. [PASS] PRD "already worked" claim verified: the server gateway echoes request options into `response.tracking.options` (`modules/core/karrio/server/core/gateway.py`, the `options = {**(payload.get("options") or {}), tracking_number: {...}}` merge), which `TrackingSerializer.create` persists — so API-created trackers keep their request language without further changes.
11. [PASS] Generated-file consistency: `schemas/shipment_request.json` gained the `"language": "EN"` example key and the generated `karrio/schemas/postnord/shipment_request.py` gained the matching `language: typing.Optional[str] = None` field in the same position; `mapper.py` untouched. Positionally consistent with `./bin/run-generate-on` output (idempotency not re-verified by regeneration).
12. [PASS] Migration safety and security: no migrations added and none needed (`Tracking.options` is a `PlainDictField`); locale travels only through `lib.to_query_string` (encoded) and a JSON body field; no secrets, no tenant-scoping changes, no new input surfaces.

## Required actions

- Fix `_merged_options` to preserve keyed per-number options within each locale group (restores smartkargo parity), and add a keyed-passthrough test to the events suite.
- Add the two missing manager tests from the PRD Testing Strategy table (tracker create persists request language; purchase inherits shipment language).
- Reconcile the PRD's D3 row, Field Mappings table, and Backward Compatibility section with the implemented `en` default.
- Optional: restructure `_process_batch` to fetch and save per partition to match the PRD's partial-save failure semantics; drop the `_key` lambda.

## Remediation

All required actions from this review were applied on the same branch:

- Finding 1 fixed in 3e22731 — `_merged_options` restored the reduce merge (keyed entries kept, scoped per locale group) and `_process_batch` now fetches and saves one partition at a time, localizing failures to the partitions after the failing one (also addressing finding 4). The lambda-to-def cleanup (finding 6) went in with it. New `test_process_carrier_trackers_keeps_keyed_options` guards the passthrough.
- Finding 2 fixed in a093da9 — `test_create_tracker_persists_request_language` (serializer-level, since the REST create views hardcode `options={}`) and `test_purchase_shipment_tracker_inherits_language` added with the PRD-promised names.
- Finding 3 fixed — PRD D3 row, Desired State snippet, Field Mappings table, and Backward Compatibility section now state the implemented `en` default with the `sv` divergence note.
- Finding 5 resolved structurally — `_merged_options` was rewritten around the reduce and its docstring now describes actual behavior.

## Test evidence

| Suite | Command | Result |
|---|---|---|
| postnord connector | `python -m unittest discover -f modules/connectors/postnord/tests` | 44/44 OK |
| events tracking tasks | `karrio test karrio.server.events.tests.test_tracking_tasks` | 8/8 OK → 9/9 after remediation |
| manager trackers | `karrio test karrio.server.manager.tests.test_trackers` | 5/5 OK → 6/6 after remediation |
| manager shipments | `karrio test karrio.server.manager.tests.test_shipments` | 43/43 OK → 44/44 after remediation |

Counts match the PRD Appendix B verification log. Note that green suites do not exercise findings 1 or 2 — that is precisely the coverage gap being reported.
