from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from .models import Plugin
from .plugin_loader_yaml import PluginLoader


def _get_os_name() -> str:
    try:
        import distro
        return distro.id().lower()
    except ImportError:
        pass
    return platform.system().lower()


def _check_debian_pkg(pkg: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["dpkg", "-l", pkg],
            capture_output=True, text=True,
        )
        for line in result.stdout.splitlines():
            if line.startswith("ii") and pkg in line:
                parts = line.split()
                if len(parts) >= 3:
                    return (True, parts[2])
        return (False, "0")
    except FileNotFoundError:
        return (False, "0")


def _check_rpm_pkg(pkg: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["rpm", "-q", pkg, "--queryformat", "%{VERSION}"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return (True, result.stdout.strip())
        return (False, "0")
    except FileNotFoundError:
        return (False, "0")


def check_os_package(name: str) -> tuple[bool, str]:
    os_name = _get_os_name()
    for family, checker in [
        ("debian", _check_debian_pkg),
        ("ubuntu", _check_debian_pkg),
        ("linuxmint", _check_debian_pkg),
        ("fedora", _check_rpm_pkg),
        ("rhel", _check_rpm_pkg),
        ("centos", _check_rpm_pkg),
    ]:
        if os_name.startswith(family):
            pkg_name = name.replace("os@-", "")
            return checker(pkg_name)
    return (False, "0")


DEP_HOOK_NAMES = ["build-depends", "depends", "tests-depends"]


def _get_os_deps_from_hooks(
    loader: PluginLoader,
    plugin: Plugin,
    variant: str,
) -> list[str]:
    os_deps: list[str] = []
    for hook_name in DEP_HOOK_NAMES:
        resolved = loader.resolve_all_hooks(plugin, variant, hook_name)
        for item_list in resolved:
            if isinstance(item_list, list):
                for item in item_list:
                    item_str = str(item).strip()
                    dep = item_str.split(":")[0].strip()
                    if dep.startswith("os@-"):
                        os_deps.append(dep)
    return os_deps


def resolve_auto_variant(
    loader: PluginLoader,
    plugin: Plugin,
    variant: str,
    plugins_dir: Path,
) -> tuple[str, str | None]:
    if not variant.startswith("auto"):
        return (variant, None)

    rest = variant[4:]
    if rest.startswith("."):
        rest = rest[1:]

    os_deps = _get_os_deps_from_hooks(loader, plugin, variant)

    if not os_deps:
        return (variant, None)

    all_found = True
    for dep in os_deps:
        found, _ = check_os_package(dep)
        if not found:
            all_found = False
            break

    if all_found:
        new_variant = f"native{'.' + rest if rest else ''}"
        return (new_variant, "native variant selected (system packages found)")
    elif rest:
        return (rest, f"auto variant '{variant}' resolved to '{rest}'")
    else:
        return ("default", "auto variant resolved to default (system packages not found)")
