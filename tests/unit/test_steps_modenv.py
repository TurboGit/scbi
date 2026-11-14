"""Environment of a module build (steps/modenv.py: handle-env,
handle-build-depends-env, handle-tests-depends-env, handle-module-env,
plugin-call-env-hooks) compared with the Bash driver functions, through
the test-only probe sub-command."""

import pytest

from probe import probe_pair, same

MODULES = ["lvl0", "lvl3", "mainmult", "mainlib", "libenv", "testme", "usetool", "metaagg",
           "metaagg2", "metaagg3", "metaagg4", "metapoly", "extenv", "varenv", "lib1:skip", "cd1",
           "reca"]


@pytest.fixture(scope="module")
def sandboxes(tmp_path_factory):
    return probe_pair(tmp_path_factory.mktemp("modenv"))


@pytest.mark.oracle
@pytest.mark.parametrize("kind", ["env", "build", "tests", "build-env", "tests-env"])
@pytest.mark.parametrize("modref", MODULES)
def test_module_env_same_as_bash(sandboxes, kind, modref):
    same(*sandboxes, ["probe", "env", kind, "@root", modref])


@pytest.mark.oracle
@pytest.mark.parametrize("modref", ["metaagg", "metaagg3", "lib1"])
def test_module_env_of_meta_parent(sandboxes, modref):
    #  handle-module-env for a module seen from a meta-module
    same(*sandboxes, ["probe", "env", "env", "metaagg", modref])
