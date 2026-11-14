"""The step wrapper (steps/wrapper.py) compared with the Bash
module-variant-wrapper / module-wrapper: messages on the console, global
and local logs, for steps which succeed, fail, are cached or nop, with
SCBI_DLOG no / yes / on-failure, in and out of tree, and a plug-in
inheriting another one. The Python driver runs YAML plug-ins: the way to
reproduce a step (scbi replay of a replay file instead of a Bash script),
the trace lines and the copies of the plug-in files in the logs
directory differ by design and are not compared."""

import re
from pathlib import Path

import pytest

from probe import probe_pair
from test_sources_handle import mask as _mask


def mask(text: str, root: Path) -> str:
    #  error locations: Bash file and line of the hook (hook shells: their
    #  prelude, a known difference)
    #  error locations: Bash file and line, or plug-in, hook and line
    text = re.sub(r"(?m)^\S+: (\S+: )?line \d+: ", "<loc>: ", _mask(text, root))
    #  how to reproduce a failing step (as tests/run masks it)
    text = re.sub(r"\(FAILED\) (bash|scbi replay) (.*\.cmd)$", r"(FAILED) <reproduce> \2", text, flags=re.M)
    text = re.sub(r"\(FAILED\) use (bash -x|--trace) option for debug$", "(FAILED) use <debug> option for debug",
                  text, flags=re.M)
    #  trace lines
    return re.sub(r"(?m)^_+TRACE: .*\n", "", text)

#  (step, modref, oot, extra environment)
CASES = [
    ("config", "failsteps", "true", {}),
    ("config", "failsteps/conferr", "true", {}),
    ("build", "failsteps/builderr", "false", {"SCBI_DLOG": "on-failure"}),
    ("install", "failsteps/installerr", "true", {"SCBI_DLOG": "yes"}),
    ("install", "failsteps", "true", {"SCBI_DLOG": "yes"}),
    ("setup", "failsteps", "true", {}),                    # no hook
    ("build", "failsteps", "true", {"BUILD_SCBI_TARGET": "arm"}),
    ("config", "libdeps", "true", {}),                     # inherit-plugin
    ("build", "libdeps", "false", {}),
    ("tests", "libdeps", "true", {"SCBI_TESTS_OPTIONS": "-v"}),
]


def files(root: Path) -> dict[str, str]:
    """Logs (time-stamps and trace lines masked)."""
    out = {}
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root))
        if not p.name.endswith(".log"):
            continue
        if p.is_file() and (rel.startswith("logs/") or "/logs/" in rel) and "report" not in rel:
            text = mask(p.read_text(errors="replace"), root)
            out[re.sub(r"logs/\d+-\d+-\d+", "logs/<today>", rel)] = text
    return out


@pytest.mark.oracle
@pytest.mark.parametrize("step, modref, oot, extra", CASES, ids=[f"{c[1]}-{c[0]}" for c in CASES])
def test_wrapper_same_as_bash(tmp_path, step, modref, oot, extra):
    bash, python = probe_pair(tmp_path / "sb")
    args = ["probe", "wrapper", step, modref, oot]
    rb, rp = bash.run(args, extra), python.run(args, extra)
    assert (rp.returncode, mask(rp.stdout, python.root), mask(rp.stderr, python.root)) == \
        (rb.returncode, mask(rb.stdout, bash.root), mask(rb.stderr, bash.root))
    assert files(python.root) == files(bash.root)
