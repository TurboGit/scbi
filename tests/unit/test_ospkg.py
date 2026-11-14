"""OS packages and auto variants (scbi/ospkg.py) compared with the Bash
functions of 6_distpkg / 9_versions, through the test-only probe
sub-command, with the packages of this machine (Debian-like: SCBI_OS_NAME
deb)."""

import shutil

import pytest

from probe import probe_pair, same
from scbi.ospkg import clean_version_string

pytestmark = pytest.mark.skipif(shutil.which("dpkg-query") is None, reason="needs dpkg-query")

ENV = {"SCBI_OS_NAME": "deb"}
PACKAGES = ["rsync", "rsync:1.0", "rsync:999", "bash:NONE", "scbi-no-such-package",
            "scbi-no-such-package:2", "os@-gmp-dev", "os@-gmp-dev:[v]", "os@-unknown-alias", "gcc"]


def test_clean_version_string():
    assert clean_version_string("1:2.3.4-5+deb12u1") == "2.3.4"
    assert clean_version_string("3.2.7-1+repack1-2") == "3.2.7-1"
    assert clean_version_string("6.3+dfsg-1") == "6.3"
    assert clean_version_string("1.2~rc1-3") == "1.2"
    assert clean_version_string("4") == "4"


@pytest.fixture(scope="module")
def sandboxes(tmp_path_factory):
    return probe_pair(tmp_path_factory.mktemp("ospkg"))


@pytest.mark.oracle
@pytest.mark.parametrize("cmd", ["check-pkg", "pkg-status"])
@pytest.mark.parametrize("pkg", PACKAGES)
def test_packages_same_as_bash(sandboxes, cmd, pkg):
    same(*sandboxes, ["probe", cmd, pkg], ENV)


@pytest.mark.oracle
@pytest.mark.parametrize("plan", ["autoa", "autob", "autov", "metaprop"])
@pytest.mark.parametrize("warning", ["no", "yes"])
def test_auto_variant_same_as_bash(sandboxes, plan, warning):
    #  the auto variants of the plan are resolved at start-up (messages
    #  shown with --stat); Bash runs them as parallel jobs: the order of
    #  the messages of two modules may vary
    bash, python = sandboxes
    args, env = [f"--plan={plan}", "--stat:short"], {**ENV, "DO_WARNING_EXTERNAL": warning}
    rb, rp = bash.run(args, env), python.run(args, env)
    assert (rp.returncode, rp.stderr) == (rb.returncode, rb.stderr)
    assert sorted(rp.stdout.splitlines()) == sorted(rb.stdout.splitlines())
