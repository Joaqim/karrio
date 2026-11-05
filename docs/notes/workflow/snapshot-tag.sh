#!/usr/bin/env bash
# Tag a deployed develop tip as a transient snapshot.
#
# Usage: snapshot-tag.sh [-r repo] [-o remote] [rev]
#   -r repo      repository (default: the repository containing the current directory)
#   -o remote    remote whose tags are also considered (default origin)
#   rev          commit to tag (default develop)
#
# Creates the local annotated tag snapshot-YYYY.MM.DD.N on rev, where the
# date is the UTC committer date of rev and N is one more than the highest
# snapshot-<date>.N among the local tags and the remote's tags, starting at 1.
# If rev already carries a snapshot-* tag, locally or on the remote, nothing
# is created. Either way the tag name is printed on stdout. Nothing is pushed.
set -euo pipefail

repo=$(git rev-parse --show-toplevel)
remote=origin

while getopts 'r:o:' opt; do
  case "$opt" in
  r) repo=$OPTARG ;;
  o) remote=$OPTARG ;;
  *) sed -n '2,7p' "$0" >&2; exit 2 ;;
  esac
done
shift $((OPTIND - 1))
rev=${1:-develop}

g() { git -C "$repo" -c submodule.recurse=false "$@"; }

commit=$(g rev-parse --verify -q "$rev^{commit}") || { echo "missing ref: $rev" >&2; exit 2; }

# Lines of "<sha> <tag>", where sha is the commit the tag peels to.
remote_tags=$(g ls-remote --tags "$remote" 'refs/tags/snapshot-*') || { echo "cannot list tags of $remote" >&2; exit 2; }
tags=$(
  g for-each-ref --format='%(*objectname) %(objectname) %(refname:short)' 'refs/tags/snapshot-*' |
    awk '{ print $1, $NF }'
  awk '{ ref = $2; sub(/^refs\/tags\//, "", ref); sha[ref] = $1; if (ref ~ /\^\{\}$/) { sub(/\^\{\}$/, "", ref); peeled[ref] = $1 } }
    END { for (r in sha) if (r !~ /\^\{\}$/) print (r in peeled ? peeled[r] : sha[r]), r }' <<<"$remote_tags"
)

existing=$(awk -v c="$commit" '$1 == c { print $2 }' <<<"$tags" | sort -u | head -1)
if [[ -n "$existing" ]]; then
  echo "exists $existing on $(g rev-parse --short "$commit")" >&2
  echo "$existing"
  exit 0
fi

date=$(TZ=UTC g log -1 --format=%cd --date=format-local:%Y.%m.%d "$commit")
n=$(awk -v p="snapshot-$date." 'index($2, p) == 1 { s = substr($2, length(p) + 1); if (s ~ /^[0-9]+$/ && s + 0 > m) m = s + 0 } END { print m + 1 }' <<<"$tags")
tag=snapshot-$date.$n

mapfile -t merged < <(
  g log --first-parent --format=%s -n 200 "$commit" |
    awk '!stop && /^merge: / { print substr($0, 8); next } { stop = 1 }' | tac
)
message="Transient snapshot of generated develop. Not a release; may be deleted once nothing references it."
if ((${#merged[@]})); then
  message+=$'\n\nMerged branches:\n'$(printf '  %s\n' "${merged[@]}")
fi

g tag -a -m "$message" "$tag" "$commit"
echo "tagged $tag on $(g rev-parse --short "$commit")" >&2
echo "$tag"
