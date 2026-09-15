# Python package-set overrides for karrio dependencies absent from nixpkgs.
# Consumed by both flake.nix (`nix develop`) and shell.nix (`nix-shell`) so the
# two entry points stay in sync. Apply via:
#   python3.override { self = python; packageOverrides = import ./nix/python-overlay.nix; }
pyfinal: pyprev: {
  django-constance = pyfinal.callPackage ./pkgs/django-constance.nix { };
  jstruct = pyfinal.callPackage ./pkgs/jstruct.nix { };
  generateDS = pyfinal.callPackage ./pkgs/generateds.nix { };
}
