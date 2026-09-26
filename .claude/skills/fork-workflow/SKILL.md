---
name: fork-workflow
description: Branch model and mandatory checks for the Joaqim/karrio fork, where develop is generated from feature branches. Use at the start of any session in this fork, before creating a branch or worktree, before claiming anything about develop, origin or push state, and after committing to a feature, docs-openspec or dev-nix-flake branch.
---

# Fork workflow

This fork's `develop` is generated: `upstream/main` plus `--no-ff` merges of the branches listed in `BRANCHES` in `docs/notes/workflow/assemble-develop.sh`.
The main checkout at `/home/joaqim/projects/karrio` has `develop` checked out; all other work happens in worktrees under `.worktrees/`.
The full description is `docs/notes/workflow/develop-assembly.md`.

## Branch model

| Branch | Base | Purpose |
|---|---|---|
| `fix-*`, `feat-*`, `chore-*`, `docs-vendored-*` bound for upstream | `upstream/main` or the unmerged branch they depend on | Changes to be opened as upstream pull requests |
| Fork feature stacks such as `feat-postnord-cn22-stamping` | Their parent feature branches | Fork-only integration of several features |
| `docs-openspec` | `upstream/main` | Working notes, the openspec corpus, and the workflow scripts including `BRANCHES` |
| `dev-nix-flake` | `chore-sdk-pypdf` | Nix flake and dev shells, agent skills, dev tooling |
| `develop` | generated | Deployment branch; never committed to |
| `main` | mirrors upstream | Never written to |

## Where work goes

| Kind of work | Where |
|---|---|
| Fix or feature meant for upstream | New worktree branched from `upstream/main` (or its unmerged parent), then registered in `BRANCHES` right after its parent |
| Change to an existing feature | That feature branch's worktree |
| Notes, PRD drafts not yet on a feature, openspec changes, workflow docs, `BRANCHES` | `docs-openspec` |
| Nix, dev shells, skills, agent tooling | `dev-nix-flake` |
| Anything on `develop` or `main` | Nowhere; redirect it to one of the rows above |

## Rules

1. At session start, run `develop-status.sh` and read its output before saying anything about `develop`, `origin/develop`, or whether a branch is pushed.
   Do not infer those from memory or from an earlier session; pass `--fetch` when the remote state matters.
2. After committing to any `BRANCHES` member, including `docs-openspec` and `dev-nix-flake`, run `rebuild-develop.sh` from the main checkout.
   It verifies the assembled result in the nix dev shell and moves local `develop` only when every check passes; use `--no-promote` to verify without moving it.
   `BRANCHES` is read from the committed tip of `docs-openspec`, so commit a `BRANCHES` edit before rebuilding.
3. Never commit to `develop` or `main`.
4. Never push unless the user explicitly asks for that push.
   `rebuild-develop.sh` prints the push commands; relay them instead of running them.
5. Pass `-c submodule.recurse=false` to every git checkout, switch, reset, merge, rebase or cherry-pick.
   The global config sets `submodule.recurse=true`, and the `community` submodule is not initialised in worktrees.
6. Enter the nix dev shell from inside the worktree being tested, because the shell roots `PYTHONPATH` at the git toplevel of its starting directory.

## Script location

The scripts `develop-status.sh`, `rebuild-develop.sh` and `assemble-develop.sh` live in `docs/notes/workflow/` on `develop` and on `docs-openspec`.
On any other branch, run them from `/home/joaqim/projects/karrio/.worktrees/docs-openspec/docs/notes/workflow/`.
They locate the repository from the current directory, or from `-r <path>`.
