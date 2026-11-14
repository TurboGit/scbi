"""The Python driver runs no Bash: no process is started through a shell
in src/scbi, except in the migration tools (Bash plug-ins and environment
files converted once) and the two cases running user code by the user's
choice (the user's $SHELL of scbi shell, a script without #! line run by
/bin/sh as execvp does)."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "scbi"

#  Migration tools: they read Bash plug-ins and environment files
MIGRATION = {"convert.py", "envconvert.py", "plugin/legacy.py", "plugin/lift.py", "plugin/liftcmd.py"}
#  (file, program) allowed
ALLOWED = {("hooks/cmdlang.py", "/bin/sh")}
SHELLS = {"bash", "sh", "/bin/bash", "/bin/sh", "/usr/bin/bash", "dash", "zsh"}
CALLS = {"run", "Popen", "call", "check_call", "check_output", "system", "popen", "execvp", "execv"}


def _program(call: ast.Call) -> str | None:
    """The program of a subprocess call when it is a literal."""
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, (ast.List, ast.Tuple)) and first.elts and isinstance(first.elts[0], ast.Constant):
        return str(first.elts[0].value)
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value.split()[0] if first.value.split() else ""
    return None


def test_no_shell_in_the_driver():
    problems = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if rel in MIGRATION:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name not in CALLS:
                continue
            if any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value for k in node.keywords):
                problems.append(f"{rel}:{node.lineno}: shell=True")
            prog = _program(node)
            if prog in SHELLS and (rel, prog) not in ALLOWED:
                problems.append(f"{rel}:{node.lineno}: runs {prog}")
            if name in ("system", "popen") and isinstance(node.func, ast.Attribute) and \
                    getattr(node.func.value, "id", "") == "os":
                problems.append(f"{rel}:{node.lineno}: os.{name}")
    assert problems == []


def test_driver_does_not_read_bash_plugins():
    """The registry of the driver refuses Bash plug-ins."""
    text = (SRC / "driver.py").read_text()
    assert "read_legacy=False" in text
