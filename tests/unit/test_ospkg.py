"""OS packages helpers (scbi/ospkg.py)."""

from scbi.ospkg import clean_version_string


def test_clean_version_string():
    assert clean_version_string("1:2.3.4-5+deb12u1") == "2.3.4"
    assert clean_version_string("3.2.7-1+repack1-2") == "3.2.7-1"
    assert clean_version_string("6.3+dfsg-1") == "6.3"
    assert clean_version_string("1.2~rc1-3") == "1.2"
    assert clean_version_string("4") == "4"
