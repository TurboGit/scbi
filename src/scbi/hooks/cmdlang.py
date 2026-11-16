"""The command language of the command hooks of plug-in definitions (config,
build, install, setup, wrapup, tests, version, run, pre-/post- steps and
the plug-in functions).

No shell is involved: the driver parses the body and runs it. External
commands are launched as subprocesses (argument list, the hook
environment); built-ins are Python functions.

A body is a text block, one step per line (``#`` comments, blank lines
ignored, a trailing ``\\`` continues a line). Blocks are given by
indentation::

    if <condition>:          the guard language (scbi.plugin.expr) with
        ...                  is-dir(p) is-file(p) is-link(p) empty(v)
    elif <condition>:        ok("<command line>") status
        ...
    else:
        ...
    for NAME in <words>:
        ...
    write FILE:              the indented text, expanded ($VAR), to FILE
        ...                  (append FILE: adds to it, write-raw FILE: and
                             append-raw FILE: do not expand)

Steps:

- a command line: words split as by the shell (quotes, backslash),
  expanded by Python (``$V``, ``${V}``, ``${V%p}``, ``${V%%p}``,
  ``${V#p}``, ``${V##p}``, ``${V:-d}``, ``$(builtin args)``), unquoted
  glob patterns expanded; a list variable gives several words, scalar
  values are not split, an unquoted word expanding to nothing is
  removed. Leading ``NAME=value`` words set the environment of the
  command. ``&&``, ``||``, pipes ``|`` and redirections (``>``, ``>>``,
  ``<``, ``2>``, ``2>>``, ``2>&1``, ``&>``) as in the shell;
- ``VAR = value...`` or ``VAR = <function> args...``: a variable of the
  hook (``export VAR = ...``: also in the environment of the commands);
  one word gives a scalar, several a list;
- built-in commands: ``cd``, ``echo``, ``return [N]``, ``exit [N]``,
  ``true``, ``false``, ``export NAME``, ``unset NAME``, ``copy`` and the
  plug-in functions.

The status of a body is the status of its last step (as Bash): a failing
step does not stop it, unless chained with ``&&``.
"""

from __future__ import annotations

import errno
import glob as _glob
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

from scbi.bashenv import quote
from scbi.hooks import builtins as _builtins
from scbi.hooks.context import HookContext
from scbi.hooks.expand import ExpandError, _split_if, expand
from scbi.plugin import expr
from scbi.plugin.model import BUILTINS
from scbi.vercmp import check_versions

#  Functions usable in an assignment (VAR = <function> args)
FUNCTIONS = (
    "get-build-type", "config-options", "last-modified-directory", "is-enabled", "get-version",
    "output", "output-words", "first-line", "status", "basename", "dirname", "command-path",
    "all-variants", "uppercase", "lowercase", "replace", "if", "all-modules", "hook-output",
)
#  Built-in commands
COMMANDS = ("cd", "echo", "return", "exit", "true", "false", ":", "export", "unset",
            "check-versions", "copy", "delete", "delete-tree")

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ASSIGN = re.compile(r"^(export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+=(?:\s+(.*)|\s*)$")
_ENV_WORD = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)
_HEADER = re.compile(r"^(if|elif)\s+(.+):$|^else\s*:$|^for\s+([A-Za-z_]\w*)\s+in\s+(.*):$|"
                     r"^(write|append|write-raw|append-raw)\s+(.+):$")
_GLOB = re.compile(r"[*?\[]")


def _xq(word: str) -> str:
    """A word as Bash xtrace shows it (quoted only when needed)."""
    return word if re.fullmatch(r"[\w@%+=:,./-]+", word) else quote(word)


class CmdSyntaxError(Exception):
    def __init__(self, line: int, message: str):
        super().__init__(f"line {line}: {message}")
        self.line = line
        self.message = message


# ----------------------------------------------------------------- AST


@dataclass(frozen=True)
class Word:
    #  (text, quote) with quote "" (unquoted, expanded, globbed), '"'
    #  (expanded) or "'" (literal)
    parts: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Redirect:
    op: str  # ">" ">>" "<" "2>" "2>>" "2>&1" "&>"
    target: Word | None


@dataclass(frozen=True)
class Simple:
    words: tuple[Word, ...]
    redirects: tuple[Redirect, ...]


@dataclass(frozen=True)
class Pipeline:
    commands: tuple[Simple, ...]


@dataclass(frozen=True)
class AndOr:
    line: int
    first: Pipeline
    rest: tuple[tuple[str, Pipeline], ...]  # ("&&" | "||", pipeline)


@dataclass(frozen=True)
class Assign:
    line: int
    name: str
    export: bool
    words: tuple[Word, ...]
    text: str  # right-hand side as written (for "output <command line>")


@dataclass(frozen=True)
class If:
    line: int
    branches: tuple[tuple[str, tuple], ...]  # (condition, body)
    orelse: tuple | None


@dataclass(frozen=True)
class For:
    line: int
    name: str
    words: tuple[Word, ...]
    body: tuple


@dataclass(frozen=True)
class Write:
    line: int
    path: Word
    text: str
    append: bool
    raw: bool


# ------------------------------------------------------------- tokenizer

_OPERATORS = ("2>&1", "2>>", "&>", "&&", "||", ">>", "2>", ">", "<", "|")


def tokenize(text: str, line: int = 0) -> list:
    """Words (Word) and operators (str) of a command line."""
    tokens: list = []
    parts: list[tuple[str, str]] = []
    cur: list[str] = []
    in_word = False
    i, n = 0, len(text)

    def flush_part(quote: str = "") -> None:
        if cur:
            parts.append(("".join(cur), quote))
            cur.clear()

    def end_word() -> None:
        nonlocal in_word
        flush_part()
        if in_word:
            tokens.append(Word(tuple(parts)))
        parts.clear()
        in_word = False

    while i < n:
        c = text[i]
        if c in " \t":
            end_word()
            i += 1
            continue
        op = next((o for o in _OPERATORS if text.startswith(o, i)), None)
        #  "2>" is an operator only at the start of a word
        if op and (not op.startswith("2") or not in_word):
            end_word()
            tokens.append(op)
            i += len(op)
            continue
        if c == "#" and not in_word:
            break
        in_word = True
        if c == "\\" and i + 1 < n:
            flush_part()
            parts.append((text[i + 1], "'"))
            i += 2
        elif c == "'":
            j = text.find("'", i + 1)
            if j < 0:
                raise CmdSyntaxError(line, f"unterminated quote in {text!r}")
            flush_part()
            parts.append((text[i + 1:j], "'"))
            i = j + 1
        elif c == '"':
            flush_part()
            j, buf = i + 1, []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n and text[j + 1] in '"\\$`':
                    #  escaped: a literal part (not expanded)
                    if buf:
                        parts.append(("".join(buf), '"'))
                        buf = []
                    parts.append((text[j + 1], "'"))
                    j += 2
                    continue
                if text.startswith("$(", j):
                    depth, k = 0, j + 1
                    while k < n:
                        depth += text[k] == "("
                        depth -= text[k] == ")"
                        if depth == 0:
                            break
                        k += 1
                    buf.append(text[j:k + 1])
                    j = k + 1
                    continue
                buf.append(text[j])
                j += 1
            if j >= n:
                raise CmdSyntaxError(line, f"unterminated quote in {text!r}")
            #  an empty "" still makes a (quoted) word
            if buf or not parts or parts[-1][1] != "'":
                parts.append(("".join(buf), '"'))
            i = j + 1
        elif text.startswith("$(", i):
            depth, k = 0, i + 1
            while k < n:
                depth += text[k] == "("
                depth -= text[k] == ")"
                if depth == 0:
                    break
                k += 1
            if k >= n:
                raise CmdSyntaxError(line, f"unterminated $( in {text!r}")
            cur.append(text[i:k + 1])
            i = k + 1
        elif text.startswith("${", i):
            k = text.find("}", i)
            if k < 0:
                raise CmdSyntaxError(line, f"unterminated ${{ in {text!r}")
            cur.append(text[i:k + 1])
            i = k + 1
        else:
            cur.append(c)
            i += 1
    end_word()
    return tokens


def _command_line(text: str, line: int) -> AndOr:
    tokens = tokenize(text, line)
    if not tokens:
        raise CmdSyntaxError(line, "empty command")
    pipelines: list[tuple[str, Pipeline]] = []
    commands: list[Simple] = []
    words: list[Word] = []
    redirects: list[Redirect] = []
    connector = ""
    i = 0

    def end_simple() -> None:
        if not words and not redirects:
            raise CmdSyntaxError(line, f"missing command in {text!r}")
        commands.append(Simple(tuple(words), tuple(redirects)))
        words.clear()
        redirects.clear()

    def end_pipeline(next_connector: str) -> None:
        nonlocal connector
        end_simple()
        pipelines.append((connector, Pipeline(tuple(commands))))
        commands.clear()
        connector = next_connector

    while i < len(tokens):
        t = tokens[i]
        if isinstance(t, Word):
            words.append(t)
        elif t in ("&&", "||"):
            end_pipeline(t)
        elif t == "|":
            end_simple()
        elif t == "2>&1":
            redirects.append(Redirect(t, None))
        else:
            if i + 1 >= len(tokens) or not isinstance(tokens[i + 1], Word):
                raise CmdSyntaxError(line, f"missing file after {t} in {text!r}")
            redirects.append(Redirect(t, tokens[i + 1]))
            i += 1
        i += 1
    end_pipeline("")
    (_, first), *rest = pipelines
    return AndOr(line, first, tuple(rest))


# --------------------------------------------------------------- parser


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _logical_lines(text: str, first_line: int) -> list[tuple[int, int, str]]:
    """(line number, indent, text) of the non-blank lines, continuations
    joined, comments kept for write blocks (stripped later)."""
    result = []
    raw = text.split("\n")
    i = 0
    while i < len(raw):
        line = raw[i]
        number = first_line + i
        if "\t" in line[: _indent(line) + 1] and line.strip():
            raise CmdSyntaxError(number, "tabs are not allowed for indentation")
        while line.endswith("\\") and i + 1 < len(raw):
            i += 1
            line = line[:-1] + " " + raw[i].strip()
        result.append((number, _indent(line), line))
        i += 1
    return result


def parse(text: str, first_line: int = 1) -> tuple:
    """The steps of a body (``first_line``: line of its first line, for
    the messages)."""
    lines = _logical_lines(text, first_line)
    body, pos = _block(lines, 0, 0)
    while pos < len(lines) and not lines[pos][2].strip():
        pos += 1
    if pos < len(lines):
        raise CmdSyntaxError(lines[pos][0], "unexpected indentation")
    return body


def _is_blank(text: str) -> bool:
    s = text.strip()
    return not s or s.startswith("#")


def _block(lines, pos: int, indent: int) -> tuple[tuple, int]:
    steps: list = []
    while pos < len(lines):
        number, ind, text = lines[pos]
        if _is_blank(text):
            pos += 1
            continue
        if ind < indent:
            break
        if ind > indent:
            raise CmdSyntaxError(number, "unexpected indentation")
        s = text.strip()
        m = _HEADER.match(s)
        if m and (m.group(1) == "elif" or s.startswith("else")):
            raise CmdSyntaxError(number, f"'{s.split()[0].rstrip(':')}' without 'if'")
        if m and m.group(5):
            #  write FILE: + indented text
            kind = m.group(5)
            pos += 1
            block: list[tuple[int, str]] = []
            while pos < len(lines) and (not lines[pos][2].strip() or lines[pos][1] > indent):
                block.append((lines[pos][1], lines[pos][2]))
                pos += 1
            while block and not block[-1][1].strip():
                block.pop()
            margin = min((b[0] for b in block if b[1].strip()), default=0)
            content = "".join(b[1][margin:] + "\n" for b in block)
            words = tokenize(m.group(6), number)
            if len(words) != 1 or not isinstance(words[0], Word):
                raise CmdSyntaxError(number, f"{kind}: a single file name is expected")
            steps.append(Write(number, words[0], content, kind.startswith("append"), kind.endswith("raw")))
            continue
        if m and (m.group(1) == "if" or m.group(3)):
            body, pos = _sub_block(lines, pos + 1, indent, number)
            if m.group(3):
                steps.append(For(number, m.group(3), tuple(w for w in tokenize(m.group(4), number)
                                                          if isinstance(w, Word)), body))
                continue
            _check_condition(m.group(2), number)
            branches = [(m.group(2).strip(), body)]
            orelse = None
            while pos < len(lines):
                n2, i2, t2 = lines[pos]
                if _is_blank(t2):
                    pos += 1
                    continue
                m2 = _HEADER.match(t2.strip())
                if i2 != indent or not m2 or not (m2.group(1) == "elif" or t2.strip().startswith("else")):
                    break
                sub, pos = _sub_block(lines, pos + 1, indent, n2)
                if m2.group(1) == "elif":
                    _check_condition(m2.group(2), n2)
                    branches.append((m2.group(2).strip(), sub))
                else:
                    orelse = sub
                    break
            steps.append(If(number, tuple(branches), orelse))
            continue
        a = _ASSIGN.match(s)
        if a:
            rhs = a.group(3) or ""
            words = tuple(w for w in tokenize(rhs, number) if isinstance(w, Word))
            if any(not isinstance(t, Word) for t in tokenize(rhs, number)) and \
                    not (words and _word_text(words[0]) in ("output", "output-words")):
                raise CmdSyntaxError(number, f"operators are only allowed after 'output' in {s!r}")
            if words and _word_text(words[0]) == "if":
                from scbi.hooks.expand import check

                try:
                    check(f"$({rhs.strip()})")
                except ExpandError as e:
                    raise CmdSyntaxError(number, str(e)) from None
            steps.append(Assign(number, a.group(2), bool(a.group(1)), words, rhs))
            pos += 1
            continue
        first = s.split()[0].rstrip(":")
        if first in ("if", "elif", "else", "for", "while", "case", "until"):
            if not s.endswith(":"):
                raise CmdSyntaxError(number, f"missing ':' at the end of {s!r}")
            raise CmdSyntaxError(number, f"invalid block header {s!r}")
        steps.append(_command_line(s, number))
        pos += 1
    return tuple(steps), pos


def _sub_block(lines, pos: int, indent: int, header_line: int) -> tuple[tuple, int]:
    while pos < len(lines) and _is_blank(lines[pos][2]):
        pos += 1
    if pos >= len(lines) or lines[pos][1] <= indent:
        raise CmdSyntaxError(header_line, "an indented block is expected")
    return _block(lines, pos, lines[pos][1])


def _check_condition(cond: str, line: int) -> None:
    try:
        expr.parse(cond)
    except expr.ExprError as e:
        raise CmdSyntaxError(line, str(e)) from None


def _word_text(word: Word) -> str:
    return "".join(t for t, _ in word.parts)


# ----------------------------------------------------------- execution


class _Return(Exception):
    def __init__(self, status: int):
        self.status = status


@dataclass
class State:
    """The state of a hook call."""

    vars: dict[str, str | list[str]]
    env: dict[str, str]
    cwd: str
    out: Callable[[str], None]  # standard output (text)
    err: Callable[[str], None]  # standard error (text)
    status: int = 0


def _copy_file(src: str, dst: str) -> None:
    """A file or symbolic link (kept as a link), replacing ``dst``."""
    if os.path.lexists(dst) and (os.path.islink(dst) or not os.path.isdir(dst)):
        os.unlink(dst)
    shutil.copy(src, dst, follow_symlinks=False)


def _copy_tree(src: str, dst: str) -> None:
    """A directory, recursively, merged into ``dst`` if it exists."""
    if os.path.lexists(dst) and (os.path.islink(dst) or not os.path.isdir(dst)):
        os.unlink(dst)
    os.makedirs(dst, exist_ok=True)
    shutil.copymode(src, dst)
    for entry in os.scandir(src):
        target = os.path.join(dst, entry.name)
        if entry.is_dir(follow_symlinks=False):
            _copy_tree(entry.path, target)
        else:
            _copy_file(entry.path, target)


@dataclass
class Runner:
    """Runs bodies; ``where`` names them in the messages (the plug-in
    file and the hook)."""

    ctx: HookContext  # module, variant, plan, env... of the hook
    where: str
    #  the module's config-options (VAR = config-options)
    config_options: Callable[[], list[str]] = list
    #  plug-in functions: name -> (params, body)
    functions: dict[str, tuple[tuple[str, ...], tuple]] = field(default_factory=dict)
    #  the modules of the build of the module (all-modules): name -> status
    #  (depends-kind, is-meta, is-aggregate, is-aggregated)
    all_modules: Callable[[], dict[str, dict[str, str]]] = dict
    modules_status: dict[str, dict[str, str]] = field(default_factory=dict)
    #  hook-output MODULE HOOK: the function of the hook of another module
    #  ("" if none) and the functions once modules are loaded
    hook_function: Callable[[str, str], str] = lambda module, hook: ""
    #  hook-output MODULE HOOK of a value hook: its values (None: not a
    #  value hook)
    hook_values: Callable[[str, str, list[str]], list[str] | None] = lambda module, hook, args: None
    refresh_functions: Callable[[], dict] | None = None
    #  called with a "_TRACE: ..." line for each command and assignment (as
    #  Bash xtrace does)
    trace: Callable[[str], None] | None = None
    #  line of the step being run (messages of $(function ...) in words)
    line: int = field(default=0, init=False)

    # ------------------------------------------------------------ entry

    def run(self, body: tuple, state: State) -> int:
        try:
            self.block(body, state)
        except _Return as r:
            state.status = r.status
        return state.status

    def block(self, body: tuple, state: State) -> None:
        for step in body:
            self.step(step, state)

    def step(self, step, state: State) -> None:
        saved, self.line = self.line, getattr(step, "line", self.line)
        try:
            self._step(step, state)
        except ExpandError as e:
            self.error(state, self.line, str(e))
            state.status = 1
        finally:
            self.line = saved

    def _step(self, step, state: State) -> None:
        if isinstance(step, AndOr):
            status = self.pipeline(step.first, state, step.line)
            for op, p in step.rest:
                if (op == "&&") == (status == 0):
                    status = self.pipeline(p, state, step.line)
            state.status = status
        elif isinstance(step, Assign):
            self.assign(step, state)
        elif isinstance(step, If):
            for cond, body in step.branches:
                if self.condition(cond, state, step.line):
                    self.block(body, state)
                    return
            if step.orelse is not None:
                self.block(step.orelse, state)
            else:
                state.status = 0
        elif isinstance(step, For):
            values = self.expand_words(step.words, state)
            state.status = 0
            for v in values:
                state.vars[step.name] = v
                self.block(step.body, state)
        elif isinstance(step, Write):
            path = self._path(self.expand_words((step.path,), state, glob=False)[0], state)
            text = step.text if step.raw else self.expand_text(step.text, state, step.line)
            try:
                with open(path, "a" if step.append else "w") as f:
                    f.write(text)
                state.status = 0
            except OSError as e:
                self.error(state, step.line, f"{path}: {e.strerror}")
                state.status = 1

    # -------------------------------------------------------- expansion

    def hook_ctx(self, state: State) -> HookContext:
        import copy

        ctx = copy.copy(self.ctx)
        #  PWD: the current directory of the hook (as cd sets it in Bash)
        ctx.locals = {"PWD": state.cwd,
                      **{k: (" ".join(v) if isinstance(v, list) else v) for k, v in state.vars.items()}}
        ctx.cwd = type(self.ctx.cwd)(state.cwd)
        return ctx

    def expand_text(self, text: str, state: State, line: int) -> str:
        """Expansion of a write block, like a here-document: \\$ \\` and
        \\\\ give the character."""
        try:
            ctx = self.hook_ctx(state)
            pieces = re.split(r"\\([$`\\])", text)
            return "".join(expand(piece, ctx) if k % 2 == 0 else piece for k, piece in enumerate(pieces))
        except ExpandError as e:
            self.error(state, line, str(e))
            return ""

    def expand_words(self, words, state: State, glob: bool = True) -> list[str]:
        out: list[str] = []
        ctx = self.hook_ctx(state)
        for w in words:
            #  "$LIST" / "${LIST}" unquoted: the elements
            if len(w.parts) == 1 and w.parts[0][1] == "":
                m = re.fullmatch(r"\$(?:([A-Za-z_]\w*)|\{([A-Za-z_]\w*)\})", w.parts[0][0])
                if m:
                    value = state.vars.get(m.group(1) or m.group(2))
                    if isinstance(value, list):
                        out += value
                        continue
            #  unquoted $(function ...) alone: a list gives several words
            if len(w.parts) == 1 and w.parts[0][1] == "":
                calls = self._calls(w.parts[0][0])
                if len(calls) == 1 and calls[0][:2] == (0, len(w.parts[0][0])):
                    value = self.call(calls[0][2], state)
                    if isinstance(value, list):
                        out += value
                    elif value:
                        out.append(value)
                    continue
            text, pattern, globbing, quoted = [], [], False, False
            for part, quote in w.parts:
                v = part if quote == "'" else self.expand_part(part, state, ctx)
                text.append(v)
                if quote:
                    quoted = True
                    pattern.append(_glob.escape(v))
                else:
                    pattern.append(v)
                    globbing = globbing or bool(_GLOB.search(v))
            value = "".join(text)
            if not value and not quoted:
                continue
            if glob and globbing:
                matches = sorted(_glob.glob("".join(pattern), root_dir=state.cwd))
                out += matches or [value]
            else:
                out.append(value)
        return out

    @staticmethod
    def _calls(text: str) -> list[tuple[int, int, str]]:
        """(start, end, inner text) of the $(<function> ...) of ``text``
        whose function is an assignment function (the others are expanded
        by scbi.hooks.expand)."""
        calls, i = [], 0
        while (i := text.find("$(", i)) >= 0:
            depth, j = 0, i + 1
            while j < len(text):
                if text[j] == "(":
                    depth += 1
                elif text[j] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j >= len(text):
                break
            inner = text[i + 2 : j]
            name = inner.split(None, 1)[:1]
            if name and name[0] in FUNCTIONS:
                calls.append((i, j + 1, inner))
            i = j + 1
        return calls

    def call(self, inner: str, state: State):
        """The value of ``$(<function> args...)`` in a command word, as
        ``VAR = <function> args...``."""
        try:
            words = tuple(w for w in tokenize(inner, self.line) if isinstance(w, Word))
        except CmdSyntaxError as e:
            self.error(state, self.line, str(e))
            return ""
        return self.function(words[0].parts[0][0], Assign(self.line, "", False, words, inner), state)

    def expand_part(self, part: str, state: State, ctx: HookContext) -> str:
        """Expansion of a part of a word; the $(<function> ...) calls give
        their value (a list joined with spaces)."""
        out, last = [], 0
        for start, end, inner in self._calls(part):
            out.append(expand(part[last:start], ctx))
            value = self.call(inner, state)
            out.append(" ".join(value) if isinstance(value, list) else value or "")
            last = end
        out.append(expand(part[last:], ctx))
        return "".join(out)

    # ------------------------------------------------------- conditions

    def condition(self, cond: str, state: State, line: int) -> bool:
        from scbi.hooks.evaluate import GuardContext

        runner = self

        class _Ctx(GuardContext):
            def variable(self, name):
                if name == "status":
                    return str(state.status)
                return super().variable(name)

            def function(self, name, arg):
                path = runner._path(arg, state)
                if name == "is-dir":
                    return os.path.isdir(path)
                if name == "is-file":
                    return os.path.isfile(path)
                if name == "is-link":
                    return os.path.islink(path)
                if name == "exists":
                    return os.path.lexists(path)
                if name == "empty":
                    return arg == ""
                if name in ("depends-kind", "is-meta", "is-aggregate", "is-aggregated"):
                    status = runner.modules_status.get(arg)
                    if status is None:
                        raise expr.ExprError(f"{name}({arg}): not a module of all-modules")
                    return status[name] if name == "depends-kind" else status[name] == "true"
                if name == "ok":
                    saved = state.status
                    body = parse(arg, line)
                    sink = State(state.vars, state.env, state.cwd, lambda t: None, state.err)
                    status = runner.run(body, sink)
                    state.status = saved
                    return status == 0
                return super().function(name, arg)

        try:
            return expr.evaluate(cond, _Ctx(self.hook_ctx(state)))
        except (expr.ExprError, ExpandError, Exception) as e:  # noqa: BLE001
            self.error(state, line, f"condition {cond!r}: {e}")
            return False

    # ------------------------------------------------------- assignment

    def assign(self, step: Assign, state: State) -> None:
        name = step.words and _word_text(step.words[0])
        quoted = step.words and any(q for _, q in step.words[0].parts)
        if name in FUNCTIONS and not quoted:
            value = self.function(name, step, state)
        else:
            values = self.expand_words(step.words, state)
            value = values[0] if len(values) == 1 else ("" if not values else values)
        if value is None:
            return
        if self.trace is not None:
            shown = " ".join(_xq(v) for v in value) if isinstance(value, list) else _xq(value)
            self.trace(f"_TRACE: {step.name}={shown}")
        state.vars[step.name] = value
        if step.export:
            state.env[step.name] = " ".join(value) if isinstance(value, list) else value
        state.status = 0 if name != "output" else state.status

    def function(self, name: str, step: Assign, state: State):
        if name in ("output", "output-words"):
            rest = step.text.strip()[len(name):].strip()
            chunks: list[str] = []
            sink = State(state.vars, state.env, state.cwd, chunks.append, state.err)
            status = self.run(parse(rest, step.line), sink)
            state.status = status
            text = "".join(chunks).rstrip("\n")
            #  output-words: the words of the output (unquoted $(...))
            return text.split() if name == "output-words" else text
        if name == "if":
            #  if <condition> then A [else B]: the conditions of the command
            #  hooks; the words of A or B as the words of a command
            text = step.text.strip()
            try:
                cond, then, other = _split_if(text, text)
                chosen = then if self.condition(cond, state, step.line) else other
                values = self.expand_words(
                    tuple(w for w in tokenize(chosen, step.line) if isinstance(w, Word)), state)
            except (ExpandError, CmdSyntaxError) as e:
                self.error(state, step.line, str(e))
                return ""
            return values[0] if len(values) == 1 else values
        args = self.expand_words(step.words[1:], state)
        ctx = self.hook_ctx(state)
        if name == "get-build-type":
            return _builtins.get_build_type(ctx, *(args + ["", ""])[:2])
        if name == "config-options":
            return list(self.config_options())
        if name == "last-modified-directory":
            return _builtins.last_modified_directory(ctx, " ".join(args))
        if name == "is-enabled":
            return _builtins.is_enabled(ctx, *(args + ["", "", ""])[:3])[1]
        if name == "get-version":
            return _builtins.get_version(ctx)
        if name == "first-line":
            return " ".join(args).split("\n", 1)[0]
        if name == "status":
            return str(state.status)
        if name == "basename":
            return os.path.basename(args[0].rstrip("/")) if args else ""
        if name == "dirname":
            return os.path.dirname(args[0].rstrip("/")) or "." if args else "."
        if name == "command-path":
            return shutil.which(args[0], path=state.env.get("PATH")) or "" if args else ""
        if name == "uppercase":
            return " ".join(args).upper()
        if name == "lowercase":
            return " ".join(args).lower()
        if name == "replace":
            try:
                return _builtins.replace(ctx, *args)
            except _builtins.BuiltinError as e:
                self.error(state, step.line, str(e))
                return ""
        if name == "all-modules":
            self.modules_status = dict(self.all_modules())
            return list(self.modules_status)
        if name == "hook-output":
            return self.hook_output(args, state, step.line)
        if name == "all-variants":
            #  the variants of a variant string (a.b -> [a, b]), none for default
            v = " ".join(args)
            return [] if v == "default" else v.replace(".", " ").split()
        return None

    def hook_output(self, args: list[str], state: State, line: int) -> str | list[str]:
        """``hook-output MODULE HOOK ARGS...``: the output of the hook of
        another module (empty when it has none), the list of the values of
        a value hook."""
        if len(args) < 2:
            self.error(state, line, "hook-output: module and hook expected")
            return ""
        values = self.hook_values(args[0], args[1], args[2:])
        if values is not None:
            return values
        fct = self.hook_function(args[0], args[1])
        if not fct:
            return ""
        if fct not in self.functions and self.refresh_functions is not None:
            self.functions = self.refresh_functions()
        if fct not in self.functions:
            return ""
        params, body = self.functions[fct]
        chunks: list[str] = []
        saved = {p: state.vars.get(p) for p in params}
        for p, v in zip(params, args[2:] + [""] * len(params)):
            state.vars[p] = v
        sink = State(state.vars, state.env, state.cwd, chunks.append, state.err, state.status)
        self.run(body, sink)
        for p, v in saved.items():
            if v is None:
                state.vars.pop(p, None)
            else:
                state.vars[p] = v
        return "".join(chunks).rstrip("\n")

    # --------------------------------------------------------- commands

    def _path(self, path: str, state: State) -> str:
        return path if os.path.isabs(path) else os.path.join(state.cwd, path)

    def error(self, state: State, line: int, message: str) -> None:
        state.err(f"{self.where}: line {line}: {message}\n")

    def pipeline(self, p: Pipeline, state: State, line: int) -> int:
        if len(p.commands) == 1:
            return self.simple(p.commands[0], state, line)
        return self.external_pipeline(p, state, line)

    def _argv(self, cmd: Simple, state: State) -> tuple[dict[str, str], list[str]]:
        words = list(cmd.words)
        env: dict[str, str] = {}
        while words and len(words[0].parts) and words[0].parts[0][1] == "":
            m = _ENV_WORD.match(words[0].parts[0][0])
            if not m:
                break
            first = Word(((m.group(2), ""),) + words[0].parts[1:])
            env[m.group(1)] = "".join(self.expand_words((first,), state, glob=False)) if \
                _word_text(first) else ""
            words.pop(0)
        argv = self.expand_words(words, state)
        if self.trace is not None:
            self.trace("_TRACE: " + " ".join([f"{k}={_xq(v)}" for k, v in env.items()]
                                             + [_xq(a) for a in argv]))
        return env, argv

    def simple(self, cmd: Simple, state: State, line: int) -> int:
        env_extra, argv = self._argv(cmd, state)
        if not argv:
            for k, v in env_extra.items():
                state.vars[k] = v
            return 0
        name = argv[0]
        if name in COMMANDS or name in self.functions:
            return self.builtin(name, argv[1:], cmd, state, line, env_extra)
        return self.external([(cmd, env_extra, argv)], state, line)

    def builtin(self, name, args, cmd: Simple, state: State, line, env_extra) -> int:
        out, err, close = self._sinks(cmd, state, line)
        if out is None:
            return 1
        try:
            if name == "cd":
                target = self._path(args[0] if args else state.env.get("HOME", ""), state)
                if not os.path.isdir(target):
                    err(f"{self.where}: line {line}: cd: {args[0] if args else ''}: No such file or directory\n")
                    return 1
                state.cwd = os.path.normpath(target)
                return 0
            if name == "echo":
                newline = True
                if args and args[0] == "-n":
                    newline, args = False, args[1:]
                out(" ".join(args) + ("\n" if newline else ""))
                return 0
            if name in ("return", "exit"):
                #  Bash: the status is taken modulo 256 (return -1 gives 255)
                raise _Return(int(args[0]) & 0xFF if args and re.fullmatch(r"-?\d+", args[0])
                              else state.status)
            if name in ("true", ":"):
                return 0
            if name == "false":
                return 1
            if name == "export":
                for a in args:
                    k, sep, v = a.partition("=")
                    if sep:
                        state.vars[k] = v
                    val = state.vars.get(k, "")
                    state.env[k] = " ".join(val) if isinstance(val, list) else val
                return 0
            if name == "unset":
                for a in args:
                    state.vars.pop(a, None)
                    state.env.pop(a, None)
                return 0
            if name == "check-versions":
                a, op, b = (args + ["", "", ""])[:3]
                return 0 if check_versions(a, op, b) else 1
            if name == "copy":
                return self.copy(args, state, lambda m: err(f"{self.where}: line {line}: copy: {m}\n"))
            if name in ("delete", "delete-tree"):
                return self.delete(args, state, lambda m: err(f"{self.where}: line {line}: {name}: {m}\n"),
                                   tree=name == "delete-tree")
            #  a plug-in function
            params, body = self.functions[name]
            saved = {p: state.vars.get(p) for p in params}
            for p, v in zip(params, args + [""] * len(params)):
                state.vars[p] = v
            sub = State(state.vars, state.env, state.cwd, out, err, state.status)
            status = self.run(body, sub)
            for p, v in saved.items():
                if v is None:
                    state.vars.pop(p, None)
                else:
                    state.vars[p] = v
            return status
        finally:
            close()

    def delete(self, args: list[str], state: State, error, tree: bool = False) -> int:
        """``delete PATH...``: files and symbolic links removed (as ``rm
        -f``, a directory is an error); ``delete-tree PATH...``: files and
        directories removed recursively (as ``rm -fr``). Only under the
        sandbox ($SCBI_BDIR): the location of each path (its directory
        with ``..`` and symbolic links resolved, then its name) must be in
        the sandbox. All the paths are checked first: on an error nothing
        is deleted. A symbolic link is removed, not its target. A missing
        path is not an error."""
        if any(a.startswith("-") for a in args):
            error(f"no option supported: {' '.join(a for a in args if a.startswith('-'))}")
            return 1
        if not args:
            error("missing operand")
            return 1
        bdir = self.ctx.env.get("SCBI_BDIR") if self.ctx.env is not None else ""
        if not bdir:
            error("no sandbox (SCBI_BDIR not set), nothing deleted")
            return 1
        sandbox = os.path.realpath(bdir)
        paths = []
        for a in args:
            p = self._path(a, state).rstrip(os.sep) or os.sep
            name = os.path.basename(p)
            if name in ("", ".", ".."):
                #  delete dir/.. or dir/.: the directory itself
                real = os.path.realpath(p)
            else:
                real = os.path.join(os.path.realpath(os.path.dirname(p)), name)
            if not real.startswith(sandbox + os.sep):
                error(f"'{a}' ({real}) is not in the sandbox {sandbox}, nothing deleted")
                return 1
            if not tree and os.path.isdir(real) and not os.path.islink(real):
                error(f"'{a}' is a directory (use delete-tree), nothing deleted")
                return 1
            paths.append(real)
        status = 0
        for a, real in zip(args, paths):
            try:
                if os.path.isdir(real) and not os.path.islink(real):
                    shutil.rmtree(real)
                elif os.path.lexists(real):
                    os.unlink(real)
            except OSError as e:
                error(f"cannot delete '{a}': {e.strerror or e}")
                status = 1
        return status

    def copy(self, args: list[str], state: State, error) -> int:
        """``copy SOURCE... DEST``: files and directories (recursively,
        symbolic links kept as links) copied as ``cp -r`` does: into DEST
        when it is a directory (or for several sources), else to DEST.
        Existing files are replaced, existing directories merged."""
        if any(a.startswith("-") for a in args):
            error(f"no option supported: {' '.join(a for a in args if a.startswith('-'))}")
            return 1
        if len(args) < 2:
            error("missing destination" if args else "missing file operand")
            return 1
        *sources, dest = args
        dpath = self._path(dest, state)
        into = os.path.isdir(dpath)
        if len(sources) > 1 and not into:
            error(f"target '{dest}' is not a directory")
            return 1
        status = 0
        for src in sources:
            spath = self._path(src, state)
            if not os.path.lexists(spath):
                error(f"cannot stat '{src}': No such file or directory")
                status = 1
                continue
            target = os.path.join(dpath, os.path.basename(os.path.normpath(spath))) if into else dpath
            if os.path.realpath(spath) == os.path.realpath(target):
                error(f"'{src}' and '{dest}' are the same file")
                status = 1
                continue
            try:
                if os.path.isdir(spath) and not os.path.islink(spath):
                    if os.path.realpath(target).startswith(os.path.realpath(spath) + os.sep):
                        error(f"cannot copy a directory, '{src}', into itself, '{dest}'")
                        status = 1
                        continue
                    _copy_tree(spath, target)
                else:
                    _copy_file(spath, target)
            except OSError as e:
                error(f"cannot copy '{src}' to '{dest}': {e.strerror or e}")
                status = 1
        return status

    def _sinks(self, cmd: Simple, state: State, line: int):
        """Output functions of a built-in with its redirections."""
        out, err = state.out, state.err
        files = []

        def close() -> None:
            for f in files:
                f.close()

        for r in cmd.redirects:
            if r.op == "2>&1":
                err = out
                continue
            if r.op == "<":
                continue
            target = self.expand_words((r.target,), state, glob=False)[0]
            path = self._path(target, state)
            try:
                f = open(path, "a" if r.op.endswith(">>") else "w")
            except OSError as e:
                state.err(f"{self.where}: line {line}: {target}: {e.strerror}\n")
                close()
                return None, None, close
            files.append(f)
            if r.op in (">", ">>"):
                out = f.write
            elif r.op in ("2>", "2>>"):
                err = f.write
            else:
                out = err = f.write
        return out, err, close

    def _streams(self, cmd: Simple, state: State, line: int, stdout_default):
        """stdin, stdout, stderr of an external command, its redirections
        applied in order (2>&1 takes the stdout of that moment). The
        values are file objects or the symbols "OUT" / "ERR" (the state's
        output functions) or the default stdout (a pipe to the next
        command). Returns False after an error."""
        stdin = None
        stdout = stdout_default
        stderr = "ERR"
        opened = []
        for r in cmd.redirects:
            if r.op == "2>&1":
                stderr = stdout
                continue
            path = self._path(self.expand_words((r.target,), state, glob=False)[0], state)
            mode = {"<": "rb", ">": "wb", ">>": "ab", "2>": "wb", "2>>": "ab", "&>": "wb"}[r.op]
            try:
                f = open(path, mode)
            except OSError as e:
                state.err(f"{self.where}: line {line}: {path}: {e.strerror}\n")
                for o in opened:
                    o.close()
                return False
            opened.append(f)
            if r.op == "<":
                stdin = f
            elif r.op in (">", ">>"):
                stdout = f
            elif r.op in ("2>", "2>>"):
                stderr = f
            else:
                stdout = stderr = f
        return stdin, stdout, stderr, opened

    def external(self, chain, state: State, line: int) -> int:
        """Run the commands of ``chain`` connected by pipes:
        [(Simple, extra environment, argv)]."""
        procs = []
        readers: list[tuple[object, Callable[[str], None]]] = []
        opened_all = []
        to_close: list[int] = []
        prev_read = None
        status = 0
        try:
            for idx, (cmd, env_extra, argv) in enumerate(chain):
                last = idx == len(chain) - 1
                if last:
                    out_default, next_read = "OUT", None
                else:
                    next_read, w = os.pipe()
                    out_default = w
                    to_close.append(w)
                streams = self._streams(cmd, state, line, out_default)
                if streams is False:
                    return 1
                stdin, stdout, stderr, opened = streams
                opened_all += opened
                if stdin is None:
                    stdin = prev_read if prev_read is not None else subprocess.DEVNULL
                env = dict(state.env)
                env["PWD"] = state.cwd
                env.update(env_extra)
                if "/" in argv[0]:
                    #  relative to the directory of the hook
                    exe = argv[0] if os.path.exists(self._path(argv[0], state)) else None
                else:
                    exe = shutil.which(argv[0], path=env.get("PATH"))
                if exe is None:
                    #  as Bash: a path is not searched in PATH
                    why = "No such file or directory" if "/" in argv[0] else "command not found"
                    state.err(f"{self.where}: line {line}: {argv[0]}: {why}\n")
                    status = 127
                    prev_read = next_read
                    continue
                popen_out = subprocess.PIPE if stdout in ("OUT", "ERR") else stdout
                if stderr == stdout and stdout in ("OUT", "ERR"):
                    popen_err = subprocess.STDOUT
                elif stderr == "ERR" and stdout == "OUT" and state.err is state.out:
                    #  the output of the commands is not split (as in the
                    #  logs of the steps)
                    popen_err = subprocess.STDOUT
                elif stderr in ("OUT", "ERR"):
                    popen_err = subprocess.PIPE
                else:
                    popen_err = stderr
                try:
                    #  argv[0] as written (as a shell does), the program found
                    try:
                        proc = subprocess.Popen(argv, executable=exe, cwd=state.cwd, env=env, stdin=stdin,
                                                stdout=popen_out, stderr=popen_err)
                    except OSError as e:
                        if e.errno != errno.ENOEXEC:
                            raise
                        #  a script without #! line: run by the shell, as
                        #  execvp and a shell do
                        proc = subprocess.Popen(["/bin/sh", exe, *argv[1:]], cwd=state.cwd, env=env,
                                                stdin=stdin, stdout=popen_out, stderr=popen_err)
                except PermissionError:
                    state.err(f"{self.where}: line {line}: {argv[0]}: Permission denied\n")
                    status = 126
                    prev_read = next_read
                    continue
                if proc.stdout is not None:
                    readers.append((proc.stdout, state.out if stdout == "OUT" else state.err))
                if proc.stderr is not None:
                    readers.append((proc.stderr, state.out if stderr == "OUT" else state.err))
                if isinstance(prev_read, int):
                    os.close(prev_read)
                prev_read = next_read
                procs.append((proc, last))
            for fd in to_close:
                os.close(fd)
            to_close = []
            if isinstance(prev_read, int):
                os.close(prev_read)
            self._drain(readers)
            for proc, last in procs:
                proc.wait()
                if last:
                    status = proc.returncode
            return status
        finally:
            for fd in to_close:
                try:
                    os.close(fd)
                except OSError:
                    pass
            for f in opened_all:
                f.close()

    @staticmethod
    def _drain(readers) -> None:
        import selectors

        sel = selectors.DefaultSelector()
        for stream, sink in readers:
            sel.register(stream, selectors.EVENT_READ, sink)
        open_streams = len(readers)
        while open_streams:
            for key, _ in sel.select():
                data = key.fileobj.read1(65536)
                if not data:
                    sel.unregister(key.fileobj)
                    key.fileobj.close()
                    open_streams -= 1
                    continue
                key.data(data.decode(errors="replace"))

    def external_pipeline(self, p: Pipeline, state: State, line: int) -> int:
        chain = []
        for cmd in p.commands:
            env_extra, argv = self._argv(cmd, state)
            if not argv:
                continue
            if argv[0] in COMMANDS or argv[0] in self.functions:
                self.error(state, line, f"{argv[0]}: built-ins cannot be used in a pipe")
                return 1
            chain.append((cmd, env_extra, argv))
        return self.external(chain, state, line)
