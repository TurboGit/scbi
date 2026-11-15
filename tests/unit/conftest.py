import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from corpus import REPO_ROOT  # noqa: E402


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT
