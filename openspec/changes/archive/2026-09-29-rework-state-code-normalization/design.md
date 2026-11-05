## Context

`fix-state-code-normalization` (#1141) carries two commits on `upstream/main`: `b3dd30a79` adds `normalize_state_code` to `modules/core/karrio/server/core/validators.py` and calls it from `AugmentedAddressSerializer.validate`, and `7660b0a71` routes FedEx pickup create and update through `provider_utils.state_code`.
`fix-fedex-state-code-countries` (#1143) carries one commit, `7f7ba626b`, that adds `STATE_CODE_COUNTRIES` to `modules/connectors/fedex/karrio/providers/fedex/utils.py` and makes `state_code` return `None` outside it.
Both branches have worktrees under `.worktrees/`, both PRs are open and unreviewed, and `assemble-develop.sh` currently lists #1141's branch before #1143's.

The SDK already has the reverse lookup: `lib.to_state_name(value, country)` wraps `utils.Location(...).as_state_name`, which reads `units.CountryState`.
`units.CountryState` lists AE, AU, CA, CN, IN, MX and US, and is exported through `/v1/references` as `states`; the dashboard address form (`packages/ui/components/address-form.tsx:157`) makes the state required for every country listed there.

## Goals / Non-Goals

**Goals:**

- The server stores the state as submitted, as on `upstream/main`.
- A connector can derive a subdivision code from a stored state by calling one SDK function, and FedEx does so.

**Non-Goals:**

- Applying the resolver in connectors other than FedEx; other connectors can opt in later in their own changes.
- Subdivision data for countries outside `units.CountryState`, including the Nordic countries.
- Changing `/v1/references` or the dashboard state picker.

## Decisions

### Resolver is `lib.to_state_code`, backed by `Location.as_state_code`

The resolver sits next to `to_state_name` in `modules/sdk/karrio/lib.py` with the same signature, `to_state_code(value, country, **kwargs)`, and delegates to a new `Location.as_state_code` property in `modules/sdk/karrio/core/utils/helpers.py`.
This mirrors an existing pair, so upstream reviewers see a familiar shape, and connectors reach it through `import karrio.lib as lib` as the project conventions require.

Alternatives considered: resolving inside `ComputedAddress.state_code` would change the value every connector sees and reintroduce the "one shape for all carriers" problem one layer lower; a FedEx-local helper would not be reusable by DHL Express or UPS, which also send state codes.

### Resolver data comes only from `units.CountryState`

The Nordic table from `b3dd30a79` is dropped, not moved.
After #1143 no connector consumes Nordic region codes, and adding the Nordic countries to `units.CountryState` would make the dashboard require a state for them through the `isStateRequired` coupling.

### Matching keeps the useful subset of #1141's algorithm

The value is stripped, an ISO `CC-` prefix for the given country is removed, and an exact case-insensitive code match wins.
Otherwise names are compared after NFD accent folding and casefolding, with one trailing `state`, `province`, `county` or `region` word removed from both sides; lookups are built once per country and cached.
A name that maps to more than one code is not resolved.

Dropped from #1141: the `ø`/`æ` translation, the `län`/`fylke`/`maakunta`/`lääni` suffixes, the `Region ` prefix, the trailing-`s` and `ae`-to-`e` variants, all of which served only Nordic names, and the `PQ` to `QC` alias, because FedEx is the only consumer and it sends `PQ` either way.

### FedEx order of operations is gate, resolve, map

`provider_utils.state_code` returns `None` when the state is empty or the country is outside `STATE_CODE_COUNTRIES`, then resolves the state with `lib.to_state_code`, then applies the existing `QC` to `PQ` mapping to the resolved value.
Gating first keeps #1143's behaviour intact, and mapping after resolution lets "Québec" reach FedEx as `PQ`.

### #1141 is rebuilt on top of #1143

Both PRs now change the body of `provider_utils.state_code`, so an independent base would conflict.
`fix-state-code-normalization` is rebuilt from `fix-fedex-state-code-countries` with three commits:

1. `fix(sdk): resolve subdivision names to state codes` adds `Location.as_state_code`, `lib.to_state_code` and SDK tests.
2. `fix(fedex): send state names as subdivision codes` changes `provider_utils.state_code` and adds FedEx rate and shipment tests.
3. `fix(fedex): route pickup addresses through state code helper`, the existing `7660b0a71` cherry-picked with its tests, extended with a Québec-by-name pickup case if it fits the existing fixture.

`b3dd30a79` is not carried over, so `validators.py` and the manager tests match `upstream/main`.
Both PRs are opened from the fork against upstream `main`, so #1141's diff shows #1143's commit until #1143 merges; the PR body states the dependency.
The PR is retitled `fix(fedex): send state names as subdivision codes`, since the SDK function exists to serve that fix.

Alternatives considered: folding the resolver into #1143 would grow a small, self-contained fix; closing #1141 and opening a new PR would discard its number for no gain, as it has no reviews.

### No new server test

`upstream/main` already stores the state as submitted, and the rebuilt branch has no `modules/core` diff.
The "stored as entered" requirement is verified by running the existing `karrio.server.manager.tests` on the rebuilt branch and by a spot check against the dev API, not by a new upstream test that would add a `modules/core` diff to a FedEx PR.

## Risks / Trade-offs

- [Addresses on the dev deployment already hold codes such as `O`] → FedEx drops the state for Sweden, and other carriers receive what is stored; the user corrects affected addresses in the dashboard, and no migration is written.
- [A name shared by two subdivisions, or a typo, is sent to FedEx unchanged and may be rejected] → the same outcome as `upstream/main`, and the FedEx error surfaces in the rate or shipment messages.
- [Stacked fork PRs show a combined diff upstream] → the #1141 body names #1143 as a prerequisite, and the diff narrows once #1143 merges.
- [Force-pushing #1141 rewrites its history] → the PR has no reviews or review comments, so no discussion is detached; the old head is kept as a tag before the rebuild.

## Migration Plan

1. Tag the current head of `fix-state-code-normalization` as a backup, then rebuild the branch in its worktree from `fix-fedex-state-code-countries`.
2. Run the SDK, FedEx and manager test suites on the rebuilt branch.
3. Force-push the branch with `--force-with-lease` and rewrite the #1141 title and body.
4. Swap the order of the two branches in `BRANCHES`, reassemble develop, and leave the develop push to the user.

Rollback restores the branch from the backup tag and reverts the `BRANCHES` order.
