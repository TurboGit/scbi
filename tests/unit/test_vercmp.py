import itertools

import pytest

from corpus import OPS, version_strings
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


@pytest.mark.oracle
def test_check_versions_oracle(oracle):
    versions = version_strings()
    cases = [(a, op, b) for a, b in itertools.product(versions, repeat=2) for op in OPS]
    expected = oracle.batch('check-versions "$1" "$2" "$3" && echo T || echo F', cases)
    mismatches = [
        c for c, out in zip(cases, expected) if check_versions(*c) != (out.strip() == "T")
    ]
    assert mismatches == [], mismatches[:20]


@pytest.mark.oracle
def test_get_version_number_oracle(oracle):
    values = version_strings() + ["gnat-12.2", "abc", "1.2.3.4", "x86_64", "-1", "release_7_8"]
    expected = oracle.batch('get-version-number R "$1"; printf "%s" "$R"', [(v,) for v in values])
    for v, out in zip(values, expected):
        assert get_version_number(v) == out, v
