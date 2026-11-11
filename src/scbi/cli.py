"""Command line entry point of the Python SCBI driver.

Only a placeholder for now: the driver is implemented incrementally (see the
migration plan). Until then every invocation fails so that the regression
ratchet reports the tests as not passing.
"""

import sys


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    print("scbi (python): not implemented yet", file=sys.stderr)
    return 1
