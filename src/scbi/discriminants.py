"""OS discriminants (port of ``get-distrib`` and ``setup-discriminants``).

Discriminants are words describing the running machine (distribution,
version, codename, architecture, host and domain names, cross target...)
used by plan barriers and ``@on``. The probing of the machine is separated
from the computation so that the latter can be tested.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass

OS_NAMES = ("deb", "ubt", "cos", "rhl", "fed", "win", "mingw")


@dataclass
class LsbInfo:
    """Raw output lines of ``lsb_release -d / -r / -i / -c``."""

    description: str = ""  # "Description:\tDebian GNU/Linux 12 (bookworm)"
    release: str = ""  # "Release:\t12"
    distributor: str = ""  # "Distributor ID:\tDebian"
    codename: str = ""  # "Codename:\tbookworm"


@dataclass
class HostInfo:
    lsb: LsbInfo
    machine: str  # uname -m
    hostname_short: str  # hostname --short
    domain: str  # hostname --domain
    is_windows: bool = False
    mingw_prefix: str = ""


def get_distrib(info: HostInfo) -> str:
    """Port of ``get-distrib``."""
    if info.is_windows:
        return "mingw" if info.mingw_prefix else "win"
    des = info.lsb.description
    for word, name in (
        ("Debian", "deb"),
        ("Ubuntu", "ubt"),
        ("Red Hat", "rhl"),
        ("CentOS", "cos"),
        ("Fedora", "fed"),
    ):
        if word in des:
            return name
    return "none"


def _lsb_value(line: str) -> str:
    #  ${VAR#*:+([[:blank:]])}: shortest prefix, so up to the first ':'
    #  followed by a single blank
    m = re.match(r"^[^:]*?:[ \t]", line)
    return line[m.end() :] if m else line


@dataclass
class OsInfo:
    name: str
    version: str
    codename: str
    major_version: str
    os_id: str
    discriminants: list[str]  # in insertion order

    def as_set(self) -> set[str]:
        return set(self.discriminants)


def setup_discriminants(info: HostInfo, host: str, target: str) -> OsInfo:
    """Port of the discriminants initialization of scripts.d/6_distpkg."""
    name = get_distrib(info)
    discs: list[str] = [name]
    version = codename = major = os_id = "unknown"

    def add(d: str) -> None:
        if d not in discs:
            discs.append(d)

    if info.is_windows:
        add("windows")
    else:
        ver = _lsb_value(info.lsb.release)
        oid = _lsb_value(info.lsb.distributor)
        cnm = _lsb_value(info.lsb.codename)
        des = _lsb_value(info.lsb.description)
        if ver.startswith("n/a"):
            ver = ver[3:]
        des = des.replace("/", " ").replace("(", " ").replace(")", " ")

        version, codename, os_id = ver, cnm, oid
        major = version.split(".", 1)[0]

        for d in des.lower().split():
            add(d)
        add(info.machine)
        add(info.hostname_short)
        if info.domain:
            add(info.domain)
        add(os_id.lower())
        if version:
            add(version)
        if major:
            add(major)
        add(codename.lower())

    if host == target:
        add("native")
    else:
        add("cross")
        for part in target.replace("-", " ").split():
            add(f"target-{part}".lower())

    return OsInfo(name, version, codename, major, os_id, discs)


def forced_discriminants(os_name: str, os_version: str, os_major: str) -> list[str]:
    """Discriminants when SCBI_OS_NAME is forced (testsuite)."""
    return [os_major or "default", os_version or "default", os_name or "default"]


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True).stdout.rstrip("\n")
    except OSError:
        return ""


def probe_host() -> HostInfo:
    """Gather the information about the running machine."""
    uname = " ".join(platform.uname())
    is_windows = bool(re.search(r"Cygwin|Msys", uname))
    lsb = LsbInfo()
    if not is_windows:
        lsb = LsbInfo(
            description=_run(["lsb_release", "-d"]),
            release=_run(["lsb_release", "-r"]),
            distributor=_run(["lsb_release", "-i"]),
            codename=_run(["lsb_release", "-c"]),
        )
    return HostInfo(
        lsb=lsb,
        machine=platform.machine(),
        hostname_short=_run(["hostname", "--short"]),
        domain=_run(["hostname", "--domain"]),
        is_windows=is_windows,
        mingw_prefix=os.environ.get("MINGW_PREFIX", ""),
    )
