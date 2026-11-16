"""Logging (port of scripts.d/2_log: c-log-message, ilog, dlog, elog, clog,
line-sep).

Messages go to the console and to the module report log
``$SCBI_LOGS/$TODAY/$SCBI_TARGET-<module>-report.log``. As in Bash the
message is used as a printf format: ``%`` directives (without arguments)
and backslash escapes are interpreted. The "line separator" state is kept
in the file SCBI_LINE_SEP shared with the hook shells (they log with the
Bash runtime functions).
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

COLOR_CODES = {"%B": "CBOLD", "%t": "CTEXT", "%r": "CRED", "%g": "CGREEN", "%b": "CBLUE", "%c": "CCLEAR"}

_ESCAPES = {
    "\\": "\\", "a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f",
    "n": "\n", "r": "\r", "t": "\t", "v": "\v", '"': '"', "'": "'", "?": "?",
}


def printf_format(fmt: str, args: tuple[str, ...] = ()) -> str:
    """Bash ``printf FORMAT ARGS...`` (enough of it for log messages).

    Escapes are interpreted; ``%s`` ``%b`` ``%d``... consume the arguments
    (missing ones: empty string or 0); the format is reused while arguments
    remain.
    """
    out: list[str] = []
    args_l = list(args)
    i_arg = 0

    def once() -> None:
        nonlocal i_arg
        i, n = 0, len(fmt)
        while i < n:
            c = fmt[i]
            if c == "\\" and i + 1 < n:
                e = fmt[i + 1]
                if e in _ESCAPES:
                    out.append(_ESCAPES[e])
                    i += 2
                elif e in "01234567":
                    j = i + 1
                    while j < n and j < i + 4 and fmt[j] in "01234567":
                        j += 1
                    out.append(chr(int(fmt[i + 1 : j], 8)))
                    i = j
                elif e == "x":
                    j = i + 2
                    while j < n and j < i + 4 and fmt[j] in "0123456789abcdefABCDEF":
                        j += 1
                    out.append(chr(int(fmt[i + 2 : j], 16)) if j > i + 2 else "\\x")
                    i = j
                else:
                    out.append("\\" + e)
                    i += 2
            elif c == "%" and i + 1 < n:
                if fmt[i + 1] == "%":
                    out.append("%")
                    i += 2
                    continue
                j = i + 1
                while j < n and fmt[j] in "-+ #0123456789.*":
                    j += 1
                if j >= n:
                    out.append(fmt[i:])
                    break
                conv, spec = fmt[j], fmt[i + 1 : j]
                arg = args_l[i_arg] if i_arg < len(args_l) else None
                i_arg += 1
                if conv in "sbq":
                    text = arg or ""
                    if conv == "b":
                        text = printf_format(text.replace("%", "%%"))
                    width = spec.lstrip("-")
                    if width.isdigit():
                        text = text.ljust(int(width)) if spec.startswith("-") else text.rjust(int(width))
                    out.append(text)
                elif conv in "diouxXc":
                    try:
                        v = int(arg or "0")
                    except ValueError:
                        v = 0
                    out.append(("%" + spec + ("d" if conv in "iu" else conv)) % v if conv != "c" else (arg or "")[:1])
                elif conv in "feEgG":
                    try:
                        v = float(arg or "0")
                    except ValueError:
                        v = 0.0
                    out.append(("%" + spec + conv) % v)
                else:
                    out.append(fmt[i : j + 1])
                i = j + 1
            else:
                out.append(c)
                i += 1

    once()
    while i_arg < len(args_l):
        once()
    return "".join(out)


@dataclass
class Logger:
    logs: Path  # SCBI_LOGS
    today: str  # TODAY
    target: str  # SCBI_TARGET
    line_sep_file: Path  # SCBI_LINE_SEP
    quiet: bool = False  # DO_QUIET
    colors: dict[str, str] = field(default_factory=dict)  # CBOLD... -> escape
    stdout: TextIO = sys.stdout
    stderr: TextIO = sys.stderr
    #  dlog: written to the terminal when there is one (/dev/tty)
    tty: Callable[[], TextIO | None] | None = None
    clock: Callable[[], float] = time.time

    def report(self, module: str) -> Path:
        return self.logs / self.today / f"{self.target}-{module}-report.log"

    def _append(self, module: str, text: str) -> None:
        path = self.report(module)
        try:
            with open(path, "a") as f:
                f.write(text)
        except OSError:
            #  Bash prints an error for a missing log directory and goes on
            print(f"scbi: {path}: No such file or directory", file=self.stderr)

    def _ts(self) -> str:
        return time.strftime("%Y/%m/%d %H:%M:%S", time.localtime(self.clock()))

    def _set_sep(self, value: str) -> None:
        try:
            self.line_sep_file.write_text(value)
        except OSError:
            pass

    def message(self, *words: str) -> str:
        """Port of ``c-log-message``: color codes replaced."""
        msg = " ".join(words)
        for code, name in COLOR_CODES.items():
            msg = msg.replace(code, self.colors.get(name, ""))
        return msg

    def ilog(self, module: str, *words: str, tee: str | None = None) -> None:
        """``tee``: ``ilog ... | tee -a FILE``, the console line is also
        appended to FILE."""
        ts, msg = self._ts(), self.message(*words)
        line = printf_format(f"{ts} : {msg}\n")
        if not self.quiet:
            self.stdout.write(line)
            self.stdout.flush()
            if tee:
                with open(tee, "a") as f:
                    f.write(line)
        self._append(module, line)
        self._set_sep("0")

    def dlog(self, module: str, *words: str) -> None:
        ts, msg = self._ts(), self.message(*words)
        line = printf_format(f"{ts} :   {msg}\n")
        out = self.tty() if self.tty else _open_tty()
        if out is not None:
            out.write(line)
            out.flush()
        self._append(module, line)
        self._set_sep("0")

    def elog(self, module: str, *words: str) -> None:
        ts, msg = self._ts(), self.message(*words)
        c = self.colors
        line = printf_format(
            f"{ts} : %s{module}%s %s(FAILED)%s {msg}\n",
            tuple(x for x in (c.get("CBOLD", "") + c.get("CTEXT", ""), c.get("CCLEAR", ""),
                              c.get("CRED", ""), c.get("CCLEAR", ""))),
        )
        self.stderr.write(line)
        self.stderr.flush()
        self._append(module, printf_format(f"{ts} : {msg}\n"))
        self._set_sep("0")

    def clog(self, module: str) -> None:
        self._append(module, "\n")

    def line_sep(self) -> None:
        """Port of ``line-sep``: an empty line after some log messages."""
        try:
            sep = self.line_sep_file.read_text()
        except OSError:
            sep = ""
        if sep == "0" and not self.quiet:
            self.stdout.write("\n")
            self.stdout.flush()
        self._set_sep("1")


def _open_tty() -> TextIO | None:
    try:
        fd = os.open("/dev/tty", os.O_WRONLY | os.O_NOCTTY)
    except OSError:
        return None
    return os.fdopen(fd, "w")


# ---------------------------------------------------------------- statistics

def _epoch(date: str, clock: str) -> int | None:
    """``date +%s --date="DATE TIME"`` (local time)."""
    import time

    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return int(time.mktime(time.strptime(f"{date} {clock}", fmt)))
        except ValueError:
            pass
    return None


def log_stat_file(path: Path) -> list[tuple[str, int]]:
    """Port of ``compute-log-stat-file``: (module, duration) of each
    Building ... End Building pair of a report log."""
    result = []
    start = 0
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return result
    for line in lines:
        f = (line.split() + [""] * 6)[:6]
        date, clock, _x, action, _word, mod = f
        if "Building" in action:
            start = _epoch(date, clock) or 0
        elif action == "End" and start != 0:
            end = _epoch(date, clock) or 0
            result.append((mod, end - start))
            start = 0
    return result


def display_log_stat(logs: Path, module: str = "") -> str:
    """Port of ``display-log-stat``: min, average and max build time of
    each module from the report logs, sorted as ``sort`` does."""
    import subprocess
    import time

    stats: dict[str, list[int]] = {}
    for path in sorted(Path(logs).rglob(f"*{module}-report.log")):
        for mod, duration in log_stat_file(path):
            stats.setdefault(mod, []).append(duration)

    def mmss(seconds: int) -> str:
        return time.strftime("%M:%S", time.localtime(seconds))

    rows = []
    for key, values in stats.items():
        avg = abs(sum(values)) // len(values) * (1 if sum(values) >= 0 else -1)
        rows.append(f"{key:<55} : {mmss(min(min(values), 999999))}   {mmss(avg)}   {mmss(max(max(values), 0))}\n")
    text = "".join(rows)
    if text:
        text = subprocess.run(["sort"], input=text, capture_output=True, text=True).stdout
    return "\nbuild times (min, average, max):\n\n" + text + "\n"


# ------------------------------------------------------------- progress


class StatusLine:
    """A transient last line of the terminal (the build progress): every
    write to the console first erases it, it is drawn again after a
    complete line. The text is followed by a carriage return so that the
    output of a sub-process writing to the terminal starts on it."""

    ERASE = "\r\x1b[K"

    def __init__(self, stream: TextIO):
        self.stream = stream
        self.text = ""
        self.shown = False

    def width(self) -> int:
        try:
            columns = os.get_terminal_size(self.stream.fileno()).columns
        except (OSError, ValueError, AttributeError):
            columns = 0
        #  unknown size (some pseudo-terminals report 0)
        return columns if columns >= 20 else 80

    def erase(self) -> None:
        if self.shown:
            self.stream.write(self.ERASE)
            self.shown = False

    def draw(self) -> None:
        if self.text and not self.shown:
            self.stream.write(self.text[: max(self.width() - 1, 1)] + "\r")
            self.stream.flush()
            self.shown = True

    def set(self, text: str) -> None:
        self.erase()
        self.text = text
        self.draw()

    def clear(self) -> None:
        self.erase()
        self.text = ""
        self.stream.flush()


class StatusStream:
    """A console stream writing through a StatusLine."""

    def __init__(self, stream: TextIO, status: StatusLine):
        self._stream = stream
        self._status = status

    def write(self, text: str) -> int:
        if not text:
            return 0
        self._status.erase()
        n = self._stream.write(text)
        if text.endswith("\n"):
            self._stream.flush()
            self._status.draw()
        return n

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


class Progress:
    """``[n/N] module`` on a StatusLine while the driver builds; does
    nothing when disabled (not a terminal...)."""

    def __init__(self, status: StatusLine | None = None, total: int = 0):
        self.status = status
        self.total = total
        self.count = 0

    def next(self, name: str) -> None:
        self.count += 1
        if self.status is None:
            return
        self.total = max(self.total, self.count)
        self.status.set(f"[{self.count}/{self.total}] {name}")

    def close(self) -> None:
        if self.status is not None:
            self.status.clear()
