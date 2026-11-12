"""Differential oracle: run the reference Bash implementation of SCBI.

The Bash driver and runtime (``scbi``, ``scripts.d/[0-9]*``) are the
specification of the Python port. This module builds a Bash prelude that
defines every function of the driver (without running its main code) and
sources the runtime files, then lets tests call any Bash function and
retrieve its output or resulting variables.

Typical use (through the ``oracle`` fixture of conftest.py)::

    out = oracle.call("get-module-ref R lcms2/fast:v2.0; printf '%s\\n' \"${R[@]}\"")
    values = oracle.array("get-module-ref R lcms2/fast", "R")
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_FUNC_START = re.compile(r"^function\s+[A-Za-z0-9_:.@+-]+\s*\(\)")


def extract_functions(path: Path) -> str:
    """Return only the top-level function definitions of a Bash script.

    Functions are expected in the SCBI style: ``function name()`` at column 0
    and the closing ``}`` at column 0.
    """
    out: list[str] = []
    inside = False
    for line in path.read_text().splitlines():
        if not inside and _FUNC_START.match(line):
            inside = True
        if inside:
            out.append(line)
            if line.startswith("}"):
                inside = False
                out.append("")
    return "\n".join(out) + "\n"


def _bash_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


class BashError(RuntimeError):
    def __init__(self, script: str, proc: subprocess.CompletedProcess):
        super().__init__(
            f"bash exited with {proc.returncode}\n--- script ---\n{script}"
            f"\n--- stderr ---\n{proc.stderr}"
        )
        self.proc = proc


class BashOracle:
    """Run snippets of Bash with the SCBI driver functions and runtime loaded."""

    RUNTIME_GLOB = "[0-9]*"

    def __init__(
        self,
        workdir: Path,
        repo_root: Path = REPO_ROOT,
        host: str = "x86_64-linux-gnu",
        target: str | None = None,
        plugins_dir: Path | None = None,
    ):
        self.repo_root = repo_root
        self.workdir = workdir
        self.host = host
        self.target = target or host
        self.plugins_dir = plugins_dir or repo_root / "scripts.d"
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.prelude = self.workdir / "oracle-prelude.sh"
        self._write_prelude()

    def _write_prelude(self) -> None:
        runtime = sorted((self.repo_root / "scripts.d").glob(self.RUNTIME_GLOB))
        parts = [
            "shopt -s extglob",
            "declare -gA SCBI_INI_DB",
            "SCBI_VERSION=oracle",
            f"SCBI_BINARY={self.repo_root / 'scbi'}",
            f"SCBI_HOST={self.host}",
            f"SCBI_TARGET={self.target}",
            "SCBI_IS_WINDOWS=no",
            f"SCBI_PLUGINS={self.plugins_dir}",
            "SCBI_DLOG=on-failure",
            "SCBI_JOBS=2",
            "SCBI_HALF_JOBS=1",
            "SCBI_MODULES=()",
            "",
            "#  Driver functions (main code not executed)",
            extract_functions(self.repo_root / "scbi"),
            "#  Runtime",
        ]
        parts += [f"source {f}" for f in runtime]
        parts += [
            "",
            "#  Logging setup (normally done by the driver main code)",
            "DO_QUIET=no",
            'mkdir -p "$SCBI_LOGS/$TODAY"',
            f"SCBI_LINE_SEP={self.workdir / 'line-sep'}",
        ]
        self.prelude.write_text("\n".join(parts) + "\n")

    def env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        home = self.workdir / "home"
        home.mkdir(exist_ok=True)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(home),
            "LANG": "C",
            "LC_ALL": "C",
            "SCBI_ROOT": str(self.workdir / "root"),
        }
        if extra:
            env.update(extra)
        return env

    def run(
        self, script: str, env: dict[str, str] | None = None, check: bool = True
    ) -> subprocess.CompletedProcess:
        full = f"source {self.prelude} 2>/dev/null\n{script}\n"
        proc = subprocess.run(
            ["bash", "-s"],
            input=full,
            cwd=self.workdir,
            env=self.env(env),
            capture_output=True,
            text=True,
        )
        if check and proc.returncode != 0:
            raise BashError(script, proc)
        return proc

    def call(self, script: str, env: dict[str, str] | None = None) -> str:
        """Run ``script`` and return its standard output."""
        return self.run(script, env).stdout

    def array(
        self, script: str, name: str, env: dict[str, str] | None = None
    ) -> list[str]:
        """Run ``script`` then return the content of indexed array ``name``."""
        out = self.call(
            f'{script}\n(( ${{#{name}[@]}} )) && printf "%s\\0" "${{{name}[@]}}"\ntrue',
            env,
        )
        if out == "":
            return []
        items = out.split("\0")
        assert items[-1] == ""
        return items[:-1]

    def assoc(
        self, script: str, name: str, env: dict[str, str] | None = None
    ) -> dict[str, str]:
        """Run ``script`` then return the content of associative array ``name``."""
        out = self.call(
            f'{script}\nfor __k in "${{!{name}[@]}}"; do '
            f'printf "%s\\0%s\\0" "$__k" "${{{name}[$__k]}}"; done',
            env,
        )
        items = out.split("\0")[:-1]
        return dict(zip(items[0::2], items[1::2]))

    def batch(
        self,
        template: str,
        inputs: list[tuple[str, ...]],
        env: dict[str, str] | None = None,
    ) -> list[str]:
        """Run ``template`` once per input tuple in a single Bash process.

        ``template`` is Bash code using ``"$1" "$2" ...`` for the input
        fields; its standard output for each input is returned. Each run is
        done in a sub-shell so that state does not leak between inputs.
        """
        lines = []
        for fields in inputs:
            quoted = " ".join(_bash_quote(f) for f in fields)
            lines.append(f"( set -- {quoted}\n{template}\n ) ; printf '\\0'")
        out = self.call("\n".join(lines), env)
        results = out.split("\0")
        assert results[-1] == "" and len(results) == len(inputs) + 1, results[-3:]
        return results[:-1]

    def var(self, script: str, name: str, env: dict[str, str] | None = None) -> str:
        """Run ``script`` then return the value of scalar variable ``name``."""
        return self.call(f'{script}\nprintf "%s" "${{{name}}}"', env)
