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
`feat-postnord-connector` is not in `BRANCHES` itself; it reaches `develop` through `feat-postnord-cn22-stamping`, which contains it.
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
4. If the branch is new, add it to `BRANCHES` in `assemble-develop.sh` on `docs-openspec`.
5. Regenerate and deploy from the main checkout.
   Without `-r`, the script takes the repository from the current directory, so running it from a worktree roots the target worktree inside that worktree; from elsewhere, pass `-r /home/joaqim/projects/karrio`.

   ```bash
   docs/notes/workflow/assemble-develop.sh -f           # builds develop-next in .worktrees/develop-next
   git diff develop develop-next --stat                 # review what the deployment will change
   git push --force-with-lease=develop:"$(git rev-parse origin/develop)" origin develop-next:develop
   git -c submodule.recurse=false switch develop && git -c submodule.recurse=false reset --hard develop-next
   git worktree remove .worktrees/develop-next && git branch -D develop-next
   ```

A merge conflict during assembly means two feature branches disagree.
Fix it on the feature branches, never in the assembled result.

## When upstream merges a pull request

Remove the branch from `BRANCHES`, rebase any branches that depend on it onto `upstream/main`, and regenerate.

## Git hazard

The global git config sets `submodule.recurse=true`, and the `community` submodule is not initialised in `.worktrees/`.
Pass `-c submodule.recurse=false` to any reset, checkout, cherry-pick or rebase in a worktree; the script does this already.
