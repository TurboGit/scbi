import pytest

from scbi.vercmp import check_versions, get_version_number


@pytest.mark.parametrize(
    "a, op, b, expected",
    [
        ("1.0", "<", "1.0.1", True),
        ("1.0", "=", "1.0", True),
        ("v1.0", "==", "1.0", True),
        ("2.0", ">", "1.9", True),
        ("1.10", ">", "1.9", True),
        # The check-versions header comment (R4) claims the opposite, but the
        # Bash code (the reference) answers false; see the oracle test.
        ("3.0003", ">", "3.0000004", False),
        ("1.0", ">=", "1.0", True),
        ("1.0", "<=", "0.9", False),
        ("1.0", "!=", "1.1", True),
    ],
)
def test_check_versions(a, op, b, expected):
    assert check_versions(a, op, b) is expected


def test_invalid_operator():
    with pytest.raises(ValueError):
        check_versions("1", "~", "2")


@pytest.mark.parametrize(
    "value, expected",
    [("1.2.3", "1.2.3"), ("v2.0", "2.0"), ("gdb-head", "0"), ("7_8", "7.8")],
)
def test_get_version_number(value, expected):
    assert get_version_number(value) == expected
