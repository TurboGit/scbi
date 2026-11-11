"""Helpers reproducing Bash semantics the reference implementation relies on.

The Python port must behave exactly like the Bash driver (same output, same
plan resolution). Some results depend on Bash details such as word
splitting, ``read`` field assignment or the iteration order of associative
arrays; they are gathered here.
"""

from __future__ import annotations

_IFS_WS = " \t\n"


def words(value: str) -> list[str]:
    """Word splitting of an unquoted expansion with the default IFS.

    Pathname expansion is not reproduced: SCBI values never contain glob
    characters meant to match files at these places.
    """
    return value.split()


def ifs_split(value: str, sep: str) -> list[str]:
    """Word splitting with IFS set to a single non-whitespace character.

    Consecutive separators give empty fields, a trailing separator does not
    create a final empty field and an empty string gives no field.
    """
    if value == "":
        return []
    fields = value.split(sep)
    if fields[-1] == "":
        fields.pop()
    return fields


def read_fields(line: str, count: int) -> list[str]:
    """Fields assigned by ``read -r v1 ... vN`` for one input line.

    Words are separated by IFS whitespace; the last variable receives the
    rest of the line (inner whitespace preserved, trailing one removed).
    Missing fields are empty strings.
    """
    rest = line.strip(_IFS_WS)
    fields: list[str] = []
    for _ in range(count - 1):
        if not rest:
            break
        i = 0
        while i < len(rest) and rest[i] not in _IFS_WS:
            i += 1
        fields.append(rest[:i])
        rest = rest[i:].lstrip(_IFS_WS)
    if rest:
        fields.append(rest)
    return fields + [""] * (count - len(fields))


def read_lines(text: str) -> list[str]:
    """Lines seen by ``while read ...; done < file``.

    A last line without a terminating newline is not seen by the loop body
    (``read`` returns a non-zero status for it).
    """
    lines = text.split("\n")
    #  text ending with "\n" gives a final empty element; otherwise the
    #  last element is an unterminated line, also dropped.
    return lines[:-1]


_ASSOC_BUCKETS = 1024


def _bash_hash(key: str) -> int:
    #  FNV-1 as implemented by hash_string() in Bash hashlib.c
    h = 2166136261
    for c in key.encode():
        h = (h * 16777619) & 0xFFFFFFFF
        h ^= c
    return h


def assoc_keys(keys) -> list[str]:
    """Order of ``${!A[@]}`` for a Bash associative array.

    ``keys`` are given in insertion order. Bash stores them in a hash table
    of 1024 buckets, newest entry first in each bucket, and iterates over
    the buckets in order. (Tables are never large enough here to be
    rehashed.)
    """
    buckets: dict[int, list[str]] = {}
    seen: set[str] = set()
    for k in keys:
        if k in seen:
            continue
        seen.add(k)
        buckets.setdefault(_bash_hash(k) & (_ASSOC_BUCKETS - 1), []).insert(0, k)
    return [k for b in sorted(buckets) for k in buckets[b]]
