---
title: Nix dev shell in upstream-bound worktrees
---

# Nix dev shell in upstream-bound worktrees

The `dev-nix-flake` branch provides two dev shells for the SDK, CLI, connectors and plugins.
Neither shell provides `karrio.server`; Django tests run through the overlay harness described in [Server tests in upstream-bound worktrees](#server-tests-in-upstream-bound-worktrees).

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

if ! use flake "git+file:///home/joaqim/projects/karrio?ref=dev-nix-flake#upstream" --accept-flake-config; then
  echo "nix flake could not be built; check dev-nix-flake and run nix-direnv-reload" >&2
fi

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

## Server tests in upstream-bound worktrees

Worktrees have no `.venv` of their own, and the main checkout's venv at `.venv/karrio` holds editable installs that resolve `karrio` to the main checkout's sources.
`server-tests-overlay.sh` and `server-tests-run.py` in this directory run the Django suites against a worktree's sources with that venv's third-party packages:

```bash
notes=/home/joaqim/projects/karrio/.worktrees/docs-openspec/docs/notes/workflow
worktree=/home/joaqim/projects/karrio/.worktrees/<branch>
"$notes/server-tests-overlay.sh" "$worktree" python "$notes/server-tests-run.py" test --failfast karrio.server.manager.tests
"$notes/server-tests-overlay.sh" "$worktree" python "$notes/server-tests-run.py" test --failfast karrio.server.core.tests
```

The overlay script derives the main checkout from the worktree's git common directory and changes into the worktree before running the command.
It puts the worktree's `apps/api` and every module, connector, plugin, and `ee` module directory containing `karrio`, `karrio_cli`, or `pysoap` (so `modules/soap` is included) on `PYTHONPATH`.
It puts the main venv first on `PATH` and sets `VIRTUAL_ENV`, so `python` is the venv's interpreter.
Upstream-based branches import `PyPDF2`, which the venv lacks, so the script resolves `PyPDF2` 3.0.1 from the `#upstream` dev shell and exposes it through a directory in `$XDG_CACHE_HOME/karrio-server-tests/pypdf2` that symlinks only that package, not the shell's whole site-packages.
WeasyPrint needs native libraries the venv does not bundle, so `LD_LIBRARY_PATH` points at `glib`, `pango`, `harfbuzz`, and `fontconfig` built from the flake's locked nixpkgs through `nix build --inputs-from`.
`KARRIO_VENV` and `KARRIO_DEV_FLAKE` override the venv and the flake reference, which default to `<main checkout>/.venv/karrio` and the committed `dev-nix-flake` branch.

`PYTHONPATH` alone does not isolate the worktree, because the venv's `.pth` files register editable-install finders, path hooks, and `sys.path` entries that can resolve parts of the `karrio` namespace packages to the main checkout's sources.
`server-tests-run.py` removes the `__editable__` finders and path hooks and any `sys.path` entry under the main checkout outside the worktree and the venv, then runs the `karrio` CLI in-process.
After the command finishes it lists every loaded `karrio` module whose file lies under the main checkout but outside the worktree, and exits with status 3 if there is any, so a passing run proves the suites exercised the worktree's code.
A clean run ends with `karrio modules loaded from outside the worktree: 0`.
