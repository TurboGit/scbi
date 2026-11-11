"""Accepted divergences between the Bash reference and the Python port.

Each entry documents why the Bash behaviour is not reproduced. Oracle tests
use these predicates to exclude the corresponding inputs.
"""

GLOB_CHARS = set("*?[")


def modref_has_glob(ref: str) -> bool:
    """parse-module-ref compares strings with an unquoted right-hand side
    (``[[ $ver == $MODREF ]]``), so a reference containing glob characters
    is matched as a pattern and parsed oddly. Module references never contain
    glob characters (those come from @ref regular expressions in plans, which
    are not parsed as module references), so this quirk is not reproduced.
    """
    return bool(GLOB_CHARS & set(ref))
