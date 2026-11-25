"""The driver runs on Python 3.9: a static check of the sources for the
syntax and the most common library features of later versions (it runs
on any Python; the full check is the testsuite run with Python 3.9:
make test unit PYTHON=python3.9)."""

import ast

import pytest

from corpus import REPO_ROOT

SOURCES = sorted((REPO_ROOT / "src" / "scbi").rglob("*.py"))
#  types whose "X | Y" fails at run time before Python 3.10
_TYPES = {"None", "int", "str", "float", "bool", "bytes", "list", "dict", "tuple", "set", "frozenset"}
#  keyword arguments added in Python 3.10+
_KEYWORDS = {"root_dir", "strict", "kw_only", "slots", "include_hidden"}
_MODULES = {"tomllib"}


def _is_type(node) -> bool:
    if isinstance(node, ast.Constant) and node.value is None:
        return True
    if isinstance(node, ast.Name):
        return node.id in _TYPES
    if isinstance(node, ast.Subscript):
        return _is_type(node.value)
    return isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr) and _is_type(node.left)


def _annotations(tree) -> set[int]:
    """The ids of the nodes of the annotations (not evaluated with
    'from __future__ import annotations')."""
    result = set()
    for n in ast.walk(tree):
        anns = []
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            anns.append(n.returns)
        elif isinstance(n, ast.AnnAssign):
            anns.append(n.annotation)
        elif isinstance(n, ast.arg):
            anns.append(n.annotation)
        for a in anns:
            if a is not None:
                result.update(id(x) for x in ast.walk(a))
    return result


def _fstring_issues(text: str, tree) -> list[int]:
    """f-strings reusing their quote or a backslash in an expression
    (Python 3.12, PEP 701)."""
    lines = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.JoinedStr):
            continue
        seg = ast.get_source_segment(text, n) or ""
        start = next((i for i, c in enumerate(seg) if c in "'\""), None)
        if start is None:
            continue
        quote = seg[start:start + 3] if seg[start:start + 3] in ("'''", '"""') else seg[start]
        for v in n.values:
            if isinstance(v, ast.FormattedValue):
                expr = ast.get_source_segment(text, v.value) or ""
                if quote in expr or "\\" in expr:
                    lines.append(n.lineno)
    return lines


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(REPO_ROOT / "src")))
def test_python39_compatible(path):
    text = path.read_text()
    ast.parse(text, filename=str(path), feature_version=(3, 9))  # match, except*...
    tree = ast.parse(text)
    future = "from __future__ import annotations" in text
    skip = _annotations(tree) if future else set()
    issues = []
    for n in ast.walk(tree):
        if (isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr) and id(n) not in skip
                and (_is_type(n.left) or _is_type(n.right))):
            issues.append(f"{n.lineno}: runtime 'X | Y' type (Python 3.10)")
        elif isinstance(n, ast.Call):
            for kw in n.keywords:
                if kw.arg in _KEYWORDS:
                    issues.append(f"{n.lineno}: keyword argument {kw.arg}= (Python 3.10+)")
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in n.names] + ([n.module] if isinstance(n, ast.ImportFrom) else [])
            issues += [f"{n.lineno}: module {m} (Python 3.11)" for m in names if m in _MODULES]
    issues += [f"{line}: f-string nested quote or backslash (Python 3.12)" for line in _fstring_issues(text, tree)]
    assert issues == []
