import io
import re


from scbi.log import Logger, printf_format

TS = re.compile(r"^\d{4}/\d\d/\d\d \d\d:\d\d:\d\d", re.M)


def test_printf_format():
    assert printf_format("a\\tb%%\\n") == "a\tb%\n"
    assert printf_format("%s-%s|", ("x",)) == "x-|"
    assert printf_format("<%s>", ("a", "b")) == "<a><b>"
    assert printf_format("%d %5s|", ()) == "0      |"


def make(tmp_path, quiet=False, colors=None):
    (tmp_path / "logs" / "today").mkdir(parents=True, exist_ok=True)
    out, err = io.StringIO(), io.StringIO()
    log = Logger(tmp_path / "logs", "today", "tgt", tmp_path / "sep", quiet=quiet,
                 colors=colors or {}, stdout=out, stderr=err, tty=lambda: None)
    return log, out, err


def test_ilog_elog_line_sep(tmp_path):
    log, out, err = make(tmp_path)
    log.ilog("m", "Building", "%Bm%c", "(100%)")
    log.line_sep()
    log.line_sep()
    log.elog("m", "config", "failed")
    assert TS.sub("TS", out.getvalue()) == "TS : Building m (100%)\n\n"
    assert TS.sub("TS", err.getvalue()) == "TS : m (FAILED) config failed\n"
    report = (tmp_path / "logs" / "today" / "tgt-m-report.log").read_text()
    assert TS.sub("TS", report) == "TS : Building m (100%)\nTS : config failed\n"


MESSAGES = [
    ["Building", "lib1", "[default]", "(master)"],
    ["%Bbold%c", "%rred%c", "%gok%c", "%bblue%c", "%ttext%c"],
    ["100%", "done", "%s", "%d", "%%"],
    ["tab\\there", "new\\nline", "back\\\\slash", "\\e[0m"],
    ["  ↳ dep"],
]

COLORS = {"CBOLD": "\x1b[1m", "CTEXT": "\x1b[37m", "CRED": "\x1b[31m",
          "CGREEN": "\x1b[32m", "CBLUE": "\x1b[34m", "CCLEAR": "\x1b[0m"}

TEMPLATE = r"""
SCBI_LOGS=$PWD/logs-$BASHPID; TODAY=today; SCBI_TARGET=tgt
mkdir -p $SCBI_LOGS/$TODAY
SCBI_LINE_SEP=$PWD/sep-$BASHPID; echo -n 1 > $SCBI_LINE_SEP
DO_QUIET=$2
if [[ $3 == yes ]]; then
  SCBI_CBOLD=$'\e[1m' SCBI_CTEXT=$'\e[37m' SCBI_CRED=$'\e[31m'
  SCBI_CGREEN=$'\e[32m' SCBI_CBLUE=$'\e[34m' SCBI_CCLEAR=$'\e[0m'
else
  SCBI_CBOLD= SCBI_CTEXT= SCBI_CRED= SCBI_CGREEN= SCBI_CBLUE= SCBI_CCLEAR=
fi
eval "set -- $1"
{
  ilog mod "$@"; line-sep; line-sep; elog mod "$@"; dlog mod "$@"; ilog mod "$@"; clog mod
} 2>&1
printf '\x1e'
cat $SCBI_LOGS/$TODAY/tgt-mod-report.log
printf '\x1e%s' "$(< $SCBI_LINE_SEP)"
"""


# ------------------------------------------------------------ statistics

REPORT_A = """2024/01/02 10:00:00 : Building lib1 [default] (master)
2024/01/02 10:00:00 : native x86_64-linux-gnu
2024/01/02 10:01:05 : End Building lib1 [default] (master)
2024/01/02 10:02:00 : Building app [default] (master)
2024/01/02 10:12:30 : End Building app [default] (master)
"""
REPORT_B = """2024/01/03 09:00:00 : Building lib1 [default] (master)
2024/01/03 09:00:20 : End Building lib1 [default] (master)
2024/01/03 09:00:20 : End Building other [default] (master)
2024/01/03 09:30:00 : Building my-lib_2 [v1] (1.0)
2024/01/03 09:30:07 : End Building my-lib_2 [v1] (1.0)
"""


def test_status_line():
    import io

    from scbi.log import Progress, StatusLine, StatusStream

    erase = "\r\x1b[K\x1b[1A\r\x1b[K"
    term = io.StringIO()
    status = StatusLine(term)
    out = StatusStream(term, status)
    progress = Progress(status, total=3)
    progress.next("c-gmp")
    #  an empty line, then the progress
    assert term.getvalue() == "\n[1/3] c-gmp\r"
    out.write("2026/11/16 : Building c-gmp\n")
    #  both erased, the line written, drawn again
    assert term.getvalue() == f"\n[1/3] c-gmp\r{erase}2026/11/16 : Building c-gmp\n\n[1/3] c-gmp\r"
    out.write("partial")
    assert term.getvalue().endswith(f"{erase}partial")
    #  not at the start of a line: not drawn (it could not be erased)
    progress.next("c-mpfr")
    assert term.getvalue().endswith(f"{erase}partial")
    out.write(" end\n")
    assert term.getvalue().endswith(" end\n\n[2/3] c-mpfr\r")
    progress.next("c-mpc")
    progress.next("c-gcc")  # more modules than expected: the total follows
    assert term.getvalue().endswith("\n[4/4] c-gcc\r")
    progress.close()
    assert term.getvalue().endswith(f"[4/4] c-gcc\r{erase}")
    #  disabled: nothing written
    Progress().next("x")


def test_status_bar():
    import io

    from scbi.log import Progress, StatusBar, StatusStream

    now = [100.0]
    term = io.StringIO()
    bar = StatusBar(term, clock=lambda: now[0])
    out = StatusStream(term, bar)
    bar.begin(timer=False)
    rows = bar.rows
    #  the scroll region excludes the last row, the bar drawn on it
    assert term.getvalue().startswith(f"\n\x1b7\x1b[1;{rows - 1}r\x1b8\x1b[1A")
    #  the whole width (80: not a terminal), the elapsed time on the right
    width = bar.width()
    assert term.getvalue().endswith(
        f"\x1b7\x1b[{rows};1H\x1b[2K\x1b[7m{'  elapsed 0s ':>{width}}\x1b[0m\x1b8")
    now[0] += 192
    Progress(bar, total=2).next("c-gmp")
    line = bar.line()
    assert len(line) == width and line.startswith(" [1/2] c-gmp ") and line.endswith("  elapsed 3m12s ")
    assert term.getvalue().endswith(f"\x1b[7m{line}\x1b[0m\x1b8")
    #  the elapsed time at the same place whatever the progress text; a
    #  long text cut before it
    bar.set("[2/2] " + "m" * 200)
    assert len(bar.line()) == width and bar.line().endswith("m  elapsed 3m12s ")
    bar.set("[2/2] c")
    assert bar.line().index("elapsed") == line.index("elapsed")
    #  narrower than the elapsed time: its end only
    bar.width = lambda: 10
    assert bar.line() == "sed 3m12s "
    #  the output is written as is (it scrolls above the bar)
    size = len(term.getvalue())
    out.write("a line\n")
    assert term.getvalue()[size:] == "a line\n"
    now[0] += 3600
    assert bar.elapsed() == "1h03m12s"
    bar.clear()
    assert term.getvalue().endswith(f"\x1b7\x1b[r\x1b[{rows};1H\x1b[2K\x1b8")


def test_report_plain_and_raw(tmp_path):
    #  the colors on the console only; tee on the report log not doubled
    log, out, _ = make(tmp_path, colors={"CBOLD": "<B>", "CCLEAR": "</B>"})
    report = tmp_path / "logs" / "today" / "tgt-m-report.log"
    log.ilog("m", "%Bm%c", "built", tee=str(report))
    log.elog("m", "%Bm%c", "failed")
    log.dlog("m", "%Bm%c", "detail")
    assert TS.sub("TS", out.getvalue()) == "TS : <B>m</B> built\n"
    assert TS.sub("TS", report.read_text()) == "TS : m built\nTS : m failed\nTS :   m detail\n"
    #  raw: as given (no color codes, no printf escapes)
    line = log.ilog_raw("m", "    50% done \\n %B")
    assert TS.sub("TS", line) == "TS :     50% done \\n %B\n"
    assert report.read_text().endswith(line)
    assert out.getvalue().endswith(line)
    quiet, qout, _ = make(tmp_path, quiet=True)
    quiet.ilog_raw("m", "  q")
    assert qout.getvalue() == "" and report.read_text().endswith(" :   q\n")
