"""Start-up settings of the driver: port of the top-level code of the
runtime files (scripts.d/1_setup, 2_log, 5_tools, 6_distpkg, 8_mail,
_os_windows), which the Python driver does not read.

- the default directories (1_setup), overridden by the environment or
  the environment file settings (``${VAR:-default}``);
- ``TODAY``, the log directory of the day and the removal of old logs
  (2_log);
- the distribution (``SCBI_OS_NAME``, ``SCBI_OS_VERSION``...), the
  installed packages (``SCBI_PKGS``) and the ``os@-`` aliases
  (``SCBI_ALIAS``) of 6_distpkg;
- the status constants of 5_tools, the mail default of 8_mail.

Testsuite only (``SCBI_TESTSUITE=yes``): ``SCBI_OS_NAME=test`` is a fake
distribution whose installed packages are given by ``SCBI_TEST_PKGS``
("name=version ..."), checked as Debian packages.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from scbi.ospkg import clean_version_string

#  The 1_setup defaults, in order (a default may use a previous value)
DEFAULTS = (
    ("SCBI_ROOT", "{HOME}/dev"),
    ("SCBI_BDIR", "{SCBI_ROOT}/builds"),
    ("SCBI_PREFIX", "{SCBI_BDIR}/install"),
    ("SCBI_ARCHIVES", "{SCBI_BDIR}/.archives"),
    ("SCBI_PATCH", "{SCBI_BDIR}/.patches"),
    ("SCBI_LOGS", "{SCBI_BDIR}/.logs"),
    ("SCBI_GIT_REPO", "{SCBI_ROOT}/repositories/git"),
    ("SCBI_SVN_REPO", "{SCBI_ROOT}/repositories/svn"),
    ("SCBI_HG_REPO", "{SCBI_ROOT}/repositories/hg"),
)

#  Constants of 5_tools
CONSTANTS = {
    "SCBI_STATUS_VERSION_OK": "0", "SCBI_STATUS_VERSION_NOK": "1",
    "SCBI_STATUS_PKG_NOT_INSTALLED": "2", "SCBI_STATUS_PKG_NOT_FOUND": "3",
    "SCBI_ERROR_HOOK_NOT_FOUND": "4", "SCBI_ERROR_PLUGIN_NOT_FOUND": "5",
    "VERSION_OK": "99999999", "VERSION_ERROR": "-1",
}

#  The fake distribution of the testsuite
TEST_OS = "test"
#  Defaults not set by the test runtime file tests/scripts.d/1_setup
TEST_UNSET = ("SCBI_SVN_REPO", "SCBI_HG_REPO")


def defaults(get: Callable[[str], str]) -> dict[str, str]:
    """The 1_setup values (``get``: the current driver variables)."""
    values: dict[str, str] = {}

    def cur(name: str) -> str:
        return values[name] if name in values else get(name)

    for name, default in DEFAULTS:
        values[name] = cur(name) or default.format_map(_Lookup(cur))
    return values


class _Lookup(dict):
    def __init__(self, get: Callable[[str], str]):
        super().__init__()
        self.get_var = get

    def __missing__(self, key: str) -> str:
        return self.get_var(key)


def today() -> str:
    return time.strftime("%Y_%m_%d")


def clean_logs(logs: str, home: str, days: str) -> None:
    """Port of ``clean-scbi-logs`` (only logs under $HOME)."""
    if not logs or not home or not logs.startswith(home):
        return
    for args in (["-name", "*.log", "-ctime", f"+{days}", "-delete"],
                 ["-ctime", f"+{days}", "-empty", "-type", "d", "-delete"]):
        subprocess.run(["find", logs, *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def line_sep_file() -> str:
    """SCBI_LINE_SEP of 2_log: a file holding 1 (a new line is needed)."""
    fd, path = tempfile.mkstemp(dir="/dev/shm" if os.path.isdir("/dev/shm") else None)
    os.write(fd, b"1")
    os.close(fd)
    return path


def _output(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True, errors="replace").stdout
    except OSError:
        return ""


def _dnf_packages(rhl: bool) -> dict[str, str]:
    pkgs: dict[str, str] = {}
    for line in _output(["dnf", "repoquery", "--installed"]).splitlines():
        if line.startswith("Not root") or (rhl and "is not registered" in line) or not line.strip():
            continue
        #  <name>-<indice>:<version>-<level>.<rel>.<arch>
        n = line.strip()
        pkg = n.split(":", 1)[0].rsplit("-", 1)[0]
        pkgs[pkg] = clean_version_string(n.split(":", 1)[1] if ":" in n else n)
    return pkgs


def installed_packages(os_name: str, getvar: Callable[[str], str]) -> dict[str, str]:
    """``init-<os>-pkg``: the installed packages and their version."""
    pkgs: dict[str, str] = {}
    if os_name in ("deb", "ubt"):
        for line in _output(["dpkg-query", "-l"]).splitlines()[5:]:
            f = line.split()
            if len(f) < 3:
                continue
            pkgs[f[1].rsplit(":", 1)[0] if ":" in f[1] else f[1]] = clean_version_string(f[2])
    elif os_name in ("cos", "fed", "rhl"):
        pkgs = _dnf_packages(os_name == "rhl")
    elif os_name == "mingw":
        for line in _output(["pacman", "-Q"]).splitlines():
            f = line.split()
            if f:
                pkgs[f[0]] = clean_version_string(f[1] if len(f) > 1 else "")
    elif os_name == TEST_OS and getvar("SCBI_TESTSUITE") == "yes":
        for item in getvar("SCBI_TEST_PKGS").split():
            name, _, version = item.partition("=")
            pkgs[name] = version
    return pkgs


def _read_alias(path: Path, alias: dict[str, str]) -> None:
    """``init-alias FILE``: FILE and FILE-* (``read pkg a``)."""
    files = [path] + sorted(path.parent.glob(f"{path.name}-*")) if path.parent.is_dir() else [path]
    for f in files:
        if not f.is_file():
            continue
        for line in f.read_text(errors="replace").splitlines():
            parts = line.strip(" \t\n").split(None, 1)
            if parts:
                alias[parts[0]] = parts[1].strip(" \t") if len(parts) > 1 else ""


def distrib_alias(dist: str, plugins: str, bdir: str, cwd: str, is_windows: bool) -> dict[str, str]:
    """``init-distrib-alias DIST``."""
    names = [dist]
    if not is_windows:
        m = re.search(r"([0-9]+)(\.([0-9]+))?", _output(["lsb_release", "-r", "-s"]).strip())
        if m:
            names.append(f"{dist}~{m.group(1)}")
            if m.group(3):
                names.append(f"{dist}~{m.group(1)}.{m.group(3)}")
    alias: dict[str, str] = {}
    for name in names:
        for d in (plugins, bdir, cwd):
            prefix = ".pkgs-" if d == plugins else ".scbi-pkgs-"
            _read_alias(Path(d, f"{prefix}{name}"), alias)
    return alias


def os_packages(os_name: str, getvar: Callable[[str], str], cwd: str) -> tuple[dict[str, str], dict[str, str]]:
    """SCBI_PKGS and SCBI_ALIAS (``init-${SCBI_OS_NAME}-pkg``)."""
    pkgs = installed_packages(os_name, getvar)
    if os_name in ("deb", "ubt", "cos", "fed", "rhl", "mingw"):
        alias = distrib_alias(os_name, getvar("SCBI_PLUGINS"), getvar("SCBI_BDIR"), cwd,
                              getvar("SCBI_IS_WINDOWS") == "yes")
    else:
        alias = {}
    return pkgs, alias
