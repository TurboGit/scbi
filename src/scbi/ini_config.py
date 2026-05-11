from __future__ import annotations

import configparser
import os
import re
from pathlib import Path
from typing import Any


CONTROLLED_VARS: dict[str, str] = {
    "build-dir": "SCBI_BDIR",
    "env": "ENV_NAME",
    "git-repo": "SCBI_GIT_REPO",
    "hg-repo": "SCBI_HG_REPO",
    "jobs": "SCBI_JOBS",
    "log": "SCBI_LOGS",
    "patch": "SCBI_PATCH",
    "plan": "SCBI_PLAN",
    "plugins": "SCBI_PLUGINS",
    "prefix": "SCBI_PREFIX",
    "root-dir": "SCBI_ROOT",
    "svn-repo": "SCBI_SVN_REPO",
    "archives": "SCBI_ARCHIVES",
    "target": "SCBI_TARGET",
}

BOOL_OPTIONS = {"safe", "tar", "no-patch", "clear-cache"}

STEP_OPTIONS = {
    "setup", "config", "build", "install", "wrapup",
    "quiet", "force", "update", "purge", "archive", "stat",
}


class IniConfig:
    def __init__(self) -> None:
        self._db: dict[str, str] = {}
        self._loaded_files: list[Path] = []

    def load_files(self, extra_file: str | Path | None = None) -> None:
        search_order: list[Path | None] = [
            Path.home() / ".scbi",
            Path.cwd() / ".scbi",
        ]
        if extra_file:
            search_order.append(Path(extra_file))

        for f in search_order:
            if f is not None and f.is_file():
                self._load_file(f)
                self._loaded_files.append(f)

    def _load_file(self, path: Path) -> None:
        text = path.read_text()
        cur_section = ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r'^\[(.+)\]$', line)
            if m:
                cur_section = m.group(1).strip()
                continue
            m = re.match(r'^([^=]+)=(.*)$', line)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                if not key:
                    continue
                db_key = f"{cur_section}.{key}" if cur_section else key
                if key in ("enable", "modules", "options"):
                    self._db[db_key] = self._db.get(db_key, "") + val + " "
                else:
                    self._db[db_key] = val

    def get_option(self, section: str | None, var: str) -> str:
        key = f"{section}.{var}"
        if key in self._db:
            return self._db[key]
        if section and f"common.{var}" in self._db:
            return self._db[f"common.{var}"]
        if var in self._db:
            return self._db[var]
        return ""

    def apply_values(
        self, section: str | None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        skip = {
            "setup", "config", "build", "install", "wrapup",
            "force", "modules", "stat", "update", "purge", "archive",
            "deps", "safe", "tar", "no-patch", "enable", "run",
            "tests", "tests-list", "options",
        }

        for db_key, db_val in self._db.items():
            if "." in db_key:
                sec, var = db_key.split(".", 1)
            else:
                sec, var = "", db_key

            if sec and section and sec != section and sec != "common":
                continue
            if not sec and section:
                continue
            if sec == "common" and not section:
                continue

            if var in skip:
                continue

            if var in CONTROLLED_VARS:
                target = CONTROLLED_VARS[var]
                val = self.get_option(section, var)
                if val and target not in result:
                    result[target] = val
            else:
                py_var = var.replace("-", "_")
                val = db_val
                if val:
                    result[py_var] = val

        enable_val = self.get_option(section, "enable")
        if enable_val:
            features = [f.strip() for f in enable_val.replace(",", " ").split()]
            for feat in features:
                if feat:
                    key = f"SCBI_{feat.replace('-', '_')}_SET"
                    result[key] = "true"

        modules_val = self.get_option(section, "modules")
        if modules_val:
            result["SCBI_INI_MODULES"] = modules_val.strip().split()

        for opt in STEP_OPTIONS:
            val = self.get_option(section, opt)
            if val:
                var_upper = f"DO_{opt.upper()}"
                result[var_upper] = val

        bool_opts = []
        for opt in BOOL_OPTIONS:
            val = self.get_option(section, opt)
            if val and val.upper() == "YES":
                bool_opts.append(f"--{opt}")
        if bool_opts:
            result["SCBI_INI_OPTIONS"] = bool_opts

        deps_val = self.get_option(section, "deps")
        if deps_val:
            result["DEPS"] = deps_val

        run_val = self.get_option(section, "run")
        if run_val:
            result["DO_RUN"] = "yes"
            result["DO_RUN_CMD"] = run_val

        tests_val = self.get_option(section, "tests")
        if tests_val:
            result["DO_TEST"] = "yes"
            if tests_val == "only":
                result["DO_TEST"] = "yes-only"

        tests_list = self.get_option(section, "tests-list")
        if tests_list:
            result["SCBI_TESTS_OPTIONS"] = tests_list

        opts_val = self.get_option(section, "options")
        if opts_val:
            existing = result.get("SCBI_INI_OPTIONS", [])
            result["SCBI_INI_OPTIONS"] = existing + opts_val.strip().split()

        return result


def load_module_env(name: str | None, plugins_dir: Path) -> tuple[str | None, Path | None]:
    ename = f"env{'-' + name if name else ''}"
    candidates = [
        Path.cwd() / f".scbi-{ename}",
        Path.cwd().parent / f".scbi-{ename}",
        Path.home() / f".scbi-{ename}",
        plugins_dir / f".{ename}",
    ]
    for p in candidates:
        if p.is_file():
            return (str(p.parent), p)
    if name:
        print(f"build environment .{ename} not found", file=__import__("sys").stderr)
        __import__("sys").exit(1)
    return (None, None)


def parse_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    text = path.read_text()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            val = val.strip("'\"")
            env[key] = val
            continue
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            val = val.strip("'\"")
            env[key] = val
    return env
