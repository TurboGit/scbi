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

import contextlib
import dataclasses
import hashlib
import os
import re
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
                            downloaded=done.downloaded if done is not None else None, version=version)


def _get_archive(builder, module, variant, tar, proxy, options, tarcp, tarurl, tarsrc, tardir,
                 archives, bdir, log, logger, out, downloaded: int | None = None, version: str = "") -> int:
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
        downloaded = _download(io, cwd, tarcp, options, tarurl, tarsrc, archives, elog,
                               update=builder.d.get("DO_UPDATE") == "yes")
    else:
        downloaded = 1

    if not os.path.isfile(f"{archives}/{tarsrc}"):
        elog("archive", *words(tarsrc), "not", "found")
        return 1

    mdir = f"{bdir}/{module}"
    #  the SHA-256 given by the plug-in (archive-sha256), if any
    if not verify_sha256(builder, module, variant, version, archives, tarsrc, mdir, elog,
                         downloadable=tarcp.upper() != "NONE" and tarurl.upper() != "NONE"):
        return 1
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
              archives: str, elog, tmp_dir: str = "/tmp", update: bool = True) -> int:
    """The sub-shell of get-archive: 0 when the archive was already there
    and up-to-date, 1 when downloaded (or tried); the SHA-1 downloaded in
    ``tmp_dir``.

    Without ``update`` a local archive matching its local SHA-1 (or without
    one) is used as is, nothing is downloaded. The local archive and its
    SHA-1 are only replaced by a successful download: a failed one (archive
    removed from the server, server down) keeps them."""
    local = f"{archives}/{tarsrc}"
    local_sha1 = f"{local}.sha1"
    if not update and _local_archive_ok(local, local_sha1):
        return 0

    proto = registry.get(tarcp)
    tmp_sha1 = f"{tmp_dir}/{tarsrc}.sha1"
    do_download = 0

    #  the SHA-1 if present (an error page is not a SHA-1)
    _rm_f(tmp_sha1)
    if proto is not None:
        rc = io.run(proto.command(tarcp, options, f"{tarurl}/{tarsrc}.sha1", tmp_sha1), cwd)
    else:
        rc = 1
    if rc != 0 or _sha1_value(tmp_sha1) is None:
        _rm_f(tmp_sha1)
    elif not _same_file(local_sha1, tmp_sha1):
        do_download = 1

    if do_download == 1 or not os.path.isfile(local):
        do_download = 1
        part = f"{local}.part"
        _rm_f(part)
        if proto is not None:
            rc = io.run(proto.command(tarcp, options, f"{tarurl}/{tarsrc}", part), cwd)
        else:
            elog("unknown", "tar", "protocol", *words(tarcp))
            rc = 1
        if rc == 0 and os.path.isfile(part):
            os.replace(part, local)
            if os.path.isfile(tmp_sha1):
                shutil.copyfile(tmp_sha1, local_sha1)
        else:
            _rm_f(part)
            elog("cannot", "get", "archive:", *words(tarcp))
            elog("from", *words(f"{tarurl}/{tarsrc}"))
            if os.path.isfile(local):
                elog("using", "local", "archive", *words(local))
                do_download = 0

    _rm_f(tmp_sha1)
    return do_download


#  an item of the archive-sha256 hook: "<sha256>  <file>" (sha256sum, the
#  binary marker * accepted)
SHA256_LINE = re.compile(r"^([0-9A-Fa-f]{64})\s+\*?(\S(?:.*\S)?)\s*$")


def parse_sha256(item: str) -> tuple[str, str] | None:
    """(sha256, file) of an archive-sha256 item, None when invalid."""
    m = SHA256_LINE.match(item.strip())
    return (m.group(1).lower(), m.group(2)) if m else None


def expected_sha256(builder, module: str, variant: str, version: str, file: str) -> str | None:
    """The SHA-256 of ``file`` given by the archive-sha256 hook of the
    module, None when not given."""
    d = builder.d
    try:
        values = d.runner().variant_values(module, variant, "archive-sha256", [], d.plan,
                                           builder.modules_list)
    except Exception:  # noqa: BLE001 - reported by scbi lint
        return None
    for line in "\n".join(values).splitlines():
        entry = parse_sha256(line)
        if entry is not None and entry[1] == file:
            return entry[0]
    return None


#  the archive checked last (expected SHA-256, file, size, time): not
#  hashed again while they do not change
_CHECKED = "archive-sha256-checked"


def verify_sha256(builder, module: str, variant: str, version: str, archives: str, tarsrc: str,
                  mdir: str, elog, downloadable: bool) -> bool:
    """Checks the archive against the SHA-256 of the plug-in (true without
    one). On a mismatch the sources extracted are removed and, when it can
    be downloaded again, the archive is renamed <file>.bad (a local
    archive, the only copy, is kept)."""
    expected = expected_sha256(builder, module, variant, version, tarsrc)
    if expected is None:
        return True
    path = os.path.join(archives, tarsrc)
    try:
        st = os.stat(path)
    except OSError:
        return True
    stamp = f"{expected} {tarsrc} {st.st_size} {st.st_mtime_ns}\n"
    checked = os.path.join(mdir, _CHECKED)
    try:
        with open(checked) as f:
            if f.read() == stamp:
                return True
    except OSError:
        pass
    actual = file_sha256(path)
    if actual == expected:
        with contextlib.suppress(OSError):
            os.makedirs(mdir, exist_ok=True)
            with open(checked, "w") as f:
                f.write(stamp)
        return True
    elog("archive", *words(tarsrc), "SHA-256", "mismatch", f"(expected {expected},", f"got {actual})")
    if downloadable:
        #  not used again: downloaded at the next run
        with contextlib.suppress(OSError):
            os.replace(path, f"{path}.bad")
    for name in ("archive-src", "archive", "archive-sha1", _CHECKED):
        _rm_rf(os.path.join(mdir, name))
    return False


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha1_value(path: str) -> str | None:
    """The SHA-1 of a ``.sha1`` file (``sha1sum`` output: its first word),
    None when not a SHA-1 (missing file, error page...)."""
    try:
        with open(path, "rb") as f:
            first = f.read(4096).split(maxsplit=1)
    except OSError:
        return None
    if not first:
        return None
    value = first[0].decode("ascii", errors="replace").lower()
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else None


def _local_archive_ok(archive: str, sha1: str) -> bool:
    """The local archive is there and matches its local SHA-1 (if any)."""
    if not os.path.isfile(archive):
        return False
    if not os.path.exists(sha1):
        return True
    expected = _sha1_value(sha1)
    if expected is None:
        return False
    h = hashlib.sha1()
    try:
        with open(archive, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return False
    return h.hexdigest() == expected


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
