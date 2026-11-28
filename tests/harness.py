"""Harness of the regression testsuite (tests/drivers/testNNN.py).

Each driver is a pytest test using the fixture ``t`` (a :class:`Driver`):
it runs in its own copy of the test root (scripts.d, .root/repos...), so
drivers are independent and can run in parallel (pytest-xdist).

    def test(t):
        t.runs("./scbi -s -c test1")
        t.clean_diff('''\\
    xxxx/xx/xx xx:xx:xx : Building test1 [default] (master)
    ...
    ''')

- ``t.runs(cmd)`` / ``t.nruns(cmd)``: run a command line (status 0 /
  not 0 expected), its output (standard output and error) becomes the
  *output* the next checks look at. ``./scbi ...`` runs the driver in the
  test process (``SCBI_TEST_SUBPROCESS=1``: in a process), other commands
  with bash;
- checks on the output: ``diff``, ``clean_diff`` (time stamps, the
  current directory... masked), ``grep``, ``ngrep``; on values: ``ok``,
  ``nok`` (as the ``test`` command), ``is_``, ``isnt``;
- output filters: ``trim_output``, ``clean_output``, ``sort_output``,
  ``no_output_version``, ``sort_output_n_first_lines``,
  ``sort_output_but_n_lines``, ``sort_output_but_first_line``;
- shell state: ``t.sh(code)`` runs bash code (the output is available as
  the file ``$TEST_OUTPUT``, changes to it are kept), ``t.set``,
  ``t.unset``, ``t.cd``, ``t.value``.

A failing check does not stop the driver: all failures are reported at
the end, with their line in the driver.
"""

from __future__ import annotations

import difflib
import inspect
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"
SRC = REPO / "src"

#  characters needing bash to expand a command line
_SHELL_CHARS = re.compile(r"[$`*?\[\]'\"\\{}~]")
_SHELL_OPS = re.compile(r"[|&;<>()]")


def _git_files(path: Path, new: bool = False) -> list[Path] | None:
    """The tracked files under ``path``, and the new (not ignored) ones
    with ``new`` (None when not in a git tree)."""
    cmd = ["git", "ls-files", "-z", "--cached"] + (["--others", "--exclude-standard"] if new else [])
    try:
        proc = subprocess.run([*cmd, "--", str(path)], cwd=REPO, capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    files = [REPO / f for f in proc.stdout.decode().split("\0") if f]
    #  a nested repository is listed as a directory: not a file to copy
    files = [f for f in files if f.is_file() or f.is_symlink()]
    return files or None


def _copy_tree(src: Path, dst: Path, new: bool = False) -> None:
    """Copy the tracked files of ``src`` (and the new ones with ``new``;
    everything when not in git)."""
    files = _git_files(src, new)
    if files is None:
        if src.is_dir():
            shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
        return
    for f in files:
        target = dst / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target, follow_symlinks=False)


def make_root(root: Path) -> None:
    """The test root: the layout of tests/ the drivers expect."""
    #  the test plug-ins being written are used before being committed
    _copy_tree(TESTS / "scripts.d", root / "scripts.d", new=True)
    for pkgs in (REPO / "scripts.d").glob(".pkgs-*"):
        shutil.copy2(pkgs, root / "scripts.d" / pkgs.name)
    for d in ("repos", ".archives", ".store"):
        _copy_tree(TESTS / ".root" / d, root / ".root" / d)
    patches = root / ".root" / ".patches"
    patches.mkdir(parents=True, exist_ok=True)
    for p in (root / ".root" / "repos").glob("*.patch"):
        shutil.copy2(p, patches / p.name)
    (root / ".root" / "builds" / "install").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    (root / "fixtures").symlink_to(TESTS / "fixtures")
    wrapper = root / "scbi"
    wrapper.write_text("#!/bin/bash\n"
                       f'SCBI_ARGV0="$0" PYTHONPATH={SRC}${{PYTHONPATH:+:$PYTHONPATH}} exec python3 -m scbi "$@"\n')
    wrapper.chmod(0o755)


def base_env(root: Path) -> dict[str, str]:
    """The environment of the drivers (the settings of the former
    tests/run)."""
    keep = ("HOME", "USER", "LOGNAME", "SHELL", "TERM", "TMPDIR")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    sroot = str(root / ".root")
    env.update({
        "LANG": "C", "CDPATH": "", "PATH": f"{root}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "ROOTDIR": str(root), "TESTREPOS": f"{sroot}/repos",
        "SCBI_TESTSUITE": "yes", "SCBI_ROOT": sroot, "SCBI_ARCHIVES": f"{sroot}/.archives",
        "SCBI_PATCH": f"{sroot}/.patches", "SCBI_GIT_REPO": f"{sroot}/git", "SCBI_SVN_REPO": "",
        "SCBI_HG_REPO": "", "TODAY": "", "SCBI_EMAIL_NOTIFICATION": "no", "SCBI_CACHE_DIR": "no", "SCBI_BINARY_STORE": "no",
    })
    return env


# ------------------------------------------------------------- filters


def _drop_last_empty(lines: list[str]) -> list[str]:
    #  sed '${/^$/d;}'
    return lines[:-1] if lines and lines[-1] == "" else lines


def _split(text: str) -> list[str]:
    lines = text.split("\n")
    return lines[:-1] if text.endswith("\n") else lines


def _join(lines: list[str]) -> str:
    return "".join(ln + "\n" for ln in lines)


_TS = re.compile(r"^[0-9/]* [0-9:]* :")


class CheckFailed(AssertionError):
    pass


class Driver:
    """The state of a driver: its root, environment, directory and the
    output of the last command."""

    def __init__(self, root: Path, test_file: str):
        self.root = root
        self.test_file = test_file
        self.env = base_env(root)
        self.cwd = str(root)
        self.output = ""
        self.status = 0
        self.checks = 0
        self.failures: list[str] = []
        self.subprocess = os.environ.get("SCBI_TEST_SUBPROCESS") == "1"

    # -------------------------------------------------------- reports

    def _line(self) -> int:
        for frame in inspect.stack():
            if frame.filename == self.test_file:
                return frame.lineno
        return 0

    def _check(self, ok: bool, what: str, detail: str = "") -> bool:
        self.checks += 1
        if not ok:
            msg = f"{Path(self.test_file).name}:{self._line()}: {what}"
            if detail:
                msg += "\n" + detail.rstrip("\n")
            self.failures.append(msg)
        return ok

    def report(self) -> str:
        return f"{len(self.failures)} of {self.checks} checks failed\n\n" + "\n\n".join(self.failures)

    # ---------------------------------------------------------- shell

    def _bash(self, code: str, capture: bool = True, **kw) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", "-c", code], cwd=self.cwd, env=self.env, capture_output=capture, **kw)

    def value(self, word: str) -> str:
        """A Bash word expanded (variables, $(...), quotes...)."""
        if not _SHELL_CHARS.search(word):
            return word
        proc = self._bash(f"printf '%s' {word}")
        return proc.stdout.decode(errors="surrogateescape")

    def text(self, text: str) -> str:
        """A here-document with an unquoted delimiter: variables, $(...)
        and backslash escapes expanded by Bash."""
        delim = "SCBI_TEST_EOF"
        proc = self._bash(f"cat <<{delim}\n{text}{delim}\n")
        return proc.stdout.decode(errors="surrogateescape")

    def words(self, line: str) -> list[str]:
        """A command line split into expanded words, as Bash does."""
        if not _SHELL_CHARS.search(line):
            return line.split()
        proc = self._bash(f"printf '%s\\0' {line}")
        return [w for w in proc.stdout.decode(errors="surrogateescape").split("\0")[:-1]]

    def set(self, name: str, word: str = "", export: bool = True) -> None:
        """``NAME=word`` (all variables are given to the commands)."""
        self.env[name] = self.value(word)

    def unset(self, *names: str) -> None:
        for n in names:
            self.env.pop(n, None)

    def cd(self, path: str) -> None:
        self.cwd = os.path.normpath(os.path.join(self.cwd, self.value(path)))

    def sh(self, code: str) -> int:
        """Run Bash code (setup commands) as in the shell of the former
        drivers: the variables it sets (all exported, ``set -a``), the
        functions it exports and its current directory are kept for the
        following commands. ``$TEST_OUTPUT`` is the file of the output
        (the changes made to it are kept)."""
        with tempfile.NamedTemporaryFile("w", delete=False, dir=self.root, prefix=".output.") as f:
            f.write(self.output)
            path = f.name
        mark = "__SCBI_TEST_STATE__"
        script = (f"set -a\n{code}\n__status=$?\nprintf '\\0{mark}\\0%s\\0' \"$PWD\"\n"
                  "env -0\nexit $__status\n")
        try:
            env = dict(self.env, TEST_OUTPUT=path)
            proc = subprocess.run(["bash", "-c", script], cwd=self.cwd, env=env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.output = Path(path).read_text(errors="surrogateescape")
        finally:
            os.unlink(path)
        data = proc.stdout.decode(errors="surrogateescape")
        if f"\0{mark}\0" in data:
            state = data.split(f"\0{mark}\0", 1)[1].split("\0")
            self.cwd = state[0]
            env = {}
            for item in state[1:]:
                name, sep, value = item.partition("=")
                if sep and name not in ("TEST_OUTPUT", "PWD", "OLDPWD", "SHLVL", "_", "__status"):
                    env[name] = value
            self.env = env
        return proc.returncode

    # -------------------------------------------------------- running

    def _run(self, cmd: str) -> tuple[int, str]:
        first = cmd.split(None, 1)[0] if cmd.split() else ""
        if first in ("./scbi", "scbi") and not self.subprocess and not _SHELL_OPS.search(cmd):
            return self._scbi(first, self.words(cmd)[1:])
        proc = self._bash(cmd, capture=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          stdin=subprocess.DEVNULL)
        return proc.returncode, proc.stdout.decode(errors="surrogateescape")

    def _scbi(self, argv0: str, argv: list[str]) -> tuple[int, str]:
        """The driver in this process: environment, directory and standard
        streams of the process set for the call and restored after."""
        from scbi import cli

        saved_env, saved_cwd = dict(os.environ), os.getcwd()
        saved_streams = (sys.stdout, sys.stderr, sys.argv)
        sys.stdout.flush()
        sys.stderr.flush()
        fds = (os.dup(1), os.dup(2))
        with tempfile.TemporaryFile() as out:
            try:
                os.dup2(out.fileno(), 1)
                os.dup2(out.fileno(), 2)
                sys.stdout = io.TextIOWrapper(io.FileIO(1, "w", closefd=False), encoding="utf-8",
                                              errors="surrogateescape", write_through=True)
                sys.stderr = io.TextIOWrapper(io.FileIO(2, "w", closefd=False), encoding="utf-8",
                                              errors="surrogateescape", write_through=True)
                sys.argv = [argv0, *argv]
                os.environ.clear()
                os.environ.update(self.env)
                os.environ["SCBI_ARGV0"] = argv0
                os.chdir(self.cwd)
                try:
                    status = cli.main(argv)
                except SystemExit as e:
                    status = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
            finally:
                try:
                    sys.stdout.flush()
                    sys.stderr.flush()
                except (OSError, ValueError):
                    pass
                os.dup2(fds[0], 1)
                os.dup2(fds[1], 2)
                os.close(fds[0])
                os.close(fds[1])
                sys.stdout, sys.stderr, sys.argv = saved_streams
                os.environ.clear()
                os.environ.update(saved_env)
                os.chdir(saved_cwd)
            out.seek(0)
            text = out.read().decode(errors="surrogateescape")
        return status or 0, text

    def runs(self, cmd: str) -> bool:
        """RUNS: the command succeeds."""
        self.status, self.output = self._run(cmd)
        return self._check(self.status == 0, f"RUNS {cmd}: status {self.status}", self.output[-3000:])

    def nruns(self, cmd: str) -> bool:
        """NRUNS: the command fails."""
        self.status, self.output = self._run(cmd)
        return self._check(self.status != 0, f"NRUNS {cmd}: status 0", self.output[-3000:])

    # --------------------------------------------------------- checks

    def diff(self, expected: str) -> bool:
        """DIFF: the output is ``expected``."""
        if self.output == expected:
            return self._check(True, "")
        d = "".join(difflib.unified_diff(expected.splitlines(True), self.output.splitlines(True),
                                         "expected", "output"))
        return self._check(False, "DIFF", d)

    def clean_diff(self, expected: str) -> bool:
        """CLEAN-DIFF: DIFF after masking time stamps, directories,
        hashes... in the output and time stamps in ``expected``."""
        self.clean_output()
        self.trim_output()
        exp = _drop_last_empty([_TS.sub("xxxx/xx/xx xx:xx:xx :", ln) for ln in _split(expected)])
        self.output = _join([ln for ln in _split(self.output) if not re.search(r"_[_]*TRACE:", ln)])
        return self.diff(_join(exp))

    def _grep(self, args: tuple[str, ...]) -> int:
        """``grep -q ARGS <output>`` (as osht: files given in ARGS are
        searched too), in the directory of the driver."""
        with tempfile.NamedTemporaryFile("wb", dir=self.root, prefix=".output.") as f:
            f.write(self.output.encode(errors="surrogateescape"))
            f.flush()
            return subprocess.run(["grep", "-q", *args, f.name], cwd=self.cwd, env=self.env).returncode

    def grep(self, *args: str) -> bool:
        """GREP: ``grep -q args`` matches (the output, and the files of
        args)."""
        return self._check(self._grep(args) == 0, f"GREP {' '.join(args)}", self.output[-3000:])

    def ngrep(self, *args: str) -> bool:
        """NGREP: ``grep -q args`` does not match."""
        return self._check(self._grep(args) != 0, f"NGREP {' '.join(args)}", self.output[-3000:])

    def ok(self, test: str) -> bool:
        """OK: ``test <test>`` (Bash words) is true."""
        return self._check(self._bash(f"test {test}").returncode == 0, f"OK {test}")

    def nok(self, test: str) -> bool:
        """NOK: ``test ! <test>`` is true."""
        return self._check(self._bash(f"test ! {test}").returncode == 0, f"NOK {test}")

    def is_(self, left: str, op: str, right: str) -> bool:
        """IS: the values compared (osht semantics: == != =~, else the
        operator of test)."""
        ok = self._compare(left, op, right)
        return self._check(ok, f"IS {left!r} {op} {right!r}")

    def isnt(self, left: str, op: str, right: str) -> bool:
        ok = not self._compare(left, op, right)
        return self._check(ok, f"ISNT {left!r} {op} {right!r}")

    def _compare(self, left: str, op: str, right: str) -> bool:
        if op in ("=", "=="):
            return self._bash(f"[[ {left} == {right} ]]").returncode == 0
        if op == "!=":
            return self._bash(f"[[ {left} != {right} ]]").returncode == 0
        if op == "=~":
            return self._bash(f"[[ {left} =~ {right} ]]").returncode == 0
        return self._bash(f'[ {left} {op} {right} ]').returncode == 0

    # -------------------------------------------------------- filters

    def clean_output(self) -> None:
        """clean-up-osht-output: time stamps, the current directory,
        hashes, versions of squid, the reproduce lines."""
        home = self.env.get("HOME", "")
        pwd2 = self.cwd.replace(home, "~") if home else self.cwd
        lines = []
        for ln in _split(self.output):
            ln = _TS.sub("xxxx/xx/xx xx:xx:xx :", ln)
            ln = re.sub(r"squid-cgi [0-9.]*", "squid-cgi v.vv", ln)
            ln = re.sub(r"\(....................\)", "(xxxxxxxxxxxxxxxxxxxx)", ln)
            ln = ln.replace(self.cwd, "<pwd>").replace(pwd2, "<pwd>")
            ln = re.sub(r"\(FAILED\) (bash|scbi replay) (.*\.cmd)$", r"(FAILED) <reproduce> \2", ln)
            ln = re.sub(r"\(FAILED\) use (bash -x|--trace) option for debug$",
                        "(FAILED) use <debug> option for debug", ln)
            lines.append(ln)
        self.output = _join(_drop_last_empty(lines))

    def trim_output(self) -> None:
        """trim-osht-output: trailing blanks removed."""
        self.output = _join([re.sub(r" +$", "", ln) for ln in _split(self.output)])

    def sort_output(self) -> None:
        self.output = _join(sorted(_split(self.output), key=_sort_key))

    def no_output_version(self) -> None:
        """no-osht-output-version: versions (:1.2.3) masked as :x.x."""
        self.output = _join([re.sub(r":[0-9]*\.[0-9]*\.?[0-9]*", ":x.x", ln) for ln in _split(self.output)])

    def sort_output_n_first_lines(self, n: int) -> None:
        self.clean_output()
        lines = _split(self.output)
        self.output = _join(sorted(lines[:n], key=_sort_key) + lines[n:])

    def sort_output_but_n_lines(self, n: int) -> None:
        """sort-osht-output-but-n-lines: the n first lines kept, the n-th
        line removed from the rest (as the Bash version), the rest sorted."""
        lines = _split(self.output)
        rest = lines[: n - 1] + lines[n:]
        self.output = _join(lines[:n] + sorted(rest, key=_sort_key))

    def sort_output_but_first_line(self) -> None:
        self.sort_output_but_n_lines(1)


def _sort_key(line: str):
    #  sort with LANG=C: byte order
    return line.encode(errors="surrogateescape")
