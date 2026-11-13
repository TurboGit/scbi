"""get-archive (sources/archive) compared with the Bash function: the
same output, log, archives directory and extracted sources, on a
sequence of cases sharing the sandboxes (downloads, up-to-date checks,
formats, errors)."""

import hashlib
import os
import re
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from probe import probe_pair

PLUGIN = """
function arch-archive()
{
    local VERSION=$1
    echo default
    echo none
    echo ${ARCH_CP:-cp}
    echo ${ARCH_URL:-none}
    echo ${ARCH_FILE}
    [[ -n $ARCH_DIR ]] && echo $ARCH_DIR
}
"""


def make_store(store: Path) -> None:
    src = store.parent / "src"
    (src / "top" / "sub").mkdir(parents=True)
    (src / "top" / "a.txt").write_text("a\n")
    (src / "top" / "sub" / "b.txt").write_text("b\n")
    (src / "flat").mkdir()
    (src / "flat" / "x.txt").write_text("x\n")
    (src / "flat" / ".hidden").write_text("h\n")
    (src / "flat" / "d").mkdir()
    store.mkdir()
    with tarfile.open(store / "top-1.tar.bz2", "w:bz2") as t:
        t.add(src / "top", arcname="top-1")
    with tarfile.open(store / "flat-1.tar.gz", "w:gz") as t:
        for f in ("x.txt", ".hidden", "d"):
            t.add(src / "flat" / f, arcname=f)
    with zipfile.ZipFile(store / "z-1.zip", "w") as z:
        z.write(src / "top" / "a.txt", "ztop/a.txt")
    (store / "bad-1.tar.bz2").write_text("not an archive")
    for f in ("top-1.tar.bz2", "flat-1.tar.gz"):
        h = hashlib.sha1((store / f).read_bytes()).hexdigest()
        (store / f"{f}.sha1").write_text(f"{h}  {f}\n")


#  each case: (environment of the archive hook, version, action before)
CASES = [
    ({"ARCH_FILE": "top-1.tar.bz2"}, "1", None),  # url none: archive not found
    ({"ARCH_URL": "{store}", "ARCH_FILE": "top-1.tar.bz2"}, "1", None),  # download + extract
    ({"ARCH_URL": "{store}", "ARCH_FILE": "top-1.tar.bz2"}, "1", None),  # up-to-date
    ({"ARCH_URL": "{store}", "ARCH_FILE": "top-1.tar.bz2"}, "1", "sha1"),  # changed sha1
    ({"ARCH_URL": "{store}", "ARCH_FILE": "top-1.tar.bz2"}, "1", "rmsrc"),  # extract again
    ({"ARCH_URL": "{store}", "ARCH_FILE": "top-1.tar.bz2", "ARCH_DIR": "sub"}, "1", "rmsrc"),
    ({"ARCH_URL": "{store}", "ARCH_FILE": "top-1.tar.bz2", "ARCH_DIR": "nope"}, "1", "rmsrc"),
    ({"ARCH_URL": "{store}", "ARCH_FILE": "flat-1.tar.gz"}, "1", None),  # no top directory
    ({"ARCH_URL": "{store}", "ARCH_FILE": "flat-1.tar.gz", "ARCH_DIR": "d"}, "1", "rmsrc"),
    ({"ARCH_URL": "{store}", "ARCH_FILE": "z-1.zip"}, "1", None),
    ({"ARCH_URL": "{store}", "ARCH_FILE": "bad-1.tar.bz2"}, "1", None),  # corrupted
    ({"ARCH_URL": "{store}", "ARCH_FILE": "nothere-1.tar.bz2"}, "1", None),  # download fails
    ({"ARCH_URL": "{store}", "ARCH_FILE": "top-1.tar.bz2", "ARCH_CP": "notatool"}, "1", "rmarch"),
    ({"ARCH_URL": "{store}", "ARCH_FILE": "top-1.tar.bz2", "ARCH_CP": "true"}, "1", None),  # unknown
    ({"ARCH_URL": "{store}", "ARCH_FILE": "NONE"}, "1", None),
]


def tree(root: Path) -> list[str]:
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        for name in sorted(dirnames + filenames):
            p = Path(dirpath, name)
            rel = p.relative_to(root)
            if p.is_symlink():
                result.append(f"{rel} -> {os.readlink(p)}")
            elif p.is_file():
                result.append(f"{rel} {hashlib.md5(p.read_bytes()).hexdigest()}")
            else:
                result.append(f"{rel}/")
    return sorted(result)


def mask(text: str, root: Path) -> str:
    text = re.sub(r"\d{4}/\d\d/\d\d \d\d:\d\d:\d\d", "<ts>", text)
    return text.replace(str(root), "<root>")


@pytest.mark.oracle
def test_get_archive_same_as_bash(tmp_path):
    bash, python = probe_pair(tmp_path / "sb")
    store = tmp_path / "store"
    make_store(store)
    for sb in (bash, python):
        (sb.root / "scripts.d" / "arch").write_text(PLUGIN)
        (sb.root / ".root" / ".archives").mkdir(parents=True, exist_ok=True)
    for i, (env, version, action) in enumerate(CASES):
        env = {k: v.format(store=store) for k, v in env.items()}
        for sb in (bash, python):
            arch = sb.root / ".root" / ".archives"
            mdir = sb.root / ".root" / "builds" / "arch"
            if action == "sha1":
                (arch / "top-1.tar.bz2.sha1").write_text("old\n")
            elif action == "rmsrc":
                shutil.rmtree(mdir / "archive-src", ignore_errors=True)
            elif action == "rmarch":
                (arch / "top-1.tar.bz2").unlink(missing_ok=True)
        args = ["probe", "get-archive", "arch", "default", version]
        rb, rp = bash.run(args, env), python.run(args, env)
        ctx = f"case {i}: {env} {action}"
        assert (rp.returncode, rp.stdout, rp.stderr) == (rb.returncode, rb.stdout, rb.stderr), ctx
        blog = bash.root / ".root" / "builds" / "arch.log"
        plog = python.root / ".root" / "builds" / "arch.log"
        assert mask(plog.read_text(), python.root) == mask(blog.read_text(), bash.root), ctx
        for sub in (".root/builds/arch", ".root/.archives"):
            assert tree(python.root / sub) == tree(bash.root / sub), (ctx, sub)
