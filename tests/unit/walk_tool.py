"""Test-only sub-command ``scbi walk <entry> <modref>``: the Python
dependency walker with a recording callback (compared with scbi-walk, the
same with the Bash walker, in test_walker.py)."""

import sys

from scbi.build import Builder
from scbi.walker import Walker


def main(driver, args):
    entry, modref = driver.modules[0], driver.modules[1]

    def callback(argv):
        sys.stdout.write("CB " + " ".join(argv) + "\n")
        sys.stdout.flush()

    rc = Walker(Builder(driver)).walk(entry, callback, modref, "x1", "x2", name="cb")
    sys.stdout.write(f"rc={rc}\n")
    return 0
