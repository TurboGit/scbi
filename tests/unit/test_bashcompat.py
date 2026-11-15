import pytest

from scbi.bashcompat import ShellSyntaxError, shell_words

WORDS = [
    'a b  c',
    '-DLIB="-L/usr/lib -lmpi_cxx -lmpi"',
    "'single quoted' x",
    'a\\ b "c\\"d" e',
    '"" x',
    'pre"mid dle"post',
    '--prefix=/opt/x --enable-y',
]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("$(get-build-type MAKE true) x", ["$(get-build-type MAKE true)", "x"]),
        ("$(last-modified-directory $PREFIX/lib/python*)/site-packages",
         ["$(last-modified-directory $PREFIX/lib/python*)/site-packages"]),
        ('"$PREFIX/a b" ${X}', ["$PREFIX/a b", "${X}"]),
    ],
)
def test_shell_words_keep_expansions(text, expected):
    assert shell_words(text) == expected


@pytest.mark.parametrize("text", ["'$X'", '"abc', "$(abc"])
def test_shell_words_errors(text):
    with pytest.raises(ShellSyntaxError):
        shell_words(text)
