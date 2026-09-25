#!/usr/bin/env bash
# Report whether the generated develop branch is current with its inputs.
#
# Usage: develop-status.sh [--fetch] [-r repo]
#   --fetch   fetch origin and upstream first (default: no network access)
#   -r repo   any checkout of the repository (default: the current directory)
#
# BRANCHES is read from the committed tip of docs-openspec, the branch that
# owns assemble-develop.sh, so the report does not depend on which checkout
# runs it or on how stale that checkout's copy of the script is.
#
# Exit status: 0 when develop contains every BRANCHES tip, 1 when it does not,
# 2 when a required ref is missing or another error occurs.
set -euo pipefail

owner=docs-openspec
assembler=docs/notes/workflow/assemble-develop.sh
fetch=0
start=.

while (($#)); do
  case "$1" in
  --fetch) fetch=1 ;;
  -r) start=${2:?-r needs a path}; shift ;;
  -h | --help) sed -n '2,13p' "$0"; exit 0 ;;
  *) sed -n '2,13p' "$0" >&2; exit 2 ;;
  esac
  shift
done

common=$(git -C "$start" rev-parse --path-format=absolute --git-common-dir) || exit 2
repo=$(dirname "$common")
g() { git -C "$repo" -c submodule.recurse=false "$@"; }
sha() { g rev-parse --verify -q "$1^{commit}"; }
short() { g rev-parse --short "$1"; }

if ((fetch)); then
  g fetch -q --no-recurse-submodules origin
  g fetch -q --no-recurse-submodules upstream
fi

for ref in "$owner" develop upstream/main; do
  sha "$ref" >/dev/null || { echo "missing ref: $ref" >&2; exit 2; }
done

mapfile -t BRANCHES < <(
  g show "$owner:$assembler" |
    sed -n '/^BRANCHES=(/,/^)/p' | sed '1d;$d' | tr -d ' \t' | grep -v '^$'
)
((${#BRANCHES[@]})) || { echo "no BRANCHES found in $owner:$assembler" >&2; exit 2; }

status=0
problems=()

compare() {
  local ahead behind
  read -r ahead behind < <(g rev-list --left-right --count "$1...$2")
  if ((ahead == 0 && behind == 0)); then echo equal
  elif ((behind == 0)); then echo "ahead $ahead"
  elif ((ahead == 0)); then echo "behind $behind"
  else echo "diverged +$ahead/-$behind"
  fi
}

printf 'BRANCHES  %s from %s@%s\n' "${#BRANCHES[@]}" "$owner" "$(short "$owner")"
printf '%-32s %-11s %s\n' branch develop origin
for b in "${BRANCHES[@]}"; do
  if ! sha "refs/heads/$b" >/dev/null; then
    printf '%-32s %-11s %s\n' "$b" missing -
    problems+=("$b missing locally")
    status=2
    continue
  fi
  if g merge-base --is-ancestor "$b" develop; then
    in=contained
  else
    in=MISSING
    ((status == 2)) || status=1
  fi
  if sha "refs/remotes/origin/$b" >/dev/null; then
    remote=$(compare "$b" "origin/$b")
  else
    remote="no remote"
  fi
  printf '%-32s %-11s %s\n' "$b" "$in" "$remote"
done

for ((i = 0; i < ${#BRANCHES[@]}; i++)); do
  for ((j = i + 1; j < ${#BRANCHES[@]}; j++)); do
    [[ "$(sha "${BRANCHES[j]}")" != "$(sha "${BRANCHES[i]}")" ]] || continue
    if g merge-base --is-ancestor "${BRANCHES[j]}" "${BRANCHES[i]}" 2>/dev/null; then
      problems+=("order: ${BRANCHES[j]} is a parent of ${BRANCHES[i]} but is listed after it")
    fi
  done
done

echo
if sha refs/remotes/origin/develop >/dev/null; then
  printf 'develop        %s  vs origin/develop %s: %s\n' \
    "$(short develop)" "$(short origin/develop)" "$(compare develop origin/develop)"
else
  printf 'develop        %s  no origin/develop\n' "$(short develop)"
fi
behind=$(g rev-list --count develop..upstream/main)
if ((behind)); then
  printf 'upstream/main  %s  develop base is behind by %s\n' "$(short upstream/main)" "$behind"
else
  printf 'upstream/main  %s  contained in develop\n' "$(short upstream/main)"
fi

base=$(g merge-base develop upstream/main)
mapfile -t merged < <(g log --first-parent --format=%s "$base..develop" | sed -n 's/^merge: //p')
for m in "${merged[@]}"; do
  [[ " ${BRANCHES[*]} " == *" $m "* ]] || problems+=("develop merges $m, which is not in BRANCHES")
done

echo
echo "worktrees"
main_branch=$(g symbolic-ref -q --short HEAD || echo detached)
main_dirty=$(git -C "$repo" status --porcelain | wc -l)
printf '  %-32s %-32s %s\n' "(main checkout)" "$main_branch" \
  "$( ((main_dirty)) && echo "dirty ($main_dirty)" || echo clean)"
[[ "$main_branch" == develop ]] || problems+=("main checkout is on $main_branch, expected develop")

while read -r key value; do
  case "$key" in
  worktree) wt=$value; wb=detached ;;
  branch) wb=${value#refs/heads/} ;;
  "")
    [[ "${wt:-}" == "$repo/.worktrees/"* ]] || { wt=; continue; }
    dirty=$(git -C "$wt" status --porcelain --ignore-submodules=all | wc -l)
    state=$( ((dirty)) && echo "dirty ($dirty)" || echo clean)
    if [[ " ${BRANCHES[*]} " != *" $wb "* ]]; then
      case "$wb" in
      docs-* | dev-* | develop-next) ;;
      *)
        state="$state, unregistered"
        problems+=("worktree ${wt#"$repo"/} is on $wb, which is not in BRANCHES")
        ;;
      esac
    fi
    printf '  %-32s %-32s %s\n' "${wt#"$repo"/.worktrees/}" "$wb" "$state"
    wt=
    ;;
  esac
done < <(g worktree list --porcelain; echo)

wt_owner=$repo/.worktrees/$owner
if [[ -d "$wt_owner" ]] && ! git -C "$wt_owner" diff --quiet HEAD -- "$assembler"; then
  problems+=("$assembler has uncommitted edits in .worktrees/$owner; they are not used until committed")
fi

echo
for p in "${problems[@]}"; do echo "warning: $p"; done
case "$status" in
0) echo "develop: current (contains every BRANCHES tip)" ;;
1) echo "develop: STALE (run rebuild-develop.sh)" ;;
*) echo "develop: ERROR" ;;
esac
exit "$status"
