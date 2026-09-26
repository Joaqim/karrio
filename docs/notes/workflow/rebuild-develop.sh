#!/usr/bin/env bash
# Regenerate develop from BRANCHES, verify it, and promote it locally.
#
# Usage: rebuild-develop.sh [--no-promote] [--skip-sdk] [--shell name] [-r repo]
#   --no-promote  build and verify only; leave local develop untouched
#   --skip-sdk    skip ./bin/run-sdk-tests (touched connector suites still run)
#   --shell name  dev shell of the dev-nix-flake flake (default: default)
#   -r repo       any checkout of the repository (default: the current directory)
#
# Steps: assemble develop-next with the assemble-develop.sh committed on
# docs-openspec; detach its worktree; inside the nix dev shell, check that
# karrio imports resolve into that worktree, run the test suite of every
# connector that differs from upstream/main, then ./bin/run-sdk-tests; check
# that develop-next contains every BRANCHES tip; move local develop to it when
# the main checkout is clean. The worktree and develop-next are removed on
# success and kept for inspection on failure. Nothing is pushed; the push
# commands are printed at the end.
set -euo pipefail

owner=docs-openspec
assembler=docs/notes/workflow/assemble-develop.sh
target=develop-next
promote=1
sdk=1
shell=default
start=.

while (($#)); do
  case "$1" in
  --no-promote) promote=0 ;;
  --skip-sdk) sdk=0 ;;
  --shell) shell=${2:?--shell needs a name}; shift ;;
  -r) start=${2:?-r needs a path}; shift ;;
  -h | --help) sed -n '2,18p' "$0"; exit 0 ;;
  *) sed -n '2,18p' "$0" >&2; exit 2 ;;
  esac
  shift
done

common=$(git -C "$start" rev-parse --path-format=absolute --git-common-dir)
repo=$(dirname "$common")
worktree=$repo/.worktrees/$target
flake="git+file://$repo?ref=dev-nix-flake#$shell"
g() { git -C "$repo" -c submodule.recurse=false "$@"; }
gw() { git -C "$worktree" -c submodule.recurse=false "$@"; }

if g check-ignore -q logs/; then
  logdir=$repo/logs
else
  logdir=${XDG_STATE_HOME:-$HOME/.local/state}/agent-logs/karrio
fi
mkdir -p "$logdir"
log=$logdir/rebuild-develop-$(date +%Y%m%d-%H%M%S).log
exec > >(tee "$log") 2>&1
echo "log: $log"

cleanup() {
  if [[ -d "$worktree" ]]; then g worktree remove --force "$worktree"; fi
  if g rev-parse --verify -q "refs/heads/$target" >/dev/null; then g branch -q -D "$target"; fi
}
fail() {
  echo "FAILED: $*"
  echo "kept for inspection: $worktree (branch $target); log: $log"
  exit 1
}

script=$(mktemp)
trap 'rm -f "$script"' EXIT
g show "$owner:$assembler" >"$script"
mapfile -t BRANCHES < <(sed -n '/^BRANCHES=(/,/^)/p' "$script" | sed '1d;$d' | tr -d ' \t' | grep -v '^$')
echo "assembler: $owner@$(g rev-parse --short "$owner"), ${#BRANCHES[@]} branches"

bash "$script" -r "$repo" -t "$target" -w "$worktree" -f || fail "assembly"
gw checkout -q --detach
next=$(gw rev-parse HEAD)

mapfile -t connectors < <(
  g diff --name-only upstream/main "$next" -- modules/connectors/ | cut -d/ -f3 | sort -u
)
tested=()
for c in "${connectors[@]}"; do
  [[ -d "$worktree/modules/connectors/$c/tests" ]] && tested+=("$c")
done
echo "connectors differing from upstream/main: ${tested[*]:-none}"

mapfile -t packages < <(
  for c in "${tested[@]}"; do
    for p in "$worktree/modules/connectors/$c/karrio/providers"/*/; do
      echo "karrio.providers.$(basename "$p")"
    done
  done
)

# The shell hook roots PYTHONPATH at the git toplevel of the directory nix
# develop starts in, so it must start inside the worktree. VIRTUAL_ENV is set
# to the path bin/activate-env expects so run-sdk-tests does not try to source
# a virtualenv the fresh worktree lacks.
(
  cd "$worktree"
  # shellcheck disable=SC2016
  VIRTUAL_ENV=$worktree/.venv/karrio nix develop "$flake" --accept-flake-config --command bash -euo pipefail -c '
    root=$(pwd -P)
    python - "$root" "$@" <<"PY"
import importlib, os, sys
root = sys.argv[1]
bad = []
for name in ["karrio.lib", "karrio.core", *sys.argv[2:]]:
    path = os.path.realpath(importlib.import_module(name).__file__)
    print(f"import {name}: {path}")
    if not path.startswith(root + os.sep):
        bad.append(name)
if bad:
    sys.exit(f"imports resolved outside {root}: {bad}")
PY
  ' _ "${packages[@]}"
) || fail "import paths"

for c in "${tested[@]}"; do
  echo "== connector $c"
  (cd "$worktree" && nix develop "$flake" --accept-flake-config --command \
    python -m unittest discover -f "modules/connectors/$c/tests") || fail "connector $c"
done

if ((sdk)); then
  echo "== bin/run-sdk-tests"
  (cd "$worktree" && VIRTUAL_ENV=$worktree/.venv/karrio nix develop "$flake" --accept-flake-config \
    --command ./bin/run-sdk-tests) || fail "run-sdk-tests"
else
  echo "== bin/run-sdk-tests skipped (--skip-sdk)"
fi

for b in "${BRANCHES[@]}"; do
  g merge-base --is-ancestor "$b" "$next" || fail "$target does not contain $b"
done
echo "contains all ${#BRANCHES[@]} BRANCHES tips"

old=$(g rev-parse develop)
if ((promote)); then
  if [[ -n "$(git -C "$repo" status --porcelain)" ]]; then
    fail "main checkout is dirty; develop not promoted"
  fi
  if [[ "$(g symbolic-ref -q --short HEAD)" == develop ]]; then
    g reset -q --hard "$next"
  else
    g branch -f develop "$next"
  fi
  echo "develop: $(g rev-parse --short "$old") -> $(g rev-parse --short develop)"
else
  echo "develop not promoted (--no-promote); $target was $(g rev-parse --short "$next")"
fi
cleanup

echo
echo "push commands (not run):"
if ((promote)) && [[ "$(g rev-parse develop)" != "$(g rev-parse origin/develop)" ]]; then
  echo "  git push --force-with-lease=develop:$(g rev-parse origin/develop) origin develop"
fi
for b in "${BRANCHES[@]}"; do
  if ! g rev-parse --verify -q "refs/remotes/origin/$b" >/dev/null; then
    echo "  git push -u origin $b"
  elif [[ "$(g rev-parse "$b")" != "$(g rev-parse "origin/$b")" ]]; then
    if g merge-base --is-ancestor "origin/$b" "$b"; then
      echo "  git push origin $b"
    elif ! g merge-base --is-ancestor "$b" "origin/$b"; then
      echo "  git push --force-with-lease=$b:$(g rev-parse "origin/$b") origin $b"
    fi
  fi
done
