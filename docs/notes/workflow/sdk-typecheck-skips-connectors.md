---
title: SDK typecheck skips connectors
---

# SDK typecheck skips connectors

`bin/run-sdk-typecheck` runs mypy over no connector package, locally or in upstream CI.
Observed on `upstream/main` at `deea10f85`.

## How connectors are selected

The script typechecks the SDK submodules first (`bin/run-sdk-typecheck:9-11`), then selects connector packages with `find "modules/connectors" -type f -name "setup.py"` (`bin/run-sdk-typecheck:22`) and passes each directory to `run_connector_typecheck` through `xargs` (`bin/run-sdk-typecheck:23`).
The selection line dates from `656781fa9` (2023-11-06).

Connectors ship `pyproject.toml` instead of `setup.py` since `139d25fd7` ("migrate from setup.py to pyproject.toml", 2025-05-06).
On `upstream/main`, `git ls-tree -r --name-only upstream/main modules/connectors` lists 29 `modules/connectors/*/pyproject.toml` files and no `setup.py` at any depth.

The `find` therefore returns nothing, `xargs` receives a single blank line, and GNU `xargs -I{}` ignores blank lines, so `run_connector_typecheck` is never called.
The script then prints `typecheck complete` and exits 0.

## Where it runs

Upstream CI runs the script in the `sdk-tests` job as `./bin/run-sdk-typecheck -v` (`.github/workflows/tests.yml:56-57`).
The `-v` argument is not read by the script.
A local run on the `fix-state-code-normalization` branch in `python:3.12-slim-bookworm` reported 14 `Success` lines, one per SDK submodule found by the first loop, and no connector output (`$XDG_STATE_HOME/agent-logs/karrio/pr1141-typecheck-head-20260925-094034.log`).

## Follow-up

This is a candidate for a separate upstream issue.
Changing the selector to `pyproject.toml` would start typechecking all 29 connectors, and the number of mypy errors that would surface has not been measured.
