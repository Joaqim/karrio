# Tasks

## 1. Branch setup

- [x] 1.1 Run `docs/notes/workflow/develop-status.sh` and create worktree `.worktrees/feat-shipment-advisors` on a new branch `feat-shipment-advisors` from `upstream/main` with `git -c submodule.recurse=false worktree add`, and verify the worktree HEAD equals `upstream/main`
- [x] 1.2 Register `feat-shipment-advisors` in BRANCHES of `docs/notes/workflow/assemble-develop.sh` on docs-openspec immediately after `feat-tracker-locale` (upstream-bound, no fork dependencies), update `develop-assembly.md`'s branch listing, commit on docs-openspec, and verify `develop-status.sh` lists the branch as not yet contained

## 2. Plugin metadata and registry

- [x] 2.1 Add `shipment_advisors` (list, default empty) to `PluginMetadata` after `system_config` in `modules/sdk/karrio/core/metadata.py`, and report `advisor` in `plugin_types` when it is non-empty and as `plugin_type` for plugins that are neither carrier nor LSP, and verify unit tests for an advisor-only plugin (type `advisor`), a carrier plugin with advisors (types `carrier` and `advisor`), and a plugin without advisors (types unchanged)
- [x] 2.2 Add the `ADVISORS` registry of `(plugin_id, advisor)` pairs to `modules/sdk/karrio/references.py`, reset and filled in `import_extensions` beside `SYSTEM_CONFIGS`, with an uncached `get_advisors()`, and verify unit tests that register in-memory plugins through the discovery path and assert collection, reset on re-import, and that an advisor-only plugin is not listed as unknown in the references output

## 3. Advisor context and runner

- [x] 3.1 Create `modules/sdk/karrio/core/advisors.py` with an immutable `AdvisorContext` built from settings by allowlist (`carrier_name`, `carrier_id`, `account_country_code`, `test_mode`, `operation`, deep-copied `config`), and verify a unit test with a settings object carrying an API key, secret, `metadata`, and `id` asserting none of them is reachable from the context
- [x] 3.2 Implement `run_advisors(request, settings, operation)` passing each advisor a deep copy of the request, filling missing `carrier_name` and `carrier_id`, downgrading levels other than `info` and `warning` to `warning`, and converting a raising advisor into a `shipment_advisor_failed` warning naming the plugin while the remaining advisors still run, with the broad-exception rationale in the docstring, and verify unit tests for level downgrade, request isolation (a mutating advisor leaves the caller's request unchanged), failure isolation, and message identity filling

## 4. SDK invocation points

- [x] 4.1 Run advisors in `Rating.fetch` per gateway inside `flatten()` only when that gateway returned rates, and verify interface tests with MagicMock gateways asserting one advisor message per carrier for two rating gateways and none for a gateway that returned no rates or aborted
- [x] 4.2 Run advisors in `Shipment.create` after parsing only when shipment details are present, passing the request as sent to the carrier (the swapped copy for returns), and verify interface tests for a successful shipment (advisor warning alongside carrier messages, details unchanged), a failed shipment (no advisor message), and a return shipment (advisor sees the original recipient as shipper)
- [x] 4.3 Verify with a test that rate and shipment responses are identical to the pre-change output when no advisor plugin is installed, and run the SDK core suite

## 5. Server persistence

- [ ] 5.1 Merge the messages returned by shipment creation into `shipment.messages` in `buy_shipment_label` (`modules/manager/karrio/server/manager/serializers/shipment.py`), de-duplicated by carrier id, code, and message, and verify a Django test in the manager module that purchases a shipment through the API with a patched gateway returning a warning at shipment creation and asserts the purchased shipment's messages include it once alongside stored rate messages
- [ ] 5.2 Run `karrio test --failfast karrio.server.manager.tests` and `karrio.server.core.tests` in the nix dev shell, and verify both pass

## 6. Documentation, review, and integration

- [ ] 6.1 Document the advisor contract (signature, context fields, non-blocking and isolation rules, invocation points, persistence, example advisor-only plugin metadata) in the SDK plugin documentation under `apps/www` beside the existing plugin docs, and verify the example matches a passing unit-test fixture
- [ ] 6.2 Write `PRDs/SHIPMENT_ADVISORS.md` from `PRDs/TEMPLATE.md` on the feature branch, derived from this proposal and design (ASCII diagrams, existing-code analysis, file-level plan, testing strategy), and verify it covers every spec requirement
- [ ] 6.3 Write `changelog.md` in this change directory (features; the purchase-time message persistence noted as a behaviour change including carrier warnings such as `customs_omitted_intra_eu`), and verify each entry maps to a commit
- [ ] 6.4 Run the fresh-context review gate against the spec, design, PRD, and repository checklists (karrio.lib usage, functional style, the single documented broad exception, tests for every requirement, no secrets reachable by advisors), address findings, and verify the reviewer reports no blocking issue
- [ ] 6.5 Run `docs/notes/workflow/rebuild-develop.sh`, and verify it reports develop current with all BRANCHES tips contained and all suites passing
