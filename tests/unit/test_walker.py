"""The dependency walker (walker.py) compared with the Bash
``for-all-modules*`` functions, through the test-only probe sub-command."""

import pytest

from probe import probe_pair, same
from scbi.walker import ENTRY_POINTS

MODULES = ["dmain", "listDA", "reca", "cd1", "cdb", "lib1", "meta-meta/both:v2",
           "lib2", "dmod", "nothere", "lib1:skip"]


@pytest.fixture(scope="module")
def sandboxes(tmp_path_factory):
    return probe_pair(tmp_path_factory.mktemp("walk"))


@pytest.mark.oracle
@pytest.mark.parametrize("entry", sorted(ENTRY_POINTS))
@pytest.mark.parametrize("modref", MODULES)
def test_walker_same_as_bash(sandboxes, entry, modref):
    args = ["--plan=meta-meta"] if modref.startswith("meta-meta") else []
    same(*sandboxes, args + ["probe", "walk", entry, modref])
