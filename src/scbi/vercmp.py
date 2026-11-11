"""Version strings comparison and extraction.

Ports of ``check-versions`` (scripts.d/0_runtime) and ``get-version-number``
(scripts.d/5_tools). The Bash code relies on IFS word splitting, printf
format reuse and ASCII string comparison of padded strings; it is reproduced
literally here so that results are identical (checked by the oracle tests).
"""

from __future__ import annotations

import re

VERSION_OK = "99999999"
VERSION_ERROR = "-1"

_OPS = ("=", "==", "!=", "<", "<=", ">", ">=")


def _ifs_split(value: str, sep: str = ".") -> list[str]:
    """Bash word splitting of an unquoted expansion with IFS set to ``sep``.

    A non-whitespace IFS character delimits fields: consecutive separators
    give empty fields, but a trailing separator does not create a final
    empty field and an empty string gives no field.
    """
    if value == "":
        return []
    fields = value.split(sep)
    if fields[-1] == "":
        fields.pop()
    return fields


def _bash_printf(fmt_count: int, width: int, args: list[str]) -> str:
    """``printf`` with a format made of ``fmt_count`` ``%<width>s``.

    As in Bash the format is reused while arguments remain, and missing
    arguments are taken as empty strings.
    """
    if fmt_count == 0:
        return ""
    out: list[str] = []
    i = 0
    while True:
        for _ in range(fmt_count):
            arg = args[i] if i < len(args) else ""
            out.append(arg.rjust(width))
            i += 1
        if i >= len(args):
            break
    return "".join(out)


def _strip_leading_digits(value: str) -> str:
    return re.sub(r"^[0-9]*", "", value)


def _remove_suffix(value: str, suffix: str) -> str:
    #  ${a%$al}: the shortest suffix matching $al (taken literally here)
    if suffix and value.endswith(suffix):
        return value[: -len(suffix)]
    return value


def _normalized(v1: str, op: str, v2: str) -> tuple[str, str]:
    a = v1[1:] if v1.startswith("v") else v1
    b = v2[1:] if v2.startswith("v") else v2
    a = a[1:] if a.startswith("V") else a
    b = b[1:] if b.startswith("V") else b

    al = _strip_leading_digits(a.rsplit(".", 1)[-1])
    bl = _strip_leading_digits(b.rsplit(".", 1)[-1])
    ai = _remove_suffix(a, al)
    bi = _remove_suffix(b, bl)

    ap = re.sub(r"[0-9]", "", ai).replace(".", ".0")
    bp = re.sub(r"[0-9]", "", bi).replace(".", ".0")

    width = 1
    for x in _ifs_split(f"{a}.{b}"):
        width = max(width, len(x))

    #  fmt=${*//[^.]}: one %ws per dot found in the arguments joined by '.'
    count = "".join([v1, op, v2]).count(".") + 2

    sa = _bash_printf(count, width, _ifs_split(ai + bp))
    sa = f"{sa}-{al.rjust(width)}"
    sb = _bash_printf(count, width, _ifs_split(bi + ap))
    sb = f"{sb}-{bl.rjust(width)}"
    return sa, sb


def check_versions(v1: str, op: str, v2: str) -> bool:
    """Port of ``check-versions``: compare two versions with ``op``.

    ``op`` is one of ``= == != < <= > >=``.
    """
    if op not in _OPS:
        raise ValueError(f"invalid version operator {op!r}")
    a, b = _normalized(v1, op, v2)
    if op in ("=", "=="):
        return a == b
    if op == "!=":
        return a != b
    if op == "<":
        return a < b
    if op == ">":
        return a > b
    if op == "<=":
        return a < b or a == b
    return a > b or a == b


_NUM_RE = re.compile(r"[^0-9-]*(-?[0-9]*(\.[0-9]*)?(\.[0-9]*)?).*")


def get_version_number(value: str) -> str:
    """Port of ``get-version-number`` (scripts.d/5_tools)."""
    text = value.replace("_", ".")
    #  sed s/re/\1/g works line by line
    num = "\n".join(_NUM_RE.sub(r"\1", line, count=1) for line in text.split("\n"))
    nletters = len(value) - len(num)
    if nletters > 5 or num[-1:] == ".":
        return "0"
    return num
