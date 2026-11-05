# Karrio modules + plugins development shell.
#
# Provides a Python interpreter carrying the third-party dependencies of the
# SDK, CLI, connectors and plugins (from nixpkgs plus the out-of-tree
# derivations in ./pkgs), and puts the local pure-Python sources on PYTHONPATH
# as editable namespace packages. No virtualenv or pip install step is needed.
#
# `withPyPDF2` adds PyPDF2 for branches based on upstream karrio, which still
# import it (the fork's branches use pypdf). PyPDF2 is flagged with known
# vulnerabilities in nixpkgs; that flag is cleared only in the package set of
# the shell built with `withPyPDF2 = true`.
{
  pkgs,
  withPyPDF2 ? false,
}:
let
  inherit (pkgs) lib;

  allowPyPDF2 = _pyfinal: pyprev: {
    pypdf2 = pyprev.pypdf2.overrideAttrs (old: {
      meta = old.meta // {
        knownVulnerabilities = [ ];
      };
    });
  };

  python = pkgs.python312.override {
    self = python;
    packageOverrides = lib.composeManyExtensions (
      [ (import ./python-overlay.nix) ] ++ lib.optional withPyPDF2 allowPyPDF2
    );
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
      ps.pypdf
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
    ++ lib.optional withPyPDF2 ps.pypdf2
  );

  # `kcli` is the modules/cli console entry point (pyproject `kcli =
  # "karrio_cli.__main__:app"`). The local CLI source is not pip-installed in
  # this env, so reproduce the script as a wrapper that runs the pinned
  # interpreter against the editable source carried on PYTHONPATH by the
  # shellHook below. This lets connector `generate` scripts and
  # `bin/run-generate-on` (which invoke `kcli`) work unmodified.
  kcli = pkgs.writeShellScriptBin "kcli" ''
    exec ${pythonEnv}/bin/python3 -m karrio_cli "$@"
  '';
in
pkgs.mkShell {
  name = if withPyPDF2 then "karrio-dev-upstream" else "karrio-dev";

  packages = [
    pythonEnv
    kcli
    pkgs.uv
  ];

  shellHook = ''
    # karrio is a pkgutil namespace package (extend_path), so adding each
    # module/connector/plugin source root to PYTHONPATH merges the
    # karrio.{mappers,providers,schemas,plugins}.* subpackages across them with
    # no install step. Editing the sources takes effect immediately.
    # Root at the git toplevel so a shell entered from a subdirectory, or a
    # worktree nested inside another checkout, resolves its own sources.
    root="$(${pkgs.git}/bin/git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"
    # Core source roots (sdk provides karrio.*, soap provides pysoap, cli
    # provides karrio_cli) are always on the path.
    extra="$root/modules/sdk:$root/modules/soap:$root/modules/cli"
    # Connectors and plugins extend the karrio namespace; include those present.
    for d in "$root"/modules/connectors/*/ "$root"/plugins/*/ ; do
      if [ -d "$d/karrio" ]; then
        extra="$d:$extra"
      fi
    done
    # The inherited PYTHONPATH is dropped: carrying it over lets modules absent
    # from this checkout resolve to another checkout's sources.
    export PYTHONPATH="$extra"
    export KARRIO_DEV_ROOT="$root"

    # This nix shell is an alternative entry point alongside the standard
    # bin/activate-env virtualenv workflow; it does not replace it. Surface the
    # constraints that differ from the venv so codegen and scaffolding behave
    # predictably here.
    cat >&2 <<'KARRIO_ENV_NOTE'
karrio nix dev shell active (alternative to `source bin/activate-env`).
  - `kcli` and `./bin/cli` both run the editable local CLI source with no
    pip/virtualenv step (kcli is provided here as a wrapper around the pinned
    interpreter), so connector `generate` scripts and `bin/run-generate-on` work.
  - Local sources (sdk, soap, cli, connectors, plugins) are on PYTHONPATH; a
    newly scaffolded connector joins PYTHONPATH on the next shell entry (e.g.
    `direnv reload`).
KARRIO_ENV_NOTE
  '';
}
