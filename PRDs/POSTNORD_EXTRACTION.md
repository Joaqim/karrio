# PostNord connector extraction to standalone plugin repo

| Field | Value |
|-------|-------|
| Project | Karrio fork |
| Version | 1.0 |
| Date | 2026-10-13 |
| Status | In progress |
| Owner | Joaqim Planstedt |
| Type | Architecture |
| Reference | [PRD_POSTNORD_INTEGRATION.md](./PRD_POSTNORD_INTEGRATION.md), [POSTNORD_CN22_STAMPING.md](./POSTNORD_CN22_STAMPING.md), [POSTNORD_CUSTOMS_BOOKING_DOCUMENTS.md](./POSTNORD_CUSTOMS_BOOKING_DOCUMENTS.md), [POSTNORD_SERVICE_POINT_BOOKING.md](./POSTNORD_SERVICE_POINT_BOOKING.md) |

The four reference PRDs ride the postnord branches: they are present in the assembled develop union and leave develop with the branches in Phase 4.

---

## Executive summary

This PRD covers extracting the `postnord` connector from the fork monorepo (`modules/connectors/postnord`, a 10-branch family in the develop assembly) into the standalone public repository `PrimePack-AB/karrio-postnord`, repairing the branch-family divergence, and completing the standalone-plugin switchover for both postnord and dhl_freight_sweden.
Unlike the DHL Freight Sweden extraction, whose fork-side switchover was deferred, this change executes the switchover in the same effort: a two-deploy sequence removes the in-tree copy only after the standalone plugin is mounted and verified inert, so production never spends a moment without postnord.
The extraction also repairs a semantic loss: the develop union silently dropped the letter-service opt-in gates, cf7ad467a (2026-10-08) then dropped them deliberately, and this change re-instates them as the connector's first standalone behavior — knowingly changing default rate results at the final deploy.

### Key decisions

1. Repo: `PrimePack-AB/karrio-postnord`, public, LGPL-3.0.
2. Fork-coupled SDK: the package depends on plain `karrio` plus a documented fork-SDK floor; upstream karrio cannot import the plugin.
3. Seed: the develop union `65468d813` with the `offer_*` gates re-instated.
4. History: a single root import, not filter-repo preservation; the fork retains the provenance.
5. Switchover: both connectors, two deploys, no coverage window.
6. CI: one workflow testing against a pinned public fork SDK SHA.
7. dev is wired to the standalone plugins before the develop push.

### Scope

| In scope | Out of scope |
|----------|--------------|
| Standalone repo scaffold (74-file byte-fidelity seed) | Publishing to PyPI |
| Divergence repair: `offer_*` opt-in gates re-instated; EU VAT verification by test-run | Sandbox evidence suite (deferred; offline tests only at extraction) |
| Docs migration, Starlight docs site, agent conventions, CI against the pinned fork SDK | Service narrowing; upstream `community/` contribution (fork-coupled, decision 1) |
| Fork branch removal and develop rebuild | n8n python env change (stays without postnord) |
| Plan-repo packaging (npins, overlay, extraPlugins), dev wiring, two-phase deploy with verification gates, DHL debt retirement (rides Gate U2) | |

---

## Decisions

All decisions are locked as of 2026-10-13.

| # | Decision | Choice | Date |
|---|----------|--------|------|
| 1 | SDK dependency | Fork-coupled: pyproject keeps `dependencies = ["karrio"]` (no pip-solvable fork ref exists) plus a TOML/README fork-SDK floor note; dev and test run `-e ../karrio/modules/sdk`. Upstream karrio cannot import the plugin (fork-only `PluginMetadata` fields). | 2026-10-13 |
| 2 | Seed | develop union `65468d813`, `offer_*` gates re-instated (confirmed 2026-10-13, knowingly reversing cf7ad467a's 2026-10-08 drop; Deploy B changes default rate results — risk R4); EU VAT verified by test-run, the code already being correct on develop. | 2026-10-13 |
| 3 | Switchover | Both connectors this time; postnord branches leave BRANCHES; develop drops the in-tree copy; two-deploy sequence; the DHL debt is retired. | 2026-10-13 |
| 4 | Repo | `PrimePack-AB/karrio-postnord`, public, LGPL-3.0. | 2026-10-13 |
| 5 | History | Single root import (a conscious divergence from the DHL extraction's filter-repo preservation; the union's 119 commits carry gate-add/gate-drop noise; the fork retains provenance; this PRD documents the mapping). | 2026-10-13 |
| 6 | Test CI | Yes: one workflow with the fork SHA pinned as a variable (possible because Joaqim/karrio is public; `modules/sdk` installs without private submodules). | 2026-10-13 |
| 7 | dev | Wire dev to consume the standalone plugins before the Gate-U3 develop push; dev never loses postnord. | 2026-10-13 |

### Riding defaults

| Default | Resolution |
|---------|------------|
| Sandbox tests | Suite deferred; offline tests only at extraction. |
| Version | Bump to 2026.10 in the repair commit (C8). |
| Connector notes | Copy and stay: the fork keeps its copies (DHL precedent); the eori-vat checkpoint note stays fork-side only. |
| n8n python env | Stays without postnord (it never had it). |

---

## Problem statement

### Current state

The connector lives in the fork monorepo as a 10-branch family (BRANCHES lines 48-57 of `docs/notes/workflow/assemble-develop.sh`), assembled into the generated `develop` branch as a 74-file tree under `modules/connectors/postnord` carrying 119 commits of history.
The family diverged internally during September-October 2026.
The develop union silently lost the letter-service opt-in gates — a semantic union loss — which cf7ad467a then made deliberate on 2026-10-08 (`fix(postnord): drop opt-in gates for letter services`).
Ten of the 25 assembly branches exist to serve one connector that upstream will never take in-tree.
The DHL Freight Sweden extraction (2026-10-03) established the standalone-plugin pattern and the deployment's plugin-consumption mechanism, but its plan-side wiring is complete yet unpushed.

### Desired state

The connector moves to the public standalone repository `PrimePack-AB/karrio-postnord` with the divergence repaired (opt-in gates restored), the deployment consumes both postnord and dhl_freight_sweden solely as standalone plugins, and the fork's develop assembly drops the 10 postnord branches, the in-tree connector copies, and the riding manifests — sequenced so production never loses postnord.

### Problems

1. **Divergence and semantic union loss**: the assembled develop rates letter services differently than any single branch intends going forward; the gates must be restored deliberately, not by accident of assembly.
2. **Branch load**: 10 of 25 BRANCHES entries serve one connector; every connector fix re-parents a stack.
3. **No standalone lifecycle**: the connector cannot be versioned or consumed outside the fork's develop assembly.
4. **DHL debt**: the completed plan-side wiring for the DHL switchover sits unpushed; this change retires it in the same sequence.

---

## Goals and success criteria

### Goals

1. Public `PrimePack-AB/karrio-postnord` seeded byte-identical from the develop union, gates repaired, standalone suite and CI green.
2. The deployment consumes postnord and dhl_freight_sweden solely as standalone plugins, verified across two gated deploys with no coverage window.
3. The fork's develop assembly drops the postnord branches with the rebuild diff exactly enumerated.
4. dev serves postnord from the plugin before the develop push lands.

### Success criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Seed fidelity | 74 files byte-identical to the `65468d813` tree at C1 | Must-have |
| Standalone suite | green from the repo root, including the three letter-gating tests, the eori-vat fallback/precedence/guard/misplaced tests, and the Monaco/Mount Athos/NI territory cases | Must-have |
| CI | workflow green against the pinned fork SDK SHA | Must-have |
| Rebuilt develop diff | exactly the enumerated removals — 74 connector files, 4 postnord PRDs, 2 requirements lines, develop-assembly.md edits — plus this PRD arriving via docs-openspec | Must-have |
| Deploy A inertness | `/v1/references` postnord identical before and after; plugin mounted at `/var/lib/karrio-plugins/postnord` | Must-have |
| dev continuity | dev serves postnord from the plugin before Gate U3 | Must-have |
| Deploy B correctness | postnord present solely from the plugin; `POSTNORD_ENABLED` auto-seeded; services 34/UX absent with default config, present with toggles (Z12 connection for UX) | Must-have |

---

## Alternatives considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Single root import | Clean public history free of gate-add/gate-drop noise | No in-repo provenance | **Selected** |
| filter-repo history preservation (DHL precedent) | 119 commits of live-verified provenance ride along | The union history carries the noise the repair exists to fix; the fork retains provenance anyway | Rejected |
| Both-connectors switchover now | Retires the DHL debt; one deployment sequence | More moving parts per change | **Selected** |
| PostNord-only switchover, DHL deferred | Smaller change | Leaves the completed DHL wiring unpushed indefinitely | Rejected |
| Two-deploy sequence | No coverage window; inert-mount verification | Two user gates instead of one | **Selected** |
| Single-deploy switchover | One gate | A window where postnord exists only via an unverified mount, or not at all | Rejected |
| Upstream `community/` contribution | Upstream maintenance | Fork-only `PluginMetadata` fields make the plugin unimportable by upstream karrio | Rejected |

### Trade-off analysis

The history decision is the deliberate divergence from the DHL precedent: the union's 119 commits record both the gate addition and the gate drops that this change reverses, so importing them would publish a narrative the repaired connector supersedes.
Provenance is not lost — the fork keeps the branch family (renamed, not deleted) and this PRD fixes the seed mapping (`65468d813` tree, byte-identical) — but the standalone repo starts from a single root commit citing the union SHA.
The switchover decision follows the DHL extraction's own deferred-debt lesson: splitting extraction from switchover left six complete-but-unpushed commits, so this change executes both in one gated sequence.

---

## Technical design

### Existing code analysis

| Component | Location | Reuse strategy |
|-----------|----------|----------------|
| Connector tree | `modules/connectors/postnord/` at `65468d813` — 74 files: tests 22, providers 18 (10 core + pickup 4 + shipment 4), schemas 17 (9 generated .py + 8 .json sources), vendor 9, mappers 4, plugins init 1, README/generate/pyproject 3 | Seeded via `git archive`; C1 byte-fidelity gate |
| Discovery chain | `modules/sdk/karrio/references.py:42` — `import_extensions()`, four-tier priority, already-registered names skipped | Consumed as-is; the tier order makes Deploy A inert and Deploy B atomic |
| Develop assembly | `docs/notes/workflow/assemble-develop.sh` — BRANCHES lines 48-57 hold the 10 postnord branches (of 25) | F2 deletes lines 48-57 |
| Rebuild with auto-derived tests | `docs/notes/workflow/rebuild-develop.sh:80-84` derives the differing connectors; `:118-121` runs their suites | The post-removal rebuild must show postnord absent from the differing list |
| Deployment plugin consumption | `~/projects/plan/modules/clan/services/karrio/flake-module.nix:85-87` — `extraPlugins` option, default `{ inherit nordic_conventions dhl_freight_sweden; }`, bind-mounted read-only into `/var/lib/karrio-plugins` and scanned via `KARRIO_PLUGINS` | P2 adds postnord to the default |
| Overlay packaging | `~/projects/plan/modules/nixpkgs/overlays/karrio.nix:39-59` — `karrio-dhl-freight-sweden` buildPythonPackage entry | P2 mirrors the entry for `karrio-postnord` |
| Pins | `~/projects/plan/npins/sources.json` — `dhl_freight_sweden` at line 16, `karrio` at line 29 (currently `65468d813`, the seed commit) | P1 adds the postnord pin; P3 advances the karrio pin |
| Requirements manifests | `requirements.sdk.dev.txt:27` (`-e ./modules/connectors/postnord`), `source.requirements.txt:74` (`karrio_postnord @ file://${PWD}/modules/connectors/postnord`) | Auto-vanish with the branches |
| Riding PRDs | the four reference PRDs linked in the header | Leave develop with the branches; enumerated in the rebuild-diff gate |
| Extraction precedent | `PRDs/DHL_FREIGHT_SWEDEN_EXTRACTION.md`; `~/projects/nordic_conventions` lifecycle | Packaging, repo conventions, and gate sequencing mirror both |

### Registration priority

Why the sequencing works — `modules/sdk/karrio/references.py:42`:

```
import_extensions()
  ├─ (1) karrio.plugins entry points        ─┐ higher priority
  ├─ (2) karrio.plugins namespace scan       │ skips already-
  ├─ (3) karrio.mappers legacy scan          │ registered names
  └─ (4) KARRIO_PLUGINS directory scan      ─┘
       in-tree connectors reach (2) via nix PYTHONPATH glob modules/connectors/*/
       standalone plugins reach (4) via extraPlugins bind-mount /var/lib/karrio-plugins
```

### Deployment sequence

No-coverage-window elimination:

```
      GATE-U2                                GATE-U3                GATE-U4
prime ─── Deploy A ────┐   fork: BRANCHES removal,  ┌── Deploy B ───► plugin is the
   in-tree postnord    │   rebuild develop (no      │   npins karrio   ONLY postnord;
   serves (namespace   │   in-tree postnord),       │   pin advanced   gates LIVE:
   scan wins); plugin  │   push develop ────────────┘   (atomic swap)   34/UX hidden
   mounted but INERT   │   (also deploys dev — dev wired first)           unless toggled
```

Service codes 34 (tracked letter) and UX (export letter) are the gated letter services.

---

## Edge cases and failure modes

### Edge cases

| Scenario | Expected behavior | Handling |
|----------|-------------------|----------|
| Rebuilt develop diff shows anything beyond the enumerated set | Stop; do not promote | The enumeration is the gate; extras mean peer state or a wrong base (R8) |
| Deploy A changes `/v1/references` or any behavior | Stop | Any change falsifies the discovery-priority assumptions (R7) |
| A production connection relies on ungated 34/UX | Missing rate services after Deploy B | Pre-Deploy-B check of prime connections (R4); enable the toggles or use a Z12-issuer connection |
| Tests run outside the standalone repo root | Phantom results from main-checkout code | Run from the repo root with the fork SDK editable-installed (R9) |
| Live keys surface in ported notes | Public leak | Redaction pass before C9; `.env` gitignored; live keys never committed (R3) |
| PostNord spec terms disfavor redistribution | Public vendor/ blocked | 10-minute terms check before Gate U1; fallback strips vendor/ from the public repo (R1) |

### Failure modes

| What can go wrong | Impact | Mitigation |
|-------------------|--------|------------|
| A semantic union loss rides a future rebuild | Wrong behavior on develop | The branch family is retired by this change; the standalone repo has one history |
| An extraPlugins key collides with a community plugin name | nix evaluation failure | The flake's collision assertion (flake-module.nix:394-404) must not trip; eval gates in Phase 5a |
| The vendored spec snapshot drifts from the live API | Stale schemas | Noted in the standalone CLAUDE.md current-state ledger (C12, R10) |
| The karrio pin advances past the removal before dev is wired | dev loses postnord | Decision 7 ordering: dev wiring precedes Gate U3 |

---

## Implementation plan

Phases are numbered as in the approved plan; execution order is P0 → P1 → P2 → P3 → Gate U1 → P5a → Gate U2 → P5b → P4 → Gate U3 → P5c → Gate U4 → P5d → P4e.
Commit prefixes name their target repo: C-numbered commits land in the standalone repo, F-numbered in the fork, P-numbered in the plan repo.

```
P0 PRD → P1 scaffold → P2 repair+green → P3 docs → GATE-U1 (create repo, push)
      → P5a plan-repo changes + eval gates → P5a-dev dev wiring → GATE-U2 (push plan, Deploy A)
      → P5b Deploy A verify (inert) → P4 fork switchover (rebuild, promote)
      → GATE-U3 (push docs-openspec, vendored-specs, force-with-lease develop)
      → P5c npins pin advance → GATE-U4 (push plan, Deploy B) → P5d verify → P4e cleanup
```

### Phase 0: PRD (docs-openspec)

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| This PRD | `PRDs/POSTNORD_EXTRACTION.md` | Completed 2026-10-13 | S |

### Phase 1: Scaffold (~/projects/karrio-postnord, local only)

Seed from the git tree, never the working dir (untracked `__pycache__`/egg-info residue): `git -c submodule.recurse=false archive 65468d813 modules/connectors/postnord | tar -x -C ~/projects/karrio-postnord --strip-components=3`, then `git init -b main`.

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| C1 `feat(postnord): add connector from the fork develop union (65468d813)` | 74 files, byte-identical | Pending | M |
| C2 `chore: adapt packaging for the standalone repository` | pyproject: authors PrimePack AB, homepage, `packages.find include ["karrio*"]`, `exclude-package-data "*"=["__init__.pyi"]`; version stays 2026.6 until C8 | Pending | S |
| C3 `chore: point the generate script at the karrio monorepo checkout` | generate: bare `kcli` → `"${ROOT}/bin/cli"` | Pending | S |
| C4 `chore: add the karrio namespace pyright markers` | five empty `karrio/*/__init__.pyi` + pyrightconfig.json (extraPaths `../karrio/modules/sdk`, py3.12) | Pending | S |
| C5 `chore: add development scaffolding` | .gitignore (the DHL repo's), LICENSE (byte-copy of the fork root LICENSE), requirements-dev.txt = `-e ../karrio/modules/sdk` with fork-coupling comment | Pending | S |
| C6 `docs: extend the readme for standalone installation and development` | README.md: install via git URL, fork-SDK-floor paragraph, dev/venv/unittest/generate sections; `.env` (gitignored) copied from the fork `.env` POSTNORD_* keys — live keys never committed (R3) | Pending | S |
| C13 `ci: test the connector against the pinned fork sdk` | workflow: checkout plugin + Joaqim/karrio (submodules false) at the pinned SHA variable; `pip install -e modules/sdk -e .`; `python -m unittest discover -f -s tests` | Pending | S |

### Phase 2: Divergence repair

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| C7 `feat(postnord): restore the offer opt-in gates for letter services` | manual reverse-port of cf7ad467a's connector hunks, citing cf7ad467a in the body plus the rationale note (gates restored per the 2026-10-13 decision, superseding cf7ad467a for 34/UX); hunk inventory below | Pending | M |
| C8 `chore: bump version to 2026.10` | pyproject — the first public state carries a behavior change vs the union | Pending | S |

C7 hunk inventory:

| File | Changes |
|------|---------|
| `karrio/providers/postnord/units.py` | ConnectionConfig `offer_tracked_letter`/`offer_export_letter` default false; `ServiceAvailabilityRule.required_config`; both SERVICE_AVAILABILITY entries including `allowed_issuer_codes={Z12}` for export letter; 3-arg fail-closed `is_service_available`; gated letter-products comment |
| `karrio/mappers/postnord/settings.py` | connection_config passthrough |
| `tests/postnord/fixture.py` | `gateway_letters_off`, `gateway_letters_on`, `gateway_z11` |
| `tests/postnord/test_rate.py` | three gating tests; default-catalog serviceCodes assertion without 34/UX (the other letters stay offered — mainline semantics) |
| `README.md` | two connection-config rows, edited from develop's README directly to resolve the adjacency conflict |

### Phase 3: Docs migration

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| C9 `docs: port the connector working notes from the fork` | the 12 connector-facing notes from `docs/notes/postnord/` plus `docs/notes/guides/postnord-customs-declaration-proxy.md` into `docs/notes/{integration,sandbox}/` with a README index; redaction pass (R3); fork copies stay; the eori-vat checkpoint note stays fork-side | Pending | M |
| C10 `docs: distill concepts and guides for the documentation site` | Starlight-visible `docs/{index,concepts/*,guides/*,development/*}`: letter gating + toggles, EU VAT area, ZDC entry code, CN22/CN23/invoice split, ZPL preference, stamping; no sandbox claims without committed fixtures | Pending | M |
| C11 `docs: add the starlight docs site workflow` | docs-pages.yml; harness `PrimePack-AB/starlight-docs-harness` pinned; SITE_BASE=/karrio-postnord | Pending | S |
| C12 `docs: add repository conventions for agents` | CLAUDE.md: commands, fork-SDK floor, evidence/redaction rules, guide.developer.postnord.com citation rules, current-state ledger | Pending | S |

### Review gate

A fresh-context agent reviews the standalone repo against this PRD between Phase 3 and Gate U1, per the fork's prd-and-review rules.

### Phase 5a: Plan repo (~/projects/plan) + dev wiring

The plan repo carries an uncommitted npins edit — the user's staged dhl pin refresh e87ce60→1f9a009; it is surfaced and committed as part of P1 or separately per the user, never silently absorbed.

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| P1 `chore(npins): pin karrio-postnord` | npins add PrimePack-AB/karrio-postnord@main at the Gate-U1 SHA | Pending | S |
| P2 `feat(karrio): package postnord and mount it as an extra plugin` | overlay `plan/modules/nixpkgs/overlays/karrio.nix`: `karrio-postnord` buildPythonPackage mirroring the dhl entry (version 2026.10, src npins.postnord, propagatedBuildInputs [karrio-sdk], pythonImportsCheck); `plan/modules/clan/services/karrio/flake-module.nix:87` extraPlugins default += postnord | Pending | M |
| Dev wiring (decision 7) | locate dev's deployment (how the develop push deploys dev — fork CI, webhook, or host), apply the same standalone-plugin consumption, verify dev sees postnord from the plugin; reduces to verification if dev already runs through the plan repo service | Pending | M |
| Eval gates | `nix flake check` / repo equivalents + `nix build` the server package (eval-only confirmation; the extraPlugins collision assertion must not trip) | Pending | S |

No n8n change (default); no karrio-nix change (its optional-module derivation disappears when the karrio pin moves past the removal).

### Phase 4: Fork switchover

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| F1 `chore: drop vendored postnord specs (moved to standalone repo)` | on docs-vendored-carrier-specs (temp worktree): delete the 9 vendor files, mirroring the dhl precedent 2e910d16b; postnord is the sole vendor carrier; verified no postnord branch carries vendor/ | Pending | S |
| F2 `docs(workflow): drop the postnord branches from the develop assembly` | on docs-openspec: delete BRANCHES lines 48-57 in assemble-develop.sh; update develop-assembly.md stack prose (no remaining branch bases on a removed one); the `requirements.sdk.dev.txt:27` and `source.requirements.txt:74` lines auto-vanish with the branches | Pending | M |
| Rebuild | from the main checkout in the nix dev shell: `rebuild-develop.sh --no-promote` — postnord must be absent from the differing-connectors list; `git diff --stat develop develop-next` must show only the 74 connector files, the 4 PRDs, the 2 requirements lines, and develop-assembly.md edits, plus this PRD arriving via docs-openspec; anything extra → stop; then promote | Pending | M |
| Cleanup (after Gate U3) | remove the 10 postnord worktrees; rename branches `deprecated-<name>` (dhl precedent); origin refs untouched | Pending | S |

### Phase 5c/5d: Pin advance + Deploy B verification

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| P3 `chore(npins): advance the karrio pin past the postnord removal` | npins karrio entry (sources.json:29) | Pending | S |
| Verify | restart; `/v1/references` postnord present (now solely from the plugin); `POSTNORD_ENABLED` auto-seeded; rate quote shows 34/UX absent with default config and present with toggles (Z12 connection for UX); optional tracking smoke | Pending | S |

---

## User gates

Every push and deploy is the user's explicit action; each gate is a hard stop.

| Gate | Reached when | User actions | What it carries |
|------|--------------|--------------|-----------------|
| U1 | Phases 1-3 green and the fresh-context review passed | create `PrimePack-AB/karrio-postnord` (public) and push main | the standalone repo at the C13 tip (C1-C13) |
| U2 | Phase 5a eval gates pass | push plan main; deploy to prime (Deploy A); micro-gate: list then delete the stale untracked `modules/connectors/dhl_freight_sweden/` dir in the fork checkout (R6) | the 6 pending dhl commits, the surfaced dhl pin refresh, P1, P2 |
| U3 | Deploy A verified inert; develop rebuilt, diff-gated, promoted | push docs-openspec (this PRD + F2); push docs-vendored-carrier-specs (F1); `git push --force-with-lease` develop | the develop switchover; deploys dev (already wired — decision 7) |
| U4 | P3 committed | push plan main; deploy to prime (Deploy B) | the karrio npins pin advance — the atomic swap to plugin-only postnord |

---

## Testing strategy

| Phase | Verification |
|-------|--------------|
| 1 | 74-file ls-tree count; recursive diff shows only the C2/C3/C4 intended edits; standalone venv suite green from the repo root (PYTHONPATH pinning hazard, R9); entry-point assertion after `pip install -e .` |
| 2 | full suite green including the three gating tests, the eori-vat fallback/precedence/guard/misplaced tests, and the Monaco/Mount Athos/NI territory cases (no code repair — develop code already correct); pyright clean; `grep -c offer_ units.py` ≥ 4 |
| 3 | Starlight harness dev render from `../starlight-docs-harness` (notes/ excluded, links resolve); suite still green |
| 5a | `nix flake check` / repo equivalents; `nix build` the server package (eval-only; the collision assertion must not trip) |
| Deploy A (5b) | api+worker restart clean; `/var/lib/karrio-plugins/postnord/` contains `karrio/plugins/postnord`; `/v1/references` postnord identical to pre-deploy — in-tree still wins discovery; the plugin is inert |
| 4 | `rebuild-develop.sh --no-promote`; postnord absent from differing connectors; the diff-stat gate; then promote |
| Deploy B (5d) | `/v1/references` postnord present solely from the plugin; `POSTNORD_ENABLED` auto-seeded; 34/UX absent with default config, present with toggles (Z12 for UX); optional tracking smoke |

```bash
# From ~/projects/karrio-postnord root, standalone venv
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -f -s tests
```

Run tests from the repo root only; the fork SDK rides requirements-dev.txt as `-e ../karrio/modules/sdk` (R9).

---

## Risk assessment

Ranked as in the approved plan.

| # | Risk | Impact | Mitigation |
|---|------|--------|------------|
| R1 | PostNord spec licensing blocks the public vendor/ directory | High | 10-minute terms check before Gate U1; fallback strips vendor/ from the public repo |
| R4 | Deploy B changes the default rate catalog (gates live) | Medium | Pre-check prime connections for ungated 34/UX reliance before the deploy; enable toggles where needed |
| R5 | dev loses postnord during the switchover | Medium | Decision 7: dev wired before Gate U3 |
| R3 | Live keys leak through ported notes | High | Redaction pass before C9; `.env` gitignored; live keys never committed |
| R8 | Parallel sessions share docs-openspec | Medium | Pathspec commits; sequence the PRD and BRANCHES commits; never rebuild over uncommitted peer state |
| R9 | Worktree venv pinning yields phantom test results | Medium | Run tests from the repo root with the fork SDK editable-installed |
| R7 | Deploy A is not behavior-identical | High | Stop condition: any behavior change falsifies the discovery assumptions |
| R6 | Stale untracked dhl dir in the fork checkout | Low | List contents before deleting; gated micro-action at Gate U2 |
| R10 | Vendored spec snapshot drifts from the live API | Low | Noted in the standalone CLAUDE.md current-state ledger (C12) |

---

## Migration and rollback

### Backward compatibility

- API compatibility: plugin id `postnord`, entry-point key, import namespaces, and the constance flag `POSTNORD_ENABLED` all stay exactly as in-tree — they are the persisted carrier identity in tenant data.
- Data compatibility: unchanged; the carrier name on connections and shipments is the plugin id, which does not change.
- Behavior: one deliberate change — Deploy B gates services 34 (tracked letter) and UX (export letter) behind `offer_tracked_letter`/`offer_export_letter` connection config, default false; the 2026.10 version bump marks it and the R4 pre-check covers existing reliance.

### Rollback

1. Before Gate U3: prime still serves in-tree postnord and the plugin mount is inert by discovery priority; redeploying the pre-U2 plan state restores exactly the old behavior.
2. After Gate U3, before Deploy B: prime is untouched — its karrio pin still resolves to `65468d813`; dev rolls back by pinning back or rewiring.
3. After Deploy B: revert P3 (karrio pin back to `65468d813`) and redeploy; the postnord branches are renamed `deprecated-*`, not deleted, and origin refs are untouched, so develop can be rebuilt from the pre-removal assembly if ever needed.
