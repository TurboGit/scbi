"""The environment of an interpreted command hook.

A hook runs with a minimal environment built for that call and
discarded after it, so that nothing accumulates between hooks or
modules:

- from the user's environment only the variables of ``BASE`` (PATH,
  HOME, locale, terminal...), the proxy variables and those listed in
  ``PASSTHROUGH`` by the environment file;
- every exported variable the driver set or changed: the ``SCBI_*``
  driver variables, the settings of the environment files and the
  environment actions of the module (the env hooks of its dependencies,
  its build-env / tests-env), i.e. the exported variables whose value is
  not the one of the user's environment when the driver started.
"""

from __future__ import annotations

import re

BASE = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "TERM", "TMPDIR", "DISPLAY", "LANG", "LANGUAGE")
PROXIES = ("http_proxy", "https_proxy", "ftp_proxy", "no_proxy")
_LOCALE = re.compile(r"^LC_[A-Z_]+$")


def from_user(name: str) -> bool:
    """A variable of the user's environment given to the hooks."""
    return name in BASE or _LOCALE.match(name) is not None or name.lower() in PROXIES


def hook_environment(exported: dict[str, str], initial: dict[str, str],
                     passthrough: tuple[str, ...] = ()) -> dict[str, str]:
    """The environment of a hook: ``exported`` (the exported variables of
    the driver for the module) reduced to the base variables of the user
    and to the variables the driver set or changed (``initial``: the
    environment the driver started with). ``passthrough``: other variables
    of the user's environment to give (PASSTHROUGH of the environment
    file)."""
    env = {}
    for name, value in exported.items():
        if name.startswith("BASH_FUNC_"):
            continue
        if from_user(name) or name in passthrough or initial.get(name) != value:
            env[name] = value
    return env
