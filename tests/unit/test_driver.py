"""The Python driver compared with the Bash driver (end-to-end) and its
plan rewriting compared with the Bash runtime."""

import re

import pytest

from corpus import plan_files
from e2e import pair
from known_diffs import mask_bash_error_location
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
    ["--stat:short", "--target=arm-linux-gnueabi"], ["--stat:full"],
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


# ------------------------------------------------------------- sub-commands

STORE_SEQUENCE = [
    ["store", "k1", "v1"], ["store", "k2", "a  b"], ["store", "k1"], ["store", "k2"],
    ["store", "-l"], ["store", "--list:full"], ["store", "-k", "k1"], ["store", "nothere"],
    ["store", "-d", "k1"], ["store", "--list:full"], ["store", "-d"], ["store", "--bogus"],
    ["store"], ["-h", "store"], ["store", "k3", "back\\slash"], ["store", "--list:full"],
]


@pytest.mark.oracle
def test_store_same_as_bash(tmp_path):
    bash, python = pair(tmp_path)
    for args in STORE_SEQUENCE:
        rb, rp = bash.run(args), python.run(args)
        assert (rp.returncode, rp.stdout, rp.stderr) == (rb.returncode, rb.stdout, rb.stderr), args
    sb = (bash.root / "scripts.d" / ".store").read_text()
    sp = (python.root / "scripts.d" / ".store").read_text()
    assert sp == sb


SHOW_CASES = [
    ["show", "--plan=autobar", "--build-plan", "lib1"],
    ["show", "--plan=ondeps", "--build-plan", "ondeps"],
    ["show", "--target=i686-pc-mingw32", "--plan=cross", "--build-plan", "lib1"],
    ["show", "--plan=set", "--build-plan", "lib1"],
    ["show", "--plan=plgv4", "--build-plan:history", "lib1"],
    ["show", "--plan=plgv9", "--build-plan:history=plg", "lib1"],
    ["show", "--plan=modver/meta", "--build-plan"],
    ["show", "--plan=meta-meta", "--build-plan", "meta-meta/both:v2"],
    ["show", "--plan=group", "--build-plan=mod[AB],modE"],
    ["show", "--plan=set", "--module-ref", "module1", "module3"],
    ["show", "--plan=set", "--module-ref:version", "module1"],
    ["show", "--plan=set", "--module-ref:variant", "module3"],
    ["show", "--plan=dev", "--module-ref:full", "lib1", "lib2"],
    ["show"], ["-h", "show"], ["show", "--bogus"],
    ["show", "--depends", "dmain"],
    ["show", "--externals:only", "dmain"],
    ["show", "--externals", "dmain"],
    ["show", "--depends:direct", "--externals", "dmain"],
    ["show", "--externals", "--no-version", "dmain"],
    ["show", "--depends", "listDA"],
    ["show", "--depends", "--filter:dev", "listDA"],
    ["show", "--depends", "--filter:run", "listDA"],
    ["show", "--depends:direct", "--filter:run", "listDA"],
    ["show", "--depends:direct", "--filter:dev", "listDA"],
    ["show", "--depends", "reca"],
    ["show", "--depends", "recb"],
    ["show", "--depends", "cd1"],
    ["show", "--depends", "--externals:only", "cdb"],
    ["show", "--depends", "supermod"],
    ["show", "--depends", "dmain", "listDA"],
    ["show", "--plan=meta-meta", "--depends", "meta-meta/both:v2"],
    ["show", "--rdepends", "usethisplg"],
    ["show", "--rdepends", "lib1"],
    ["show", "--rdepends", "lib2", "dep1"],
    ["show", "--rdepends", "nothere"],
    ["show", "-r", "lib3"],
]


@pytest.mark.oracle
@pytest.mark.parametrize("args", SHOW_CASES, ids=" ".join)
def test_show_same_as_bash(sandboxes, args):
    bash, python = sandboxes
    rb, rp = bash.run(args), python.run(args)
    assert (rp.returncode, rp.stdout, rp.stderr) == (rb.returncode, rb.stdout, rb.stderr)


#  scbi show on the real plug-ins (scripts.d): more hook shapes for
#  --rdepends, real OS packages for --externals
REAL_SHOW_CASES = [
    ["show", "--rdepends", "c-sandbox"], ["show", "--rdepends", "c-gprbuild"],
    ["show", "--depends", "c-gps"], ["show", "--externals", "c-darktable"],
    ["show", "--externals:only", "--no-version", "c-libadalang"],
]


@pytest.mark.oracle
@pytest.mark.parametrize("args", REAL_SHOW_CASES, ids=" ".join)
def test_show_real_plugins_same_as_bash(sandboxes, args):
    bash, python = sandboxes
    args = [f"--plugins={REPO_ROOT}/scripts.d", *args]
    rb, rp = bash.run(args), python.run(args)
    assert (rp.returncode, rp.stdout, rp.stderr) == (rb.returncode, rb.stdout, rb.stderr)


SHELL_CASES = [
    ["shell", "--run", "dorun"], ["shell", "--run", "dorun/one"], ["shell", "--run", "dorun/one.two"],
    ["shell", "--run", "dorun/two.one"], ["shell", "--run=echo toto", "dorun"],
    ["shell", "--run", "mainmult"], ["shell", "--run=mainmult", "mainmult"],
    ["shell", "--run=which mainlib ; mainlib", "metaagg3"],
    ["shell", "--run=which mainlib ; mainlib", "metaagg3/agg"],
    ["shell", "--run=echo $SCBI_SHELL $PATH", "lib1", "lib2"],
    ["shell", "--mode:tests", "--run=echo $SCBI_SHELL", "lib2"],
    ["shell", "--mode:dev", "--run=echo $SCBI_SHELL", "lib2"],
    ["shell", "--run", "lib1"], ["shell"], ["-h", "shell"], ["shell", "--mode:bogus", "lib1"],
    #  interactive mode: $SHELL is a script showing where it runs
    ["shell", "lib2"], ["shell", "--mode:sb", "lib2"], ["shell", "--mode:dev", "lib2"],
    ["shell", "--mode:tests", "lib2"], ["shell", "metaagg3/agg"],
]

FAKE_SHELL = """#!/bin/bash
echo "shell in $PWD mode=$SCBI_SHELL args=$*"
echo "PATH=$PATH"
declare -F | grep -c handle-env
"""


@pytest.mark.oracle
def test_shell_same_as_bash(tmp_path):
    bash, python = pair(tmp_path)
    for sb in (bash, python):
        fake = sb.root / "fakeshell"
        fake.write_text(FAKE_SHELL)
        fake.chmod(0o755)
        #  build the modules used (same state in both sandboxes)
        for mod in ("dorun", "mainmult", "metaagg3", "lib1", "lib2"):
            sb.run([mod])
    for args in SHELL_CASES:
        env = {"SHELL": str(python.root / "fakeshell")}
        rb = bash.run(args, {"SHELL": str(bash.root / "fakeshell")})
        rp = python.run(args, env)
        m = mask_bash_error_location
        assert (rp.returncode, m(rp.stdout), m(rp.stderr)) == (rb.returncode, m(rb.stdout), m(rb.stderr)), args


SOURCE_ARCHIVE_CASES = [
    ["source-archive", "libarch:v1"], ["source-archive", "libarch/gz"],
    ["source-archive", "libarch/bz2:v2"], ["source-archive", "--lower-case", "libarch/tar:v1"],
    ["source-archive", "--sha1", "libarch/xz"], ["source-archive", "--sha256", "--clean-version", "libarch/zip:v1"],
    ["source-archive", "--md5", "-c", "libarch:v2.0"], ["source-archive", "libarch:nothere"],
    ["source-archive", "nothere"], ["source-archive", "libarch/native"], ["source-archive", "dep1"],
    ["source-archive", "lib1", "lib2"], ["source-archive"], ["-h", "source-archive"],
    ["source-archive", "--bogus", "lib1"],
]


@pytest.mark.oracle
def test_source_archive_same_as_bash(tmp_path):
    import hashlib
    import shutil
    import subprocess

    from oracle import REPO_ROOT

    bash, python = pair(tmp_path)
    repos = tmp_path / "repos"
    shutil.copytree(REPO_ROOT / "tests" / ".root" / "repos", repos, ignore=shutil.ignore_patterns("withsubm*"))
    env = {"TESTREPOS": str(repos), "GIT_ALLOW_PROTOCOL": "file"}
    for args in SOURCE_ARCHIVE_CASES:
        rb, rp = bash.run(args, env), python.run(args, env)
        def m(text):
            #  random work directory
            return re.sub(r"/dev/shm/(tmp)?[\w]{6,8}", "<workdir>", mask_bash_error_location(text))

        assert (rp.returncode, m(rp.stdout), m(rp.stderr)) == (rb.returncode, m(rb.stdout), m(rb.stderr)), args
        made_b = sorted(p.name for p in bash.root.iterdir() if p.is_file() and not p.name.startswith("scbi"))
        made_p = sorted(p.name for p in python.root.iterdir() if p.is_file() and not p.name.startswith("scbi"))
        assert made_p == made_b, args
        for name in made_b:
            fb, fp = bash.root / name, python.root / name
            if name.endswith((".md5", ".sha1", ".sha256")):
                #  the archives hold the time of the checkouts: the sums
                #  differ, each one must match its archive
                assert fp.read_text().split()[1:] == fb.read_text().split()[1:], (args, name)
                tool = {"md5": "md5sum", "sha1": "sha1sum", "sha256": "sha256sum"}[name.rsplit(".", 1)[1]]
                for sb in (bash, python):
                    assert subprocess.run([tool, "-c", name], cwd=sb.root, capture_output=True).returncode == 0
            elif ".tar" in name or name.endswith((".tgz", ".zip")):
                lst = ["unzip", "-Z1"] if name.endswith(".zip") else ["tar", "tf"]
                lb = sorted(subprocess.run([*lst, str(fb)], capture_output=True, text=True).stdout.split())
                lp = sorted(subprocess.run([*lst, str(fp)], capture_output=True, text=True).stdout.split())
                assert lp == lb, (args, name)
        for name in made_b:
            (bash.root / name).unlink()
            (python.root / name).unlink()
