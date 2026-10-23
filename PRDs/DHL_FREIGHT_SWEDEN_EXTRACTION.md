# DHL Freight Sweden Connector Extraction

| Field | Value |
|-------|-------|
| Project | Karrio fork |
| Version | 1.0 |
| Date | 2026-10-03 |
| Status | Completed |
| Owner | Joaqim Planstedt |
| Type | Architecture |
| Reference | [PRD_DHL_FREIGHT_SWEDEN_INTEGRATION.md](./PRD_DHL_FREIGHT_SWEDEN_INTEGRATION.md) |

---

## Executive Summary

This PRD covers extracting the `dhl_freight_sweden` connector from the fork
monorepo (`modules/connectors/dhl_freight_sweden`, three-branch family stack)
into a standalone public repository `PrimePack-AB/karrio-dhl-freight-sweden`,
preserving commit history, following the packaging precedent of upstream's
`community/` plugins and the lifecycle precedent of the `nordic_conventions`
plugin repository.

The fork's in-tree copy stays on `develop` unchanged until a separate
switchover change makes deployment consume the external package; extraction is
therefore zero-risk to the running deployment on `prime`.

### Key Architecture Decisions

1. **Repo name = dist name**: `karrio-dhl-freight-sweden` (PyPI-normalized form
   of `karrio_dhl_freight_sweden`); repo is the distribution source.
2. **Public visibility**: the only third-party content riding in the connector
   tree — the vendored DHL se-api-farm swagger specs — is already public on
   `Joaqim/karrio` (`develop` via `docs-vendored-carrier-specs`), so publishing
   adds no new exposure.
3. **Preserved history**: `git filter-repo --subdirectory-filter` export of the
   family tip carries all 27 commits touching the connector path, keeping the
   live-verified field-semantics provenance (payerCode, CU qualifier,
   procedureCode 1042, per-product piece minimums) in `git log`.
4. **Identity unchanged**: plugin id `dhl_freight_sweden`, entry-point key,
   import namespaces, and constance flag `DHL_FREIGHT_SWEDEN_ENABLED` all stay
   exactly as in-tree — they are the persisted carrier identity in tenant data.
5. **Deferred switchover**: `BRANCHES`, `source.requirements.txt`, the docker
   source build, and the nix dev shell keep using the in-tree copy until a
   follow-up change swaps consumption to the external package.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| History export of the 27-commit connector path | Fork-side switchover (separate change) |
| Repo assembly (LICENSE, README, gitignore, requirements-dev, vendor import) | PostNord extraction (deferred: fork-bound stamping surface) |
| Standalone verification (entry point, imports, unittest suite) | Publishing to PyPI |
| GitHub repo creation at PrimePack-AB (public) | Service narrowing (open decision, lands in the new repo) |

---

## Open Questions & Decisions

### Pending Questions

None blocking extraction. Switchover-phase questions are recorded in the
Deferred Switchover section and must be answered before that change.

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | Repo name | `karrio-dhl-freight-sweden` | Dist-name-as-repo; future extractions follow mechanically | 2026-10-03 |
| D2 | Visibility | Public | Vendored specs already public on the fork; LGPL-compatible | 2026-10-03 |
| D3 | History | Preserved via filter-repo export | Provenance of live-verified booking semantics | 2026-10-03 |
| D4 | PostNord | Not extracted now | Hard dependencies on fork-only stamping surface (SDK utils, metadata fields, server documents) | 2026-10-03 |

---

## Problem Statement

### Current State

The connector lives in the fork monorepo as a three-branch family stack
(`feat-dhl-freight-se-connector` → `feat-dhl-freight-se-customs` →
`fix-dhl-freight-se-eu-vat-territories`), assembled into `develop` by
`assemble-develop.sh` alongside 20 other branches. It is hermetic: zero
fork-only SDK imports, an outside-tree footprint of three files (PRD plus two
requirements-manifest lines), and a pyproject already standalone-package
shaped (`karrio_dhl_freight_sweden`, single `karrio.plugins` entry point,
namespace-package layout identical to upstream connectors).

### Desired State

The connector becomes independently versioned and consumable outside the fork:
a public repository whose pip installation registers `dhl_freight_sweden` with
any karrio SDK (upstream or fork) through the standard entry-point discovery
chain, with its tests, vendored API specs, and history self-contained.

### Problems

1. **Coupled release cadence**: connector changes ride the fork's develop
   assembly; independent versioning exists de-facto (2026.4 vs SDK 2026.1.32)
   but has no distribution path.
2. **Monorepo branch load**: three of 23 `BRANCHES` entries exist solely for
   this connector; every connector fix re-parents a stack.
3. **No external consumability**: consumers outside this fork cannot install
   the connector without the whole monorepo.

---

## Goals & Success Criteria

### Goals

1. Public `PrimePack-AB/karrio-dhl-freight-sweden` with the connector at repo
   root and 27 commits of preserved history.
2. Standalone suite green from the repo root with no monorepo checkout on
   `PYTHONPATH` (SDK via local editable install; upstream SDK suffices).
3. Zero behavior change in the fork: `develop` untouched by extraction.

### Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Exported commits touching connector path | exactly 27 | Must-have |
| `karrio.plugins` entry point lists `dhl_freight_sweden` | yes | Must-have |
| `python -m unittest discover -f tests` from repo root | all green | Must-have |
| Fork `develop` diff before/after extraction | none | Must-have |
| Vendored spec files present under `vendor/` | 13 | Must-have |

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Standalone repo (dist-name) | Independent lifecycle; clean history; precedent | Build-side plumbing for fork consumption | **Selected** |
| Upstream `community/` contribution | Upstream maintenance | Upstream review cadence; not ours to control | Rejected (for now) |
| Keep in-monorepo only | No work | None of the goals met | Rejected |

### Trade-off Analysis

The community route was rejected because the connector encodes
PrimePack-operational semantics (booking field semantics live-verified against
the production account) whose change cadence we control. The standalone repo
keeps that control while remaining upstream-contributable later — the package
shape is byte-identical to a community plugin, so donating it later is a
directory move.

---

## Technical Design

### Existing Code Analysis

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| Connector package | `modules/connectors/dhl_freight_sweden/` | Exported verbatim; root becomes repo root |
| Community plugin packaging | `community/plugins/royalmail/` etc. | Same pyproject/entry-point/namespace shape; README pattern |
| Standalone-plugin lifecycle | `~/projects/nordic_conventions` | requirements-dev local-SDK pattern, README structure |
| Entry-point discovery | `modules/sdk/karrio/core/plugins.py` (`karrio.plugins` group) | Consumed as-is; location-agnostic |
| Constance gating | `apps/api/karrio/server/settings/constance.py` | Auto-generates `DHL_FREIGHT_SWEDEN_ENABLED` from PLUGIN_METADATA |
| Vendored specs | `docs-vendored-carrier-specs` branch → `vendor/` | Imported as one commit from `develop` tree content |

### Architecture Overview

```
CURRENT (fork monorepo)                      TARGET (standalone + deferred switchover)

upstream/main                                PrimePack-AB/karrio-dhl-freight-sweden (public)
  │                                            pyproject: karrio_dhl_freight_sweden
  └─ feat-dhl-freight-se-connector            karrio/{plugins,providers,mappers,schemas}/
       └─ ...-customs                             dhl_freight_sweden
            └─ ...-eu-vat-territories           tests/  vendor/  LICENSE (LGPL-3.0)
                 (27 commits)                      │ pip install (git URL / wheel)
  modules/connectors/dhl_freight_sweden ────────► │
       + docs-vendored-carrier-specs (vendor/)  ▼
                    │                          karrio SDK ── entry point ──► discovery
                    ▼                          DHL_FREIGHT_SWEDEN_ENABLED (auto constance)
        assemble-develop.sh
                    │                          fork develop: in-tree copy FROZEN
                    ▼                          until switchover change swaps
                 develop ──► nix deploy        source.requirements/docker/nix to the
                 (prime)                       external package
```

### Extraction Sequence

```
┌──────────┐   ┌───────────┐   ┌──────────────┐   ┌──────────┐   ┌──────────┐
│  clone   │──►│ filter-   │──►│   assemble   │──►│ verify   │──►│ publish  │
│  single  │   │ repo      │   │ LICENSE/     │   │ unittest │   │ gh repo  │
│  branch  │   │ subdir    │   │ README/vendor│   │ entry-pt │   │ create   │
└──────────┘   └───────────┘   └──────────────┘   └──────────┘   └──────────┘
   family tip     27 commits      +4 commits        all green      user-gated
```

### Discovery Data Flow (post-install)

```
pip install karrio-dhl-freight-sweden
        │
        ▼
importlib.metadata entry_points(group="karrio.plugins")
        │  dhl_freight_sweden = karrio.plugins.dhl_freight_sweden:METADATA
        ▼
references.import_extensions() ──► _register_carrier (Mapper+Proxy+Settings)
        │
        ▼
PROVIDERS/MAPPERS + PLUGIN_METADATA ──► constance flag ──► /v1/references
```

---

## Edge Cases & Failure Modes

### Edge Cases

| Scenario | Expected Behavior | Handling |
|----------|-------------------|----------|
| filter-repo commit count ≠ 27 | Stop, report discrepancy | Verification gate before assembly |
| Test failure in standalone venv | Stop, report verbatim | No connector-code edits during extraction |
| Fork copy diverges from repo | Repo is source of truth | Fork copy frozen; switchover removes it |

### Failure Modes

| What Can Go Wrong | Impact | Mitigation |
|-------------------|--------|------------|
| History export brings merge noise | Ugly public history | Single-branch clone of linear family tip (no merges in path history) |
| Vendored specs licensing | Public redistribution question | Already public on Joaqim/karrio develop; no new exposure |
| Entry point not discovered | Connector invisible | Verified pre-publish in standalone venv |

---

## Implementation Plan

### Phase 1: Export (subagent Task)

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Single-branch clone at family tip | `~/projects/karrio-dhl-freight-sweden` | Completed | S |
| `git filter-repo --subdirectory-filter modules/connectors/dhl_freight_sweden` | same | Completed | S |

### Phase 2: Assembly

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| LICENSE LGPL-3.0 (from monorepo root) | `LICENSE` | Completed | S |
| README extension (install, registration, development) | `README.md` | Completed | S |
| Vendored specs import from develop tree | `vendor/` (13 files) | Completed | S |
| .gitignore, requirements-dev.txt | both | Completed | S |

### Phase 3: Verification

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| venv + editable installs, entry-point assertion | — | Completed | S |
| Full unittest suite from repo root | `tests/` | Completed | S |

### Phase 4: Publish (user-approved, gated on Phase 3 green)

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| `gh repo create PrimePack-AB/karrio-dhl-freight-sweden --public` + push | — | Completed | S |

### Completion (2026-10-03)

Published: https://github.com/PrimePack-AB/karrio-dhl-freight-sweden
(public, default branch `main`, remote tip `5b8ee024ea15` == local).
34 commits = 27 exported + 7 assembly (vendor specs, LICENSE as plain
LGPL-3.0 with PrimePack AB attribution header, README, requirements-dev,
gitignore, package metadata → PrimePack AB). Standalone verification:
96/96 unittest green in a fresh venv, entry point `dhl_freight_sweden`
discovered, 20-member ShippingService enum intact. Local checkout:
`~/projects/karrio-dhl-freight-sweden` (remote `origin` configured).

### Deferred: Fork Switchover (separate PRD/change)

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Remove dhl family from `BRANCHES` | `docs/notes/workflow/assemble-develop.sh` | Completed 2026-10-03 | M |
| Park family branches as deprecated | `deprecated-{feat,feat,fix}-dhl-freight-se-*` | Completed 2026-10-03 | S |
| Drop dhl vendored specs from develop | `docs-vendored-carrier-specs` | Completed 2026-10-03 | S |
| Consume external package in source build (docker path only) | `source.requirements.txt`, `bin/build-server-image-from-source` | Resolved: family branches carried the manifest lines; removal drops them — docker-source builds simply exclude the connector | S |
| Deployment adoption (plan repo) | `~/projects/plan/npins`, `~/projects/plan/modules/clan/services/karrio/flake-module.nix` | Completed 2026-10-03, deployed dormant | S |
| Nix dev shell integration | `dev-nix-flake:nix/dev-shell.nix` | Pending (connector dev now happens in the standalone repo's own venv) | S |
| Repoint conventions cross-checks | `~/projects/nordic_conventions` | Pending (dhl cross-checks skip in the fork dev shell post-removal; repoint to the standalone repo later) | S |

**Deployment consumption design (prime, nix/clan):** the karrio flake-module
already consumes external plugins by bind-mount (`extraPlugins` →
`/var/lib/karrio-plugins`, `KARRIO_PLUGINS` scan) — the same path
`nordic_conventions` rides. Adoption is an npins pin for
`PrimePack-AB/karrio-dhl-freight-sweden` plus an `extraPlugins` entry; the
extracted repo satisfies the scanner's child shape
(`karrio/plugins/dhl_freight_sweden/` at source root) unchanged. Ordering is
safe: karrio's 4-tier reference merge ranks pip-installed entry points above
the directory scan, so while the fork ships the in-tree copy the mount is
dormant; the mount takes over, same plugin id, when switchover removes the
in-tree copy. The docker `file://` path constraint applies only to
`bin/build-server-image-from-source`, not to this deployment.

**Dependencies:** Publish blocked on Phase 3 evidence. Deployment adoption can
follow publish immediately (dormant until switchover). Switchover blocked on
deployment proof of the external package.

---

## Testing Strategy

| Category | Location | Coverage Target |
|----------|----------|-----------------|
| Connector suite (existing, unmodified) | `tests/dhl_freight_sweden/` | 100% green standalone |
| Entry-point discovery | one-shot python -c | `dhl_freight_sweden` listed |
| Import surface | one-shot python -c | 20 ShippingService members |

```bash
# From repo root, standalone venv
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt -e .
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -v -f tests
```

Deployment verification (switchover phase, per existing runbook): restart,
check `/v1/references` lists `dhl_freight_sweden`, constance
`DHL_FREIGHT_SWEDEN_ENABLED`.

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Fork/repo divergence before switchover | Medium | Medium | Fork copy frozen; changes land in repo only |
| Schema codegen needs monorepo CLI | Low | Certain | `generate` keeps working via `--path`; documented in README |
| Version confusion (2026.4 vs SDK 2026.1.32) | Low | Medium | Repo adopts date-based independent versioning (nordic_conventions pattern) |
| Breaking tenant carrier identity | High | Near-zero | Identity strings unchanged; verified by suite |

---

## Migration & Rollback

### Backward Compatibility

- **API compatibility**: unchanged — same plugin id, same unified models.
- **Data compatibility**: unchanged — carrier name on connections/shipments is
  the plugin id, which does not change.
- **Rollback**: before switchover, rollback is trivial — the fork never
  stopped shipping its in-tree copy; deleting the new repo reverts everything.

---
