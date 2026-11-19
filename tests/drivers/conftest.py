"""pytest plumbing of the regression drivers (testNNN.py): the fixture
``t`` (tests/harness.py) gives each driver its own test root; the checks
which failed are reported when the driver ends."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import Driver, make_root  # noqa: E402


@pytest.fixture
def t(request, tmp_path) -> Driver:
    root = tmp_path / "tests"
    root.mkdir()
    make_root(root)
    return Driver(root, str(request.path))


#@pytest.hookimpl(wrapper=True)
@pytest.hookimpl(hookwrapper=True)
def pytest_pyfunc_call(pyfuncitem):
    result = yield
    driver = pyfuncitem.funcargs.get("t")
    counts = os.environ.get("SCBI_TEST_COUNTS")
    if counts and isinstance(driver, Driver):
        #  the number of checks of each driver (to compare two runs)
        with open(counts, "a") as f:
            f.write(f"{Path(driver.test_file).stem} {driver.checks}\n")
    if isinstance(driver, Driver) and driver.failures:
        pytest.fail(driver.report(), pytrace=False)
    return result
