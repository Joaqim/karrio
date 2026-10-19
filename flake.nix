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
      devShells = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = import ./nix/dev-shell.nix { inherit pkgs; };
          upstream = import ./nix/dev-shell.nix {
            inherit pkgs;
            withPyPDF2 = true;
          };
        }
      );
    };
}
