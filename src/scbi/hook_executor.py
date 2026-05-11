from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import IO

from .build_env import BuildEnv


def apply_env_operation(
    env: dict[str, str], op: str, var: str, value: str | None, sep: str = ":"
) -> None:
    if op in ("add-to-var",):
        if value is None:
            return
        current = env.get(var, "")
        parts = current.split(sep) if current else []
        if value not in parts:
            parts.insert(0, value)
        env[var] = sep.join(parts)
    elif op in ("prepend-to-var",):
        if value is None:
            return
        current = env.get(var, "")
        parts = current.split(sep) if current else []
        parts.insert(0, value)
        env[var] = sep.join(parts)
    elif op in ("append-to-var",):
        if value is None:
            return
        current = env.get(var, "")
        parts = current.split(sep) if current else []
        parts.append(value)
        env[var] = sep.join(parts)
    elif op in ("set-var",):
        if value is None:
            return
        env[var] = value
    elif op in ("remove-from-var",):
        if value is None:
            return
        current = env.get(var, "")
        parts = [p for p in current.split(sep) if p != value]
        env[var] = sep.join(parts)
    elif op in ("unset-var",):
        env.pop(var, None)
    elif op in ("add-dep",):
        pass
    else:
        print(f"  [scbi] unknown env operation: {op}", file=sys.stderr)


def merge_env_dict(target: dict[str, str], source: dict) -> None:
    if not isinstance(source, dict):
        return
    for op, data in source.items():
        if not isinstance(data, list):
            continue
        i = 0
        while i < len(data):
            var = str(data[i])
            value = str(data[i + 1]) if i + 1 < len(data) else None
            apply_env_operation(target, op, var, value)
            i += 2


class HookExecutor:
    def __init__(self, build_env: BuildEnv):
        self.build_env = build_env
        self.env: dict[str, str] = os.environ.copy()

    def run_commands(
        self,
        commands: list[str] | dict,
        cwd: Path | None = None,
        log_file: IO | None = None,
    ) -> int:
        if isinstance(commands, dict):
            return self._run_env_dict(commands)
        if not commands:
            return 0

        if cwd is None:
            cwd = self.build_env.build_dir
            if not cwd.exists():
                cwd = self.build_env.src_dir
                if not cwd.exists():
                    cwd = Path.cwd()

        be = self.build_env
        substituted = [be.substitute(cmd) for cmd in commands]

        for cmd in substituted:
            if log_file:
                log_file.write(f"$ {cmd}\n")
                log_file.flush()

            result = subprocess.run(
                cmd,
                shell=True,
                cwd=str(cwd),
                env=self.env,
                capture_output=False,
                text=True,
            )

            if result.returncode != 0:
                if log_file and result.stderr:
                    log_file.write(result.stderr)
                    log_file.flush()
                return result.returncode

        return 0

    def _run_env_dict(self, env_dict: dict) -> int:
        merged = dict(self.env)
        merge_env_dict(merged, env_dict)

        new_vars = {}
        for op, data in env_dict.items():
            if not isinstance(data, list):
                continue
            i = 0
            while i < len(data):
                var = str(data[i])
                value = str(data[i + 1]) if i + 1 < len(data) else None
                new_vars[var] = (op, value)
                i += 2

        be = self.build_env
        for var, (op, value) in new_vars.items():
            if value is not None:
                value = be.substitute(value)
            apply_env_operation(self.env, op, var, value)

        return 0

    def accumulate_env(self, env_dict: dict) -> None:
        if not isinstance(env_dict, dict):
            return
        be = self.build_env

        for op, data in env_dict.items():
            if not isinstance(data, list):
                continue
            i = 0
            while i < len(data):
                var = str(data[i])
                value = str(data[i + 1]) if i + 1 < len(data) else None
                if value is not None:
                    value = be.substitute(value)
                apply_env_operation(self.env, op, var, value)
                i += 2
