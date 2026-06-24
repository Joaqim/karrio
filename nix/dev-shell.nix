# Karrio modules + plugins development shell.
#
# Provides a Python interpreter carrying the third-party dependencies of the
# SDK, CLI, connectors and plugins (from nixpkgs plus the out-of-tree
# derivations in ./pkgs), and puts the local pure-Python sources on PYTHONPATH
# as editable namespace packages. No virtualenv or pip install step is needed.
{ pkgs }:
let
  python = pkgs.python3.override {
    self = python;
    packageOverrides = import ./python-overlay.nix;
  };

  pythonEnv = python.withPackages (
    ps:
    [
      # SDK runtime (modules/sdk)
      ps.attrs
      ps.jstruct
      ps.xmltodict
      ps.lxml
      ps.pillow
      ps.phonenumbers
      ps.python-barcode
      ps.pypdf2
      ps.toml
      ps.loguru
      # CLI (modules/cli)
      ps.typer
      ps.rich
      ps.requests
      ps.importlib-metadata
      ps.generateDS
      ps.tabulate
      ps.jinja2
      ps.fastapi
      ps.uvicorn
      ps.python-multipart
      # py-soap (modules/soap) third-party deps; the package itself is local
      ps.six
      # CLI dev extras (modules/cli[dev])
      ps.python-dotenv
      ps.beautifulsoup4
      # Django live-settings dependency used by the server modules
      ps.django-constance
    ]
  );
in
pkgs.mkShell {
  name = "karrio-dev";

  packages = [
    pythonEnv
    pkgs.uv
  ];

  shellHook = ''
    # karrio is a pkgutil namespace package (extend_path), so adding each
    # module/connector/plugin source root to PYTHONPATH merges the
    # karrio.{mappers,providers,schemas,plugins}.* subpackages across them with
    # no install step. Editing the sources takes effect immediately.
    root="$PWD"
    # Core source roots (sdk provides karrio.*, soap provides pysoap, cli
    # provides karrio_cli) are always on the path.
    extra="$root/modules/sdk:$root/modules/soap:$root/modules/cli"
    # Connectors and plugins extend the karrio namespace; include those present.
    for d in "$root"/modules/connectors/*/ "$root"/plugins/*/ ; do
      if [ -d "$d/karrio" ]; then
        extra="$d:$extra"
      fi
    done
    export PYTHONPATH="$extra:$PYTHONPATH"

    # This nix shell is an alternative entry point alongside the standard
    # bin/activate-env virtualenv workflow; it does not replace it. Surface the
    # constraints that differ from the venv so codegen and scaffolding behave
    # predictably here.
    cat >&2 <<'KARRIO_ENV_NOTE'
karrio nix dev shell active (alternative to `source bin/activate-env`).
  - The `kcli` console script is not installed in this env. Invoke the CLI as
    `./bin/cli ...` instead. For schema codegen, the connector `generate`
    scripts and `bin/run-generate-on` call `kcli`; run codegen directly with
    `./bin/cli codegen generate <schema.json> <out.py>` until a `kcli` wrapper
    is added here.
  - Local sources (sdk, soap, cli, connectors, plugins) are on PYTHONPATH with
    no pip/virtualenv step; a newly scaffolded connector joins PYTHONPATH on the
    next shell entry (e.g. `direnv reload`).
KARRIO_ENV_NOTE
  '';
}
