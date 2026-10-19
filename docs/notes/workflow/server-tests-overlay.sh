#!/usr/bin/env bash
# Run a command against a worktree's sources using the main checkout's venv.
#
# Usage: server-tests-overlay.sh <worktree> <command> [args...]
#
# Environment overrides:
#   KARRIO_VENV       venv providing Django and third-party packages
#                     (default: <main checkout>/.venv/karrio)
#   KARRIO_DEV_FLAKE  flake whose locked nixpkgs and #upstream shell provide
#                     WeasyPrint's native libraries and PyPDF2
#                     (default: git+file://<main checkout>?ref=dev-nix-flake)
set -euo pipefail

if (($# < 2)); then
  echo "usage: $(basename "$0") <worktree> <command> [args...]" >&2
  exit 64
fi

worktree=$(realpath "$1")
shift

common_dir=$(git -C "$worktree" rev-parse --path-format=absolute --git-common-dir)
main_checkout=$(dirname "$common_dir")
venv=${KARRIO_VENV:-$main_checkout/.venv/karrio}
flake=${KARRIO_DEV_FLAKE:-git+file://$main_checkout?ref=dev-nix-flake}
cache=${XDG_CACHE_HOME:-$HOME/.cache}/karrio-server-tests

pythonpath=$worktree/apps/api
for dir in "$worktree"/modules/*/ "$worktree"/modules/connectors/*/ "$worktree"/plugins/*/ \
  "$worktree"/ee/insiders/modules/*/ "$worktree"/ee/platform/modules/*/; do
  if [[ -d $dir/karrio || -d $dir/karrio_cli || -d $dir/pysoap ]]; then
    pythonpath+=:${dir%/}
  fi
done

# Expose only PyPDF2 from the nix upstream shell, not its whole site-packages.
pypdf2=$(nix develop "$flake#upstream" --command python -c \
  'import PyPDF2; print(PyPDF2.__path__[0])')
mkdir -p "$cache/pypdf2"
ln -sfn "$pypdf2" "$cache/pypdf2/PyPDF2"

mapfile -t native_libs < <(nix build --no-link --print-out-paths --inputs-from "$flake" \
  nixpkgs#glib.out nixpkgs#pango.out nixpkgs#harfbuzz.out nixpkgs#fontconfig.lib)
ld_library_path=$(printf '%s/lib:' "${native_libs[@]}")

export PYTHONPATH=$pythonpath:$cache/pypdf2
export VIRTUAL_ENV=$venv
export PATH=$venv/bin:$PATH
export LD_LIBRARY_PATH=${ld_library_path%:}
export KARRIO_OVERLAY_WORKTREE=$worktree
export KARRIO_OVERLAY_MAIN=$main_checkout

cd "$worktree"
exec "$@"
