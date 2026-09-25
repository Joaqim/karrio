---
title: Nix dev shell in upstream-bound worktrees
---

# Nix dev shell in upstream-bound worktrees

The `dev-nix-flake` branch provides two dev shells for the SDK, CLI, connectors and plugins.
Neither shell provides `karrio.server`; Django tests still run in the worktree's `.venv` created by `bin/activate-env`.

## The two shells

`devShells.default` is the shell for the fork's branches and the assembled `develop`, which import `pypdf`.
`devShells.upstream` is the same shell with `PyPDF2` added, for branches based on `upstream/main`, which still import `PyPDF2`.
nixpkgs marks `PyPDF2` with known vulnerabilities, and the `upstream` shell clears that flag in its own Python package set only.
Both shells use Python 3.12, matching upstream CI and the `python:3.12-slim-bookworm` verification container.

On entry the shell hook resolves the source root with `git rev-parse --show-toplevel`, falling back to `$PWD`, and exports it as `KARRIO_DEV_ROOT`.
`PYTHONPATH` is set to that root's `modules/sdk`, `modules/soap`, `modules/cli` and every connector and plugin directory that contains a `karrio` package.
Any `PYTHONPATH` inherited from the calling environment is discarded, so a module missing from the worktree fails to import instead of resolving to another checkout's sources.
The hook runs once, in the directory `nix develop` is started from, so `cd` into the worktree before running `nix develop`; a `cd` inside `--command` does not move `PYTHONPATH`:

```bash
cd /home/joaqim/projects/karrio/.worktrees/<branch>
nix develop 'git+file:///home/joaqim/projects/karrio?ref=dev-nix-flake#upstream' --command python -m unittest discover -v -f modules/connectors/<carrier>/tests
```

## Why worktrees need their own .envrc

Worktrees live under `.worktrees/` inside the `develop` checkout.
Without an `.envrc` of their own, direnv walks up to the `develop` checkout's tracked `.envrc` and loads that shell.
An upstream-bound branch has no `flake.nix`, so its `.envrc` points at the committed `dev-nix-flake` branch through a `git+file` flake reference.

Place this `.envrc` in the worktree root:

```bash
# shellcheck shell=bash
if ! has nix_direnv_version || ! nix_direnv_version "3.1.1"; then
  source_url "https://raw.githubusercontent.com/nix-community/nix-direnv/3.1.1/direnvrc" "sha256-p+fzQdrms/hDa7g+soShAybJNo4bN4SIAeSfqNKgD5I="
fi

use flake "git+file:///home/joaqim/projects/karrio?ref=dev-nix-flake#upstream"

dotenv_if_exists
```

Then run `direnv allow` in the worktree root and confirm with `direnv status` that the loaded RC path is the worktree's own `.envrc`.
A worktree for a branch that already carries the `pypdf` change can use `#default` instead of `#upstream`.

## Keeping the .envrc untracked

The `.envrc` and nix-direnv's `.direnv/` cache must stay out of the upstream-bound branches.
All worktrees share the main repository's `info/exclude` file, so the ignore lines are added once:

```bash
exclude=$(git rev-parse --path-format=absolute --git-path info/exclude)
for line in .envrc /.direnv/; do
  grep -qxF "$line" "$exclude" || printf '%s\n' "$line" >> "$exclude"
done
```

The `develop` checkout's `.envrc` is tracked, so the exclude entry does not affect it.
`git status --porcelain` in each worktree should be empty after the `.envrc` is installed.

## Picking up dev-nix-flake changes

The `git+file` reference reads the committed tip of `dev-nix-flake`, not its working tree, so uncommitted flake edits are invisible to worktrees.
nix-direnv caches the evaluated shell and does not notice a new commit on that branch.
Run `nix-direnv-reload` in each worktree after `dev-nix-flake` changes.
