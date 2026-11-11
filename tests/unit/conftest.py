import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from oracle import REPO_ROOT, BashOracle  # noqa: E402


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def oracle(tmp_path_factory) -> BashOracle:
    """Bash reference implementation with driver + runtime loaded."""
    return BashOracle(tmp_path_factory.mktemp("oracle"))
