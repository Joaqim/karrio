# Tasks

## 1. Branch rebuild

- [ ] 1.1 Run `docs/notes/workflow/develop-status.sh --fetch`, tag the current head of `fix-state-code-normalization` (`7660b0a71`) as `backup/fix-state-code-normalization-pre-rework`, and verify the tag resolves to that commit
- [ ] 1.2 In `.worktrees/fix-state-code-normalization`, reset the branch to `fix-fedex-state-code-countries` with `git -c submodule.recurse=false reset --hard`, and verify `git log upstream/main..HEAD` shows only `7f7ba626b` and `modules/core/karrio/server/core/validators.py` matches `upstream/main`

## 2. SDK resolver

- [ ] 2.1 Add `Location.as_state_code` to `modules/sdk/karrio/core/utils/helpers.py` and `to_state_code(value, country, **kwargs)` next to `to_state_name` in `modules/sdk/karrio/lib.py`, matching as in design.md (`CC-` prefix, code match, accent- and case-folded names with one trailing `state`/`province`/`county`/`region` word removed, ambiguous and unmatched values unchanged, per-country lookups cached)
- [ ] 2.2 Add SDK unit tests covering every scenario of `specs/addresses/state-codes` "SDK resolves subdivision names to codes" (California to `CA`, quebec and Québec to `QC`, ny and US-NY to `NY`, SE name unchanged, Atlantis unchanged, missing value), and verify they fail before 2.1 and pass after with `python -m unittest discover -v -f modules/sdk/tests` in the nix dev shell from the worktree
- [ ] 2.3 Commit as `fix(sdk): resolve subdivision names to state codes` and verify `./bin/run-sdk-typecheck` exits 0

## 3. FedEx connector

- [ ] 3.1 Change `provider_utils.state_code` in `modules/connectors/fedex/karrio/providers/fedex/utils.py` to gate on `STATE_CODE_COUNTRIES`, resolve through `lib.to_state_code`, then map `QC` to `PQ`
- [ ] 3.2 Add FedEx rate and shipment tests for a US recipient with state "New York" (sent as `NY`) and a Canadian address with state "Québec" (sent as `PQ`), following the existing fixture pattern in `test_rate.py` and `test_shipment.py`, and verify they fail before 3.1 and pass after with `python -m unittest discover -v -f modules/connectors/fedex/tests`
- [ ] 3.3 Commit as `fix(fedex): send state names as subdivision codes`
- [ ] 3.4 Cherry-pick `7660b0a71` (pickup create and update through `provider_utils.state_code`) with `git -c submodule.recurse=false cherry-pick`, and verify its pickup tests and a Swedish pickup address without `stateOrProvinceCode` pass in the FedEx suite

## 4. Integration checks

- [ ] 4.1 Run the SDK suite, the FedEx and DHL Express connector suites, and `karrio.server.core.tests` and `karrio.server.manager.tests` through `server-tests-overlay.sh`, and verify all pass with `git diff upstream/main...HEAD -- modules/core` empty
- [ ] 4.2 Push `fix-state-code-normalization` with `--force-with-lease`, rewrite PR #1141's title to `fix(fedex): send state names as subdivision codes` and its body in the Fix PR format (Bug, Root Cause, Fix, Tests) stating the dependency on #1143 and the removal of the server-side rewrite, and verify with `gh pr view 1141 -R karrioapi/karrio`

## 5. Fork develop

- [ ] 5.1 On docs-openspec, move `fix-fedex-state-code-countries` before `fix-state-code-normalization` in `BRANCHES` of `docs/notes/workflow/assemble-develop.sh`, update the branch listing in `develop-assembly.md` if it states the order, commit, and verify `assemble-develop.sh` produces `develop-next` without conflicts
- [ ] 5.2 Verify on `develop-next` that creating an address with `country_code` `SE` and `state_code` "Västra Götaland" through the manager API returns the state unchanged, then hand the develop push to the user
