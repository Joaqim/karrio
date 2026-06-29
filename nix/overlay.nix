_final: prev:
let
  python = prev.python3.override {
    self = python;
    packageOverrides = import ./python-overlay.nix;
  };
in
{
  inherit python;
}
