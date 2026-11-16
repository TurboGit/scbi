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

    term = io.StringIO()
    status = StatusLine(term)
    out = StatusStream(term, status)
    progress = Progress(status, total=3)
    progress.next("c-gmp")
    assert term.getvalue() == "[1/3] c-gmp\r"
    out.write("2026/11/16 : Building c-gmp\n")
    #  erased, the line written, the status drawn again
    assert term.getvalue() == "[1/3] c-gmp\r\r\x1b[K2026/11/16 : Building c-gmp\n[1/3] c-gmp\r"
    out.write("partial")
    assert term.getvalue().endswith("\r\x1b[Kpartial")
    progress.next("c-mpfr")
    progress.next("c-mpc")
    progress.next("c-gcc")  # more modules than expected: the total follows
    assert term.getvalue().endswith("[4/4] c-gcc\r")
    progress.close()
    assert term.getvalue().endswith("[4/4] c-gcc\r\r\x1b[K")
    #  disabled: nothing written
    Progress().next("x")
