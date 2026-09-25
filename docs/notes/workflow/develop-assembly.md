---
title: Develop assembly workflow
---

# Develop assembly workflow

This fork's `develop` is generated, never committed to directly.
It is `upstream/main` plus `--no-ff` merges of the feature branches listed in `assemble-develop.sh`, in dependency order.
The dev deployment tracks `develop`.
The layout dates from the 2026-09-24 history rework; the previous linear `develop` is kept as `backup-develop-2026-09-24`.

## Branches

The upstream-bound branches are `fix-core-small`, `fix-state-code-normalization` (upstream pull request #1141), `fix-fedex-state-code-countries`, `fix-dashboard-carrier-options`, `chore-sdk-pypdf`, `feat-tracker-locale`, `feat-dhl-freight-se-connector`, `docs-vendored-carrier-specs`, `feat-document-stamping` (on `chore-sdk-pypdf`), `feat-postnord-connector` (on `feat-tracker-locale`), `feat-dhl-freight-se-customs` (on `feat-dhl-freight-se-connector`) and `feat-postnord-customs-invoice` (on `feat-postnord-connector`).
Open their upstream pull requests in dependency order: `chore-sdk-pypdf` before `feat-document-stamping`, `feat-tracker-locale` before `feat-postnord-connector` before `feat-postnord-customs-invoice`, and `feat-dhl-freight-se-connector` before `feat-dhl-freight-se-customs`.
`feat-postnord-connector` is listed in `BRANCHES` before `feat-postnord-cn22-stamping`, which contains it, so the PostNord stack is merged into `develop` explicitly rather than only transitively.
`fix-fedex-smartpost-declared-value` (#1142) was closed unmerged on 2026-09-25; its FedEx failure is fixed by `fix-fedex-state-code-countries` (#1143).

The fork-only branches are `feat-postnord-cn22-stamping`, `dev-nix-flake` and `docs-openspec`.
`feat-postnord-cn22-stamping` is the PostNord connector merged with stamping, plus the CN22 seed registration.
It stays on the fork until both parents land upstream.
`dev-nix-flake` provides the nix dev shell and is based on `chore-sdk-pypdf`.
`docs-openspec` holds the openspec corpus, working notes and this workflow.

## Adding or changing a feature

1. Branch from `upstream/main`, or from the unmerged branch the work depends on.
2. Put the PRD commit first, then one commit per logical capability, in the format `type(scope): summary`.
3. Verify outside nix in `python:3.12-slim-bookworm`, matching upstream CI, and inside the nix dev shell; see [nix-dev-shell-worktrees.md](nix-dev-shell-worktrees.md) for the per-worktree `.envrc`.
4. If the branch is new, add it to `BRANCHES` in `assemble-develop.sh` on `docs-openspec`, after the branch it is based on, and commit.
5. Regenerate develop with `rebuild-develop.sh`, then push; see the agent workflow below.
   The scripts read `BRANCHES` from the committed tip of `docs-openspec`, so an uncommitted edit to the list has no effect.

A merge conflict during assembly means two feature branches disagree.
Fix it on the feature branches, never in the assembled result.

## Agent workflow

Agents follow these steps so that feature branches and the generated `develop` are never confused.
The scripts live in `docs/notes/workflow/` on `develop` and `docs-openspec`; from other branches run them from `/home/joaqim/projects/karrio/.worktrees/docs-openspec/docs/notes/workflow/`.

1. At the start of work, run `develop-status.sh` (add `--fetch` to refresh the remotes) before stating anything about `develop`, `origin` or a branch's push state.
   It lists each `BRANCHES` entry with its containment in `develop` and its state against `origin`, compares `develop` with `origin/develop` and `upstream/main`, and flags dirty worktrees and worktrees on branches missing from `BRANCHES`.
   It exits 0 when `develop` contains every `BRANCHES` tip, 1 when it is stale and 2 on error.
2. Put new work in a worktree under `.worktrees/`, branched from its parent feature branch, or from `upstream/main` for a fix meant for upstream.
   Register the branch in `BRANCHES` right after its parent.
3. Put working notes, openspec changes and this workflow on `docs-openspec`, and dev tooling, the nix flake and agent skills on `dev-nix-flake`.
4. Never commit to `develop` or `main`.
5. After committing to any `BRANCHES` member, including `docs-openspec` and `dev-nix-flake`, run `rebuild-develop.sh` from the main checkout.
   It assembles `develop-next`, runs the touched connector suites and `./bin/run-sdk-tests` in the nix dev shell inside a detached worktree, checks that every `BRANCHES` tip is contained, and moves local `develop` only if the main checkout is clean and every check passed.
   `--no-promote` stops after verification and `--skip-sdk` skips the full SDK run.
   The log goes to `$XDG_STATE_HOME/agent-logs/karrio/`, because `logs/` is not ignored in this repository.
6. Pushing is the user's decision.
   `rebuild-develop.sh` prints the push commands, with `--force-with-lease` pinned to the current `origin/develop`, and never runs them.

## When upstream merges a pull request

Remove the branch from `BRANCHES`, rebase any branches that depend on it onto `upstream/main`, and regenerate.

## Git hazard

The global git config sets `submodule.recurse=true`, and the `community` submodule is not initialised in `.worktrees/`.
Pass `-c submodule.recurse=false` to any reset, checkout, cherry-pick or rebase in a worktree; the workflow scripts do this already.
