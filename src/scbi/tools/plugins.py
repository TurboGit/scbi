"""The plug-ins given to scbi lint / scbi format: YAML plug-ins only."""

from __future__ import annotations

from pathlib import Path

CONVERT_HINT = "not a YAML plug-in, convert it with: python3 -m scbi.convert"


def resolve(driver, name: str) -> tuple[Path | None, str]:
    """The YAML file of ``name`` (a path or a plug-in of $SCBI_PLUGINS),
    or None and the reason."""
    plugins = Path(driver.get("SCBI_PLUGINS"))
    candidates = [Path(name)] if "/" in name or name.endswith(".yaml") else []
    candidates += [plugins / name if name.endswith(".yaml") else plugins / f"{name}.yaml"]
    for c in candidates:
        if c.is_file():
            if c.suffix != ".yaml":
                return None, CONVERT_HINT
            return c, ""
    legacy = Path(name) if "/" in name else plugins / name
    if legacy.is_file():
        return None, CONVERT_HINT
    return None, "not found"


def display(driver, path: Path) -> str:
    home = driver.get("HOME")
    text = str(path)
    return text.replace(home, "$HOME", 1) if home and text.startswith(home) else text
