# PostNord country locale — fresh-context review gate

Reviewed commit range `develop..HEAD` on `postnord-country-locale` (14 commits, 16 files, +1175/−26) against `PRDs/POSTNORD_LOCALE_CONTINUITY.md` and `PRDs/POSTNORD_COUNTRY_LOCALE.md`.

## Status: PASS

Provenance: dispatched as a fresh-context `code-reviewer` subagent with no implementation context, satisfying the launch criterion the previous gate could not (see the caveat in `postnord-locale-continuity-review.md`). The reviewer independently re-ran schema generation and all four suites and reconciled counts against develop baselines.

## Findings

1. [PASS] Booking locale precedence chain implemented per both PRDs (`modules/connectors/postnord/karrio/providers/postnord/shipment/create.py:157-166`): `options.language` > `config.language` > `CountryLocale.lookup` (gated on `config.locale_by_recipient`) > `"en"`. Query `locale` lowercase (`proxy.py:119`), body `language` uppercase (`create.py:211`), threaded via ctx (`create.py:278`). Country-tier reachability confirmed by direct probe: the third positional of `lib.OptionEnum("language", str, "en")` is the *state*, not a default (`modules/sdk/karrio/core/utils/enum.py:112-128`), so `.state` is `None` when unset and the `or "en"` tail is load-bearing. This corrects finding 7 of the prior review record, which called that tail redundant.
2. [PASS] `CountryLocale` handles the DK/DA trap and case normalization (`units.py:71-83`): probed `lookup("DK")→"da"`, `lookup("se")→"sv"`, `lookup("DA")→None`, `lookup(None)/lookup("")→None`, unmapped countries fall to `en`.
3. [PASS] Poller partitioning preserves keyed per-number options and saves per partition (`modules/events/karrio/server/events/task_definitions/base/tracking.py:209-219, 239-244, 246-261`), guarded by `test_process_carrier_trackers_keeps_keyed_options`.
4. [PASS] Manager materialization and inheritance (`modules/manager/karrio/server/manager/serializers/shipment.py:698-708, 920-942, 1011-1019`): derived locale materialized onto `shipment.options` before request build and tracker creation, gated by `_recipient_country_locale` which defers to `config.language` and restricts to `carrier_name == "postnord"`. Tracker PUT preserves locale (`serializers/tracking.py:115-133`, gateway echo at `modules/core/karrio/server/core/gateway.py:541-546`).
5. [PASS] All remediation claims from `postnord-locale-continuity-review.md` hold in the final code as enumerated.
6. [PASS] Schema regeneration idempotent: regenerated `karrio/schemas/postnord/shipment_request.py` is byte-identical to the committed file; no hand-edit drift; `mapper.py` untouched.
7. [PASS] Code quality, Django patterns, security: `karrio.lib as lib` throughout, no bare exceptions or mutable defaults added, no migrations needed (JSONField options), no N+1 regression (partitioning is in-memory over the fetched batch), tenant scoping untouched, apikey-in-query is PostNord's documented auth model.
8. [WARN] Two stale `sv`-default statements remain in `PRDs/POSTNORD_LOCALE_CONTINUITY.md` (line 275 sequence diagram, line 421 Testing Strategy); the implemented and tested default is `en` everywhere.
9. [WARN] Tracing records duplicate across partitions in a mixed-locale batch: `tracking.py:260` saves tracing per group but `Tracer.inner_recordings` is never drained between `bulk_save_tracing_records` calls (`modules/sdk/karrio/core/utils/tracing.py:384,429,457-461`), so earlier partitions' records re-persist on each subsequent save. Observability noise only; single-partition batches unchanged. Suggested fix: drain records after each save.
10. [WARN] A non-string `options.language` (hand-crafted API payload; `PlainDictField` does not enforce inner types) raises `TypeError` in the poller's `sorted(batch, key=_locale_key)` (`tracking.py:236-242`), stalling the whole ≤10-tracker batch each cycle, and `AttributeError` in booking's `locale.upper()` (`create.py:211`). No in-repo producer; PRD defers client-side validation. Suggested guard: `str()`-coerce in `_locale_key`.
11. [WARN] `PRDs/POSTNORD_COUNTRY_LOCALE.md` records 49/49 connector tests (branch runs 56), and its line 126 re-derivation claim does not hold after a failed purchase materializes `options.language` and the recipient is then changed before retry.
12. [WARN] Pre-existing, out of scope: REST tracker creation views hardcode `options={}` (`modules/manager/karrio/server/manager/views/trackers.py:131-134`), so request-language persistence is reachable only via serializer/GraphQL. Cosmetic nit: double blank line at `test_shipment.py:162-163`.

## Required actions

None — status PASS. Findings 9 and 10 are small hardening commits; 8 and 11 are doc corrections.

## Test evidence

| Suite | Command | Result |
|---|---|---|
| postnord connector | `python -m unittest discover -f modules/connectors/postnord/tests` | 56 OK (develop baseline 49) |
| manager shipments | `karrio test karrio.server.manager.tests.test_shipments` | 45 OK |
| manager trackers | `karrio test karrio.server.manager.tests.test_trackers` | 6 OK |
| events tracking tasks | `karrio test karrio.server.events.tests.test_tracking_tasks` | 9 OK |

Module import paths confirmed resolving to this working tree (not a stale main-checkout per the known shared-venv pinning hazard).
