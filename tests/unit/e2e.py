"""End-to-end comparison of the Bash and Python drivers.

A sandbox reproduces the setup done by tests/run (test plug-ins, runtime
files patched the same way, driver and tools, isolated HOME); the same
command is run with each driver in its own sandbox and the results
(output, status, files) can be compared, time-stamps masked.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from oracle import REPO_ROOT

TOOLS = ("lint", "source-archive", "store", "show", "shell", "format")

_TS = re.compile(r"\d{4}/\d\d/\d\d \d\d:\d\d:\d\d")
_MD5 = re.compile(r"\(([0-9a-f]{20})\)")


def mask(text: str, sandbox: Path) -> str:
    """Remove what differs between runs (time-stamps, sandbox path)."""
    text = _TS.sub("xxxx/xx/xx xx:xx:xx", text)
    text = _MD5.sub("(xxxxxxxxxxxxxxxxxxxx)", text)
    return text.replace(str(sandbox), "<pwd>")


@dataclass
class Run:
    returncode: int
    stdout: str
    stderr: str


class Sandbox:
    def __init__(self, root: Path, impl: str):
        self.root = root
        self.impl = impl
        root.mkdir(parents=True, exist_ok=True)
        plugins = root / "scripts.d"
        shutil.copytree(REPO_ROOT / "tests" / "scripts.d", plugins, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("*~", "*.yaml", "[0-9]_*", "_os_*", ".pkgs-*", ".store"))
        #  test-specific runtime files are tracked in tests/scripts.d
        for f in ("1_setup", "1_shell"):
            src = REPO_ROOT / "tests" / "scripts.d" / f
            if src.exists():
                shutil.copy(src, plugins / f)
        src = REPO_ROOT / "scripts.d"
        for pattern in ("0_runtime", "_os_*", "[2-9]*", ".pkgs-*"):
            for f in src.glob(pattern):
                if f.is_file() and not f.name.endswith("~"):
                    shutil.copy(f, plugins / f.name)
        modgen = plugins / "7_modgen"
        text = modgen.read_text()
        text = text.replace("$OPT --exclude", "$OPT -c --exclude").replace("dlog", "ilog")
        modgen.write_text(text)

        for t in TOOLS:
            shutil.copy(REPO_ROOT / f"scbi-{t}", root / f"scbi-{t}")
        if impl == "bash":
            driver = (REPO_ROOT / "scbi").read_text()
            driver = re.sub(r"(?m)^(.*ini-load-file \$HOME/.scbi)", r"#\1", driver)
            (root / "scbi").write_text(driver)
        else:
            (root / "scbi").write_text(
                "#!/bin/bash\n"
                f"SCBI_ARGV0=\"$0\" PYTHONPATH={REPO_ROOT / 'src'}${{PYTHONPATH:+:$PYTHONPATH}} "
                "exec python3 -m scbi \"$@\"\n"
            )
            #  the Python driver reads YAML plug-ins only
            to_yaml(self)
        (root / "scbi").chmod(0o755)
        for p in root.glob("scbi-*"):
            p.chmod(0o755)
        (root / "home").mkdir(exist_ok=True)
        (root / "logs").mkdir(exist_ok=True)
        (root / ".root" / "builds" / "install").mkdir(parents=True, exist_ok=True)

    def env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        env = {
            "PATH": f"{self.root}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.root / "home"),
            "LANG": "C",
            "CDPATH": "",
            "SCBI_EMAIL_NOTIFICATION": "no",
            "SCBI_CACHE_DIR": "no",
            "TERM": "dumb",
        }
        if self.impl == "python":
            #  as tests/run: the settings of the test runtime file 1_setup
            root = self.root / ".root"
            env.update(SCBI_TESTSUITE="yes", SCBI_ROOT=str(root), SCBI_ARCHIVES=f"{root}/.archives",
                       SCBI_PATCH=f"{root}/.patches", SCBI_GIT_REPO=f"{root}/git", SCBI_SVN_REPO="", SCBI_HG_REPO="", TODAY="")
        if extra:
            env.update(extra)
        return env

    def run(self, args: list[str], env: dict[str, str] | None = None, stdin: str = "") -> Run:
        proc = subprocess.run(
            ["./scbi", *args], cwd=self.root, env=self.env(env), input=stdin,
            capture_output=True, text=True,
        )
        return Run(proc.returncode, mask(proc.stdout, self.root), mask(proc.stderr, self.root))


def to_yaml(sandbox: "Sandbox") -> None:
    """Convert the plug-ins of a sandbox to YAML, as tests/run does for the
    Python driver (the plug-ins that do not convert stay Bash)."""
    convert_dir(sandbox.root / "scripts.d")


def convert_file(plugin: Path) -> None:
    """Write the YAML version of a Bash plug-in next to it."""
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    subprocess.run([sys.executable, "-m", "scbi.convert", "--output-dir", str(plugin.parent), str(plugin)],
                   env=env, check=True, stdout=subprocess.DEVNULL)


def convert_dir(plugins: Path) -> None:
    """Convert the plug-ins of a directory to YAML (in place)."""
    sources = [str(f) for f in sorted(plugins.iterdir())
               if f.is_file() and not f.name.startswith(("_", ".")) and not f.name[0].isdigit()
               and not f.name.endswith(("~", ".yaml"))]
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    for args in (["--output-dir", str(plugins), *sources], ["--closure", str(plugins)]):
        subprocess.run([sys.executable, "-m", "scbi.convert", *args], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def pair(tmp_path: Path) -> tuple[Sandbox, Sandbox]:
    return Sandbox(tmp_path / "bash", "bash"), Sandbox(tmp_path / "python", "python")
