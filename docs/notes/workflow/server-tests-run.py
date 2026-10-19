"""Run the karrio server CLI in-process against a worktree's sources only.

Invoke through server-tests-overlay.sh, which sets KARRIO_OVERLAY_WORKTREE and
KARRIO_OVERLAY_MAIN. Editable installs of the main checkout are removed from
the import machinery before karrio is imported, and the run fails with exit
status 3 if any karrio module was still loaded from outside the worktree.
"""

import os
import sys

WORKTREE = os.path.join(os.environ["KARRIO_OVERLAY_WORKTREE"], "")
MAIN = os.path.join(os.environ["KARRIO_OVERLAY_MAIN"], "")
VENV = os.path.join(os.environ.get("VIRTUAL_ENV", MAIN + ".venv"), "")


def is_editable(obj) -> bool:
    return "__editable__" in (getattr(obj, "__module__", "") or "") or (
        "__editable__" in type(obj).__module__
    )


def isolate() -> None:
    """Drop main-checkout editable installs so only worktree sources are importable."""
    dropped = [
        path
        for path in sys.path
        if path.startswith("__editable__")
        or (
            path.startswith(MAIN)
            and not path.startswith(WORKTREE)
            and not path.startswith(VENV)
        )
    ]
    sys.path[:] = [path for path in sys.path if path not in dropped]
    sys.meta_path[:] = [finder for finder in sys.meta_path if not is_editable(finder)]
    sys.path_hooks[:] = [hook for hook in sys.path_hooks if not is_editable(hook)]
    sys.path_importer_cache.clear()
    print(f"[server-tests] dropped sys.path entries: {dropped}", file=sys.stderr)


def outside_modules() -> list:
    return sorted(
        f"{name} -> {path}"
        for name, module in list(sys.modules.items())
        if name.startswith("karrio")
        and getattr(module, "__file__", None)
        and (path := os.path.realpath(module.__file__)).startswith(MAIN)
        and not path.startswith(WORKTREE)
    )


def main() -> int:
    isolate()
    sys.argv = ["karrio", *sys.argv[1:]]

    from karrio.server.__main__ import main as karrio_main

    try:
        status = karrio_main()
    except SystemExit as exit_:
        status = exit_.code

    outside = outside_modules()
    print(
        f"[server-tests] karrio modules loaded from outside the worktree: {len(outside)}",
        file=sys.stderr,
    )
    print("\n".join(f"[server-tests]   {line}" for line in outside), file=sys.stderr)

    if outside:
        return 3

    return 0 if status is None else status if isinstance(status, int) else 1


if __name__ == "__main__":
    sys.exit(main())
