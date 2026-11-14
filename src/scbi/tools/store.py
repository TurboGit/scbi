"""scbi store: a key/value store in $SCBI_PLUGINS/.store (port of
scbi-store).

    scbi store KEY             value of KEY (status 1 if not found)
    scbi store KEY VALUE       record KEY
    scbi store -d KEY...       delete keys
    scbi store -l|-k [KEY...]  list keys, --list:full with the values
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from scbi.bashcompat import assoc_keys, words


def _read_no_r(line: str) -> list[str]:
    """``read key value`` (no -r): backslash escapes removed, the first
    word and the rest of the line (blanks around removed)."""
    out, i = [], 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            out.append(line[i + 1])
            i += 2
            continue
        if c == "\\":
            i += 1
            continue
        out.append(c)
        i += 1
    text = "".join(out).strip(" \t")
    parts = text.split(None, 1)
    return (parts + ["", ""])[:2]


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, str] = {}

    def load(self) -> None:
        """sto-load (keys in file order, later duplicates win)."""
        if not self.path.is_file():
            return
        text = self.path.read_text(errors="surrogateescape")
        lines = text.split("\n")
        #  while read ... < file: an unterminated last line is not read
        for line in lines[:-1]:
            key, value = _read_no_r(line)
            self.data[key] = value

    def save(self) -> None:
        """sto-save: ``echo $key ${SCBI_STORE[$key]}`` in hash order."""
        with open(self.path, "w") as f:
            for key in assoc_keys(self.data):
                f.write(" ".join(words(f"{key} {self.data[key]}")) + "\n")


USAGE = """
SCBI-STORE {version}

{argv0} store [options]

   -h | --help             this help message
   -v | --version          display driver & plug-ins versions
      | --plugins=<dir>    specify the plugins' directory
   -e | --env=<name>       environment file ~/.scbi-<name>
      | --list-keys        list all stored keys
   -l | --list[:full]      list stored keys possibly with values
   -d | --delete           remove a key
      | --stat             display some status of current setup"""


def main(driver, args: list[str]) -> int:
    """``scbi store`` with ``args`` (options and keys after the driver
    parsing). Returns the exit status."""
    proc = subprocess.run(
        ["getopt", "-o", "kld", "-l", "list-keys,list:full,list,delete", "--", *args],
        capture_output=True, text=True, env=driver.base_env())
    if proc.returncode != 0:
        sys.stdout.write(proc.stderr)
        print('try "scbi store --help" for more information.')
        return 1
    #  eval set -- <getopt output>
    parsed = shlex.split(proc.stdout)

    do_list, do_delete, keys = "no", False, []
    for a in parsed:
        if a in ("-k", "--list-keys", "-l", "--list"):
            do_list = "yes"
        elif a == "--list:full":
            do_list = "full"
        elif a in ("-d", "--delete"):
            do_delete = True
        elif a == "--":
            pass
        else:
            keys.append(a)

    if driver.get("DO_HELP") == "yes":
        print(USAGE.format(version=driver.get("SCBI_VERSION"), argv0=driver.argv0))
        return 0

    store = Store(Path(driver.get("SCBI_PLUGINS")) / ".store")

    if do_list != "no":
        def listing(key: str) -> None:
            s = Store(store.path)
            s.load()
            for k in assoc_keys(s.data):
                if k == key or not key:
                    if do_list == "full":
                        print(" ".join(words(f"{k} {s.data[k]}")))
                    else:
                        print(k)

        selected = words(" ".join(keys))
        if not keys or not keys[0]:
            listing("")
        else:
            for key in selected:
                listing(key)
        return 0

    if do_delete:
        if not keys:
            print("scbi store : delete require at least one argument.")
        else:
            for key in words(" ".join(keys)):
                s = Store(store.path)
                s.load()
                s.data.pop(key, None)
                s.save()
            return 0
    elif len(keys) == 2:
        store.load()
        store.data[keys[0]] = keys[1]
        store.save()
        return 0
    elif len(keys) == 1:
        store.load()
        found = keys[0] in store.data
        value = " ".join(words(store.data.get(keys[0], "")))
        if os.isatty(1):
            print(value)
        else:
            sys.stdout.write(value)
        sys.stdout.flush()
        return 0 if found else 1

    print(USAGE.format(version=driver.get("SCBI_VERSION"), argv0=driver.argv0))
    return 0
