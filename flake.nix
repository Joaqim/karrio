{
  description = "Karrio modules + plugins Python development environment";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs =
    { nixpkgs, ... }:
    let
      inherit (nixpkgs) lib;
      forAllSystems = lib.genAttrs lib.systems.flakeExposed;
    in
    {
      devShells = forAllSystems (system: {
        default = import ./nix/dev-shell.nix {
          pkgs = nixpkgs.legacyPackages.${system};
        };
      });
    };
}
