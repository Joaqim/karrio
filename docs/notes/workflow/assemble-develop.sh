#!/usr/bin/env bash
# Assemble an integration branch (the fork's develop) from feature branches.
#
# Usage: assemble-develop.sh [-r repo] [-b base] [-t target] [-w worktree] [-f]
#   -r repo      repository (default: the repository containing the current directory)
#   -b base      start point (default upstream/main)
#   -t target    branch to create (default develop-next)
#   -w worktree  worktree path (default <repo>/.worktrees/<target>)
#   -f           recreate target if it exists (never allowed for main)
#
# The target is created at base, then each branch in BRANCHES is merged in
# order with --no-ff and the message "merge: <branch>". A branch already
# contained in the target is skipped. Any conflict aborts the merge and the
# script exits 1, listing the conflicting paths; resolve by fixing the feature
# branches, not the assembled result.
#
# Author and committer dates of the merge commits are pinned to the newest
# committer date among base and the input branches, so identical inputs and
# identity yield identical commit ids.
set -euo pipefail

repo=$(git rev-parse --show-toplevel)
base=upstream/main
target=develop-next
worktree=
force=0

BRANCHES=(
  fix-core-small
  fix-state-code-normalization
  fix-fedex-state-code-countries
  fix-dashboard-carrier-options
  chore-sdk-pypdf
  feat-tracker-locale
  feat-dhl-freight-se-connector
  feat-dhl-freight-se-customs
  docs-vendored-carrier-specs
  feat-document-stamping
  feat-postnord-cn22-stamping
  feat-postnord-customs-invoice
  dev-nix-flake
  docs-openspec
)

while getopts 'r:b:t:w:f' opt; do
  case "$opt" in
  r) repo=$OPTARG ;;
  b) base=$OPTARG ;;
  t) target=$OPTARG ;;
  w) worktree=$OPTARG ;;
  f) force=1 ;;
  *) sed -n '2,11p' "$0" >&2; exit 2 ;;
  esac
done
worktree=${worktree:-$repo/.worktrees/$target}

# The user's global config sets submodule.recurse=true; merges must not
# touch the ee/ and community submodule checkouts.
g() { git -C "$repo" -c submodule.recurse=false "$@"; }
gw() { git -C "$worktree" -c submodule.recurse=false "$@"; }

if [[ "$target" == main ]]; then
  echo "refusing to assemble onto main" >&2
  exit 2
fi

for ref in "$base" "${BRANCHES[@]}"; do
  g rev-parse --verify -q "$ref^{commit}" >/dev/null || { echo "missing ref: $ref" >&2; exit 2; }
done

if g rev-parse --verify -q "refs/heads/$target" >/dev/null; then
  if ((!force)); then
    echo "branch $target exists; pass -f to recreate it" >&2
    exit 2
  fi
  if [[ -d "$worktree" ]]; then
    g worktree remove --force "$worktree"
  fi
  g branch -D "$target"
fi

pinned=$(
  for ref in "$base" "${BRANCHES[@]}"; do
    g log -1 --format='%ct %cI' "$ref"
  done | sort -n | tail -1 | cut -d' ' -f2
)
export GIT_AUTHOR_DATE=$pinned GIT_COMMITTER_DATE=$pinned

g worktree add -q -b "$target" "$worktree" "$base"

for b in "${BRANCHES[@]}"; do
  if gw merge-base --is-ancestor "$b" HEAD; then
    echo "skip   $b (already contained)"
    continue
  fi
  if gw merge --no-ff --no-edit -q -m "merge: $b" "$b"; then
    echo "merged $b"
  else
    echo "conflict merging $b:" >&2
    gw diff --name-only --diff-filter=U >&2
    gw merge --abort
    exit 1
  fi
done

echo "$target at $(gw rev-parse --short HEAD) in $worktree"
