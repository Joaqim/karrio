# Development shell for `nix-shell` / direnv (`use nix`).
# Pinned via npins (see nix/nixpkgs.nix); no flake required. Avoids copying the
# monorepo working tree into the store, which the flake path incurs.
{
  pkgs ? import ./nix/nixpkgs.nix { },
}:
import ./nix/dev-shell.nix { inherit pkgs; }
