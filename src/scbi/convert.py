"""Migration of legacy Bash plug-ins to the YAML format.

One-shot tool, not used by the driver at build time::

    python3 -m scbi.convert [--check] [--output-dir DIR] PLUGIN-FILE...

For each Bash plug-in, writes ``<name>.yaml`` (next to the plug-in or into
DIR) unless something cannot be expressed in the YAML format; those issues
are reported and the plug-in must be fixed by hand. With ``--check``
nothing is written. The exit status is 1 when a plug-in has issues.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scbi.plugin import yamlfmt
from scbi.plugin.legacy import LegacyLoadError, trace_plugin
from scbi.plugin.lift import Issue, lift
from scbi.plugin.registry import Registry


def convert(path: Path) -> tuple[str | None, list[Issue]]:
    """YAML text for the plug-in ``path`` (None when not convertible)."""
    try:
        #  the legacy plug-ins only (YAML versions may be next to them)
        registry = Registry(path.parent, yaml=False)
        registry.load_module(path.name)
        res = lift(registry.traces[path.name], set(registry.functions))
    except LegacyLoadError as e:
        return None, [Issue(path.name, str(e))]
    if res.issues:
        return None, res.issues
    text = yamlfmt.dump(res.plugin)
    #  The YAML must load back to the same definition
    if yamlfmt.from_data(res.plugin.name, yamlfmt.yaml.load(text, Loader=yamlfmt._Loader)) != res.plugin:
        return None, [Issue(path.name, "internal error: YAML does not load back identically")]
    return text, []


def closure(directory: Path) -> list[str]:
    """Remove the YAML version of the plug-ins inherited (directly or not)
    by a plug-in which has none: a Bash plug-in must not inherit hooks in
    the command language (they run with the interpreter, not in Bash).
    Returns the plug-ins made Bash again."""
    plugins = sorted(p.name for p in directory.iterdir()
                     if p.is_file() and not p.name.startswith((".", "_")) and not p.name[0].isdigit()
                     and "." not in p.name and not p.name.endswith("~"))
    registry = Registry(directory, yaml=False)
    for name in plugins:
        try:
            registry.load_module(name)
        except Exception:  # noqa: BLE001 - a plug-in which does not load stays Bash
            pass
    removed: list[str] = []
    changed = True
    while changed:
        changed = False
        for name in plugins:
            if (directory / f"{name}.yaml").exists():
                continue
            for parent in registry.inherits.get(name, []):
                yml = directory / f"{parent}.yaml"
                if yml.exists():
                    yml.unlink()
                    removed.append(parent)
                    changed = True
    return removed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scbi convert", description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="only report, write nothing")
    ap.add_argument("--output-dir", type=Path, help="where to write the YAML files")
    ap.add_argument("--closure", type=Path, metavar="DIR",
                    help="remove the YAML versions of the plug-ins inherited by Bash plug-ins of DIR")
    ap.add_argument("plugins", nargs="*", type=Path)
    args = ap.parse_args(argv)
    if args.closure:
        for name in closure(args.closure):
            print(f"{name}: stays Bash (inherited by a Bash plug-in)")
        return 0

    status = 0
    for path in args.plugins:
        text, issues = convert(path)
        if issues:
            status = 1
            for i in issues:
                print(f"{path}: {i.function}: {i.message}")
            continue
        if args.check:
            print(f"{path}: ok")
            continue
        out = (args.output_dir or path.parent) / f"{path.name}.yaml"
        out.write_text(text)
        print(f"{path}: written {out}")
    return status


if __name__ == "__main__":
    sys.exit(main())
