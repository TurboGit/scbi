import io
import re

import pytest

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


@pytest.mark.oracle
def test_log_oracle(oracle, tmp_path):
    from oracle import _bash_quote

    cases = [(" ".join(_bash_quote(w) for w in msg), q, c)
             for msg in MESSAGES for q in ("no", "yes") for c in ("no", "yes")]
    outputs = oracle.batch(TEMPLATE, cases)
    for i, ((_, quiet, colors), msg, out) in enumerate(zip(cases, [m for m in MESSAGES for _ in range(4)], outputs)):
        d = tmp_path / str(i)
        log, o, e = make(d, quiet == "yes", COLORS if colors == "yes" else {})
        merged = io.StringIO()
        log.stdout = log.stderr = merged
        log.line_sep_file.write_text("1")
        log.ilog("mod", *msg)
        log.line_sep()
        log.line_sep()
        log.elog("mod", *msg)
        log.dlog("mod", *msg)
        log.ilog("mod", *msg)
        log.clog("mod")
        console, report, sep = out.split("\x1e")
        assert TS.sub("TS", merged.getvalue()) == TS.sub("TS", console), msg
        assert TS.sub("TS", log.report("mod").read_text()) == TS.sub("TS", report), msg
        assert log.line_sep_file.read_text() == sep


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


@pytest.mark.oracle
def test_display_log_stat_same_as_bash(oracle, tmp_path):
    from scbi.log import display_log_stat

    logs = tmp_path / "logs"
    (logs / "2024_01_02").mkdir(parents=True)
    (logs / "2024_01_03").mkdir()
    (logs / "2024_01_02" / "x86_64-linux-gnu-app-report.log").write_text(REPORT_A)
    (logs / "2024_01_03" / "x86_64-linux-gnu-lib1-report.log").write_text(REPORT_B)
    (logs / "2024_01_03" / "x86_64-linux-gnu-lib1-env.log").write_text(REPORT_A)
    expected = oracle.call(f"SCBI_LOGS={logs}\nSCBI_JOBS=2\ndisplay-log-stat")
    assert display_log_stat(logs) == expected
    assert "lib1" in expected
