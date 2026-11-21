"""get-archive: download the archive of a module if needed and extract it
in $SCBI_BDIR/<module>/archive-src (port of get-archive,
scripts.d/5_tools).

Output as in Bash, where it runs as ``get-archive ... 2>>$log | tee -a
$log``: the standard output (``out``) goes to the console and the log,
the error messages (elog, tools) are appended to the log. The log is the
report log of the module (the whole day): it is never truncated (Bash
truncated its per-variant log with ``> $log`` for some commands).
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
from collections.abc import Callable

from scbi.bashcompat import words
from scbi.sources.archive import extract, registry
from scbi.sources.data import archive_data
from scbi.sources.run import command_env


def check_tool(name: str, env: dict[str, str]) -> bool:
    """``check-tool``: ``command -v`` finds it."""
    return bool(name) and shutil.which(name, path=env.get("PATH")) is not None


class _Io:
    def __init__(self, log: str, env: dict[str, str]):
        self.log = log
        self.env = env

    def run(self, args: list[str], cwd: str, stdout_to_stderr: bool = False) -> int:
        """A command, its output appended to the log."""
        with open(self.log, "a") as f:
            try:
                return subprocess.run(args, cwd=cwd, env=self.env, stdin=subprocess.DEVNULL,
                                      stdout=f, stderr=subprocess.STDOUT).returncode
            except FileNotFoundError:
                f.write(f"bash: {args[0]}: command not found\n")
                return 127


def get_archive(builder, module: str, variant: str, version: str, log: str,
                out: Callable[[str], None]) -> int:
    d = builder.d
    tar, _ = archive_data(builder, module, variant, version)
    tar = tar + [""] * (7 - len(tar))
    proxy, taropts, tarcp, tarurl, tarsrc, tardir = tar[1:7]

    if tarsrc.upper() == "NONE":
        return 0

    options = taropts.replace(",", " ", 1) if taropts.upper() != "NONE" else ""
    archives = d.get("SCBI_ARCHIVES")
    bdir = d.get("SCBI_BDIR")
    #  already downloaded by the prefetch (--update:prefetch): its result
    prefetcher = getattr(builder, "prefetcher", None)
    done = prefetcher.archive_result(f"{archives}/{tarsrc}", tarurl, log) if prefetcher else None
    with open(log, "a") as errlog:
        logger = dataclasses.replace(d.log, stderr=errlog)
        return _get_archive(builder, module, variant, tar, proxy, options, tarcp, tarurl, tarsrc, tardir,
                            archives, bdir, log, logger, out,
                            downloaded=done.downloaded if done is not None else None)


def _get_archive(builder, module, variant, tar, proxy, options, tarcp, tarurl, tarsrc, tardir,
                 archives, bdir, log, logger, out, downloaded: int | None = None) -> int:
    """``downloaded``: the archive already checked / downloaded by the
    prefetch (0: unchanged, 1: downloaded), None: done here."""
    def elog(*msg: str) -> None:
        logger.stderr.flush()
        logger.elog(module, *msg)
        logger.stderr.flush()

    env = command_env(builder, module, variant, proxy)
    io = _Io(log, env)
    cwd = os.getcwd()

    if downloaded is not None:
        pass
    elif tarcp.upper() != "NONE" and tarurl.upper() != "NONE":
        if not check_tool(tarcp, env):
            elog("Required", "tool", *words(tarcp), "missing")
            return 1
        downloaded = _download(io, cwd, tarcp, options, tarurl, tarsrc, archives, elog)
    else:
        downloaded = 1

    if not os.path.isfile(f"{archives}/{tarsrc}"):
        elog("archive", *words(tarsrc), "not", "found")
        return 1

    mdir = f"{bdir}/{module}"
    if downloaded == 0 and os.path.isdir(f"{mdir}/archive-src"):
        return 0

    #  ilog to the standard output (console and log)
    lines: list[str] = []
    dataclasses.replace(logger, stdout=_Lines(lines)).ilog(module, "extract", "archive", *words(tarsrc))
    for line in "".join(lines).splitlines():
        out(line)

    if not os.path.isdir(mdir):
        io.run(["mkdir", "-p", mdir], cwd)
    for name in ("tarsrc", "tar", "tar-sha1", "archive-src", "archive", "archive-sha1", "archivetmp"):
        _rm_rf(os.path.join(mdir, name))
    os.makedirs(f"{mdir}/archivetmp", exist_ok=True)
    tmp = f"{mdir}/archivetmp"

    status = extract.unpack(io, tmp, f"{archives}/{tarsrc}", tarsrc, env, elog)
    if status is None:
        return 1
    if status != 0:
        elog("archive", *words(tarsrc), "is", "corrupted")
        return 1

    if not extract.move_sources(io, tmp, f"{mdir}/archive-src", tardir, tarsrc, elog):
        return 1

    _rm_rf(tmp)
    #  realpath --relative-to="$PWD" (both resolved)
    here = os.path.realpath(mdir)
    io.run(["ln", "-s", os.path.relpath(os.path.realpath(f"{archives}/{tarsrc}"), here), "archive"], mdir)
    if os.path.isfile(f"{archives}/{tarsrc}.sha1"):
        io.run(["ln", "-s", os.path.relpath(os.path.realpath(f"{archives}/{tarsrc}.sha1"), here),
                "archive-sha1"], mdir)
    return 0


def _download(io: _Io, cwd: str, tarcp: str, options: str, tarurl: str, tarsrc: str,
              archives: str, elog, tmp_dir: str = "/tmp") -> int:
    """The sub-shell of get-archive: 0 when the archive was already there
    and up-to-date, 1 when downloaded (or tried); the SHA-1 downloaded in
    ``tmp_dir``."""
    proto = registry.get(tarcp)
    tmp_sha1 = f"{tmp_dir}/{tarsrc}.sha1"
    do_download = 0

    #  the SHA-1 if present
    if proto is not None:
        rc = io.run(proto.command(tarcp, options, f"{tarurl}/{tarsrc}.sha1", tmp_sha1), cwd)
    else:
        rc = 1
    if rc == 0:
        if not _same_file(f"{archives}/{tarsrc}.sha1", tmp_sha1):
            do_download = 1

    if do_download == 1 or not os.path.isfile(f"{archives}/{tarsrc}"):
        do_download = 1
        if proto is not None:
            rc = io.run(proto.command(tarcp, options, f"{tarurl}/{tarsrc}", f"{archives}/{tarsrc}"), cwd)
        else:
            elog("unknown", "tar", "protocol", *words(tarcp))
            rc = 1
        if rc != 0:
            for f in (f"{archives}/{tarsrc}", f"{archives}/{tarsrc}.sha1"):
                _rm_f(f)
            elog("cannot", "get", "archive:", *words(tarcp))
            elog("from", *words(f"{tarurl}/{tarsrc}"))
        elif os.path.isfile(tmp_sha1):
            shutil.copyfile(tmp_sha1, f"{archives}/{tarsrc}.sha1")

    _rm_f(tmp_sha1)
    return do_download


class _Lines:
    def __init__(self, lines: list[str]):
        self.lines = lines

    def write(self, text: str) -> None:
        self.lines.append(text)

    def flush(self) -> None:
        pass


def _same_file(a: str, b: str) -> bool:
    """``diff -q A B`` succeeds."""
    try:
        with open(a, "rb") as fa, open(b, "rb") as fb:
            return fa.read() == fb.read()
    except OSError:
        return False


def _rm_f(path: str) -> None:
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            return
        os.unlink(path)
    except OSError:
        pass


def _rm_rf(path: str) -> None:
    if os.path.islink(path) or os.path.isfile(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
