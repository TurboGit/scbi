"""The Python driver compared with the Bash driver (end-to-end) and its
plan rewriting compared with the Bash runtime."""

import re

import pytest

from corpus import plan_files
from e2e import pair
from oracle import REPO_ROOT
from scbi.bashenv import ShellVars
from scbi.driver import Driver
from scbi.plan import PlanLoader, PlanState

CLI_CASES = [
    ["--help"], ["-h", "lib1"], ["-v"], ["--version"], [],
    ["--unknown-options"], ["-P"], ["--ukw", "lib1"], ["--plugins=/nope", "x"],
    ["--env=nothere", "lib1"], ["-e", "nothere", "lib1"], ["--plan=nothere", "lib1"],
    ["--stat"], ["--stat:short"], ["--stat", "--plan=meta"], ["--stat:short", "--plan=group"],
    ["--stat:short", "--plan=base/x"], ["-q", "--stat:short", "--plan=set"],
    ["--color:dark", "--stat:short"], ["--color:light", "--stat:short"], ["--ini=x"],
    ["--stat:short", "--target=arm-linux-gnueabi"],
]


@pytest.fixture(scope="module")
def sandboxes(tmp_path_factory):
    return pair(tmp_path_factory.mktemp("e2e"))


@pytest.mark.oracle
@pytest.mark.parametrize("args", CLI_CASES, ids=lambda a: " ".join(a) or "<none>")
def test_cli_same_as_bash(sandboxes, args):
    bash, python = sandboxes
    rb, rp = bash.run(args), python.run(args)
    assert (rp.returncode, rp.stdout, rp.stderr) == (rb.returncode, rb.stdout, rb.stderr)


@pytest.mark.oracle
def test_ini_sections_same_as_bash(tmp_path):
    bash, python = pair(tmp_path)
    ini = "stat = short\n[sc]\n   quiet = yes\n   plan = group\n[common]\n   stat = yes\n"
    for sb in (bash, python):
        (sb.root / "ini").write_text(ini)
    for args in (["--ini=sc"], [], ["--ini=other"]):
        env = {"SCBI_INI_FILE": "ini"}
        rb, rp = bash.run(args, env), python.run(args, env)
        assert (rp.returncode, rp.stdout, rp.stderr) == (rb.returncode, rb.stdout, rb.stderr), args


# ------------------------------------------------------ meta propagation

PLAN_DUMP = r"""
SCBI_PLUGINS="$1"
SCBI_OS_DISCRIMINANTS=()
SCBI_PREFIX=/p
load-module-plan "$2" > /dev/null 2>&1 || exit 1
rewrite-module-plan > /dev/null 2>&1
for k in "${!SCBI_MODVER[@]}"; do printf 'M\x1f%s\x1f%s\n' "$k" "${SCBI_MODVER[$k]}"; done
for k in "${!SCBI_PLAN_HIST[@]}"; do printf 'H\x1f%s\x1f%s\n' "$k" "${SCBI_PLAN_HIST[$k]}"; done
"""


def meta_plans():
    plans = []
    for p in plan_files():
        if p.parent.parent.name != "tests":
            continue
        text = p.read_text()
        if re.search(r"auto", text):
            continue
        plans.append(p)
    return plans


@pytest.mark.oracle
def test_meta_propagation_oracle(oracle, tmp_path):
    plans = meta_plans()
    plugins = REPO_ROOT / "tests" / "scripts.d"
    outputs = oracle.batch(PLAN_DUMP, [(str(plugins), p.name[len(".plan-"):]) for p in plans])
    checked = 0
    for plan_file, out in zip(plans, outputs):
        name = plan_file.name[len(".plan-"):]
        state = PlanState()
        try:
            PlanLoader(state, plugins, [], cwd=tmp_path).load(name)
        except Exception:
            continue
        d = Driver("scbi", {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
        d.init_globals()
        d.set("SCBI_PLUGINS", str(plugins))
        d.set("SCBI_PREFIX", "/p")
        d.set("SCBI_ROOT", str(tmp_path / "root"))
        d.load_runtime()
        d.discriminants = []
        d.plan = state
        d.registry.module_alias = state.module_alias
        from scbi.metaplan import propagate_meta_versions

        propagate_meta_versions(d)
        bash = {"M": {}, "H": {}}
        for line in out.splitlines():
            kind, k, v = line.split("\x1f")
            bash[kind][k] = v
        assert state.modver == bash["M"], name
        assert state.plan_hist == bash["H"], name
        d.clean_up()
        checked += 1
    assert checked > 20
