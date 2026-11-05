# Tasks

## 1. Branch setup

- [x] 1.1 Run `docs/notes/workflow/develop-status.sh --fetch` and create worktree `.worktrees/feat-connection-config-enum-list` on a new branch from `upstream/main` with `git -c submodule.recurse=false worktree add`
- [x] 1.2 Register `feat-connection-config-enum-list` in BRANCHES of `docs/notes/workflow/assemble-develop.sh` after `fix-commodity-value-amount-input`, update `develop-assembly.md`'s branch list, and commit on docs-openspec

## 2. SDK

- [x] 2.1 Write `PRDs/CONNECTION_CONFIG_ENUM_LIST.md` from `PRDs/TEMPLATE.md` as the branch's first commit, naming the bare-list behaviour change
- [x] 2.2 Coerce list values in `OptionEnum.__call__`, and verify `modules/sdk/tests/core/test_option_enum_list.py` passes and fails against the unpatched SDK
- [x] 2.3 Publish item enum names for list connection configs and options and report list types as `list` in `parse_type`, and verify `modules/sdk/tests/core/test_references_connection_configs.py` passes and fails against the unpatched SDK

## 3. Dashboard

- [x] 3.1 Add `packages/ui/components/ordered-enum-pills.tsx` and wire it into `renderConfigFields` with default pre-fill, and verify `tsc --noEmit -p packages/ui` reports no new errors
- [ ] 3.2 Check the dialog manually: add, remove, drag, move buttons, empty save unsetting the key, and default pre-fill for a new connection

## 4. Integration

- [x] 4.1 Run `python -m unittest discover -f modules/sdk/tests` and `./bin/run-sdk-tests` in the nix dev shell with import paths under the worktree, and the SDK suite in `python:3.12-slim-bookworm`
- [x] 4.2 Run `docs/notes/workflow/rebuild-develop.sh` and push the branch, docs-openspec and develop with its snapshot tag
- [ ] 4.3 Open the upstream draft pull request, naming the bare-list coercion change in its description
