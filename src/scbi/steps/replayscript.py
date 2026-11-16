"""``scbi replay --script``: a replay file (scbi.steps.replay) as a Bash
script to run the step by hand.

The script sets the environment of the hook, its parameters, the plug-in
variables and the driver variables, defines the plug-in functions it
calls, goes to the directory of the hook, then runs the hook body
translated from the command language (scbi.hooks.cmdlang) to Bash, with
its control flow. What is known when the script is generated (variant,
target, cross, enabled(), build-type(), version(), the value built-ins
with known arguments...) is resolved to its value; what depends on the
state when the script runs (file tests, command status, ok(), the
variables set by the hook) stays Bash.

This module only writes text: the driver runs no Bash.
"""

from __future__ import annotations

import re
import shlex

from scbi.hooks import cmdlang
from scbi.hooks.cmdlang import FUNCTIONS, AndOr, Assign, For, If, Pipeline, Simple, State, Word, Write
from scbi.hooks.evaluate import GuardContext
from scbi.hooks.expand import ExpandError, _split_if, expand
from scbi.plugin import expr
from scbi.plugin.model import BUILTINS
from scbi.steps import replay

#  check-versions and the version comparisons of conditions
_VERSIONS_HELPER = """\
_scbi_check_versions()
{
    #  $1 OP $2 (= == != < <= > >=), versions compared as sort -V
    local a=$1 op=$2 b=$3 first
    first=$(printf '%s\\n%s\\n' "$a" "$b" | sort -V | head -n1)
    case $op in
        =|==) [[ $a == "$b" ]] ;;
        !=) [[ $a != "$b" ]] ;;
        '<') [[ $a != "$b" && $first == "$a" ]] ;;
        '<=') [[ $first == "$a" ]] ;;
        '>') [[ $a != "$b" && $first == "$b" ]] ;;
        '>=') [[ $first == "$b" ]] ;;
        *) return 2 ;;
    esac
}
"""

#  conditions on the state when the script runs
_FILE_TESTS = {"exists": "-e", "is-dir": "-d", "is-file": "-f", "is-link": "-L"}
_DYNAMIC_CALLS = set(_FILE_TESTS) | {"empty", "ok"}
_WALK_CALLS = {"depends-kind", "is-meta", "is-aggregate", "is-aggregated"}
_SPECIAL = set(";&()<>|`\\'\"{} \t")


class ScriptError(Exception):
    """A construct which cannot be written as a script."""


def q(value: str) -> str:
    return shlex.quote(value)


class _Translator:
    def __init__(self, r: replay.Replay):
        self.r = r
        self.ctx = replay.context(r)
        self.ctx.locals = {k: (" ".join(v) if isinstance(v, list) else v) for k, v in r.variables.items()}
        #  variables set by the hook (or a function): their value is only
        #  known when the script runs
        self.dynamic: set[str] = set()
        #  variables holding a list (Bash arrays)
        self.lists: set[str] = {k for k, v in r.variables.items() if isinstance(v, list)}
        self.helpers: set[str] = set()
        self.called: set[str] = set()
        self.in_function = False

    # ------------------------------------------------------------ static

    def runner(self) -> cmdlang.Runner:
        return replay.runner(self.r, self.ctx)

    def state(self) -> State:
        return State(dict(self.r.variables), dict(self.r.environment), self.r.cwd, lambda t: None,
                     lambda t: None)

    def uses_dynamic(self, text: str) -> bool:
        for m in re.finditer(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)", text):
            if m.group(1) in self.dynamic:
                return True
        return "$?" in text

    # ------------------------------------------------------------- words

    def word(self, w: Word) -> str:
        """A word of a command: Bash text."""
        if len(w.parts) == 1 and w.parts[0][1] == "":
            text = w.parts[0][0]
            m = re.fullmatch(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", text)
            if m and m.group(1) in self.lists:
                return f'"${{{m.group(1)}[@]}}"'
            m = re.fullmatch(r"\$\((.*)\)", text, re.S)
            if m and _balanced(m.group(1)):
                return self.substitution(m.group(1), quoted=False)
        out = []
        for text, quote in w.parts:
            if quote == "'":
                out.append(q(text) if text else "''")
            elif quote == '"':
                out.append('"' + self.inner(text, quoted=True) + '"')
            else:
                out.append(self.inner(text, quoted=False))
        return "".join(out)

    def inner(self, text: str, quoted: bool) -> str:
        """Text of a word part: variables and $(...) translated, literal
        characters escaped."""
        out, i, n = [], 0, len(text)
        while i < n:
            c = text[i]
            if c == "$" and text.startswith("$(", i):
                j = _closing(text, i + 1)
                inner = text[i + 2 : j]
                #  in a larger word: one word (a list joined with spaces)
                out.append(self.dq(inner) if quoted else '"' + self.dq(inner) + '"')
                i = j + 1
                continue
            if c == "$":
                m = re.compile(r"\$(?:\{[^}]*\}|[A-Za-z_][A-Za-z0-9_]*)").match(text, i)
                if m:
                    ref = m.group(0)
                    name = re.match(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)", ref).group(1)
                    if name in self.lists and ref in (f"${name}", f"${{{name}}}"):
                        ref = f"${{{name}[*]}}"
                    out.append(ref if quoted else f'"{ref}"')
                    i = m.end()
                    continue
            if quoted:
                out.append("\\" + c if c in '"`\\' else c)
            else:
                out.append("\\" + c if c in _SPECIAL else c)
            i += 1
        return "".join(out)

    def dq(self, inner: str) -> str:
        """``$(f args)`` as text inside double quotes."""
        sub = self.substitution(inner, quoted=True)
        if len(sub) >= 2 and sub[0] == '"' and sub[-1] == '"':
            return sub[1:-1]
        #  a value quoted by shlex: its text escaped for double quotes
        value = shlex.split(sub)[0] if sub else ""
        return re.sub(r'(["$`\\])', r"\\\1", value)

    def substitution(self, inner: str, quoted: bool) -> str:
        """``$(f args)`` of a word: Bash text (a value, ``$(...)`` or an
        array expansion)."""
        words = inner.split(None, 1)
        name = words[0] if words else ""
        rest = words[1] if len(words) > 1 else ""
        if name == "config-options":
            return '"${CONFIG_OPTIONS[*]}"' if quoted else '"${CONFIG_OPTIONS[@]}"'
        if name not in FUNCTIONS and name not in BUILTINS:
            raise ScriptError(f"unknown function $({name} ...)")
        if name in ("all-modules", "hook-output"):
            raise ScriptError(f"{name} is not available in a replay")
        if not self.uses_dynamic(inner) and name not in ("output", "output-words", "status"):
            value = self.static_function(name, inner)
            if isinstance(value, list):
                return " ".join(q(v) for v in value) if not quoted else q(" ".join(value))
            return q(value)
        if name in ("output", "output-words"):
            cmd = self.command_line(rest)
            return f'"$({cmd})"' if name == "output" or quoted else f"$({cmd})"
        if name == "status":
            return '"$?"'
        if name == "command-path":
            return f'"$(command -v {self.words_of(rest)})"'
        if name in ("basename", "dirname"):
            return f'"$({name} {self.words_of(rest)})"'
        if name in ("uppercase", "lowercase"):
            tr = "'[:lower:]' '[:upper:]'" if name == "uppercase" else "'[:upper:]' '[:lower:]'"
            return f'"$(echo {self.words_of(rest)} | tr {tr})"'
        raise ScriptError(f"$({inner}): arguments only known when the hook runs")

    def static_function(self, name: str, inner: str):
        """The value of a function with known arguments (as the hook
        would compute it)."""
        try:
            if name in FUNCTIONS:
                words = tuple(w for w in cmdlang.tokenize(inner, 0) if isinstance(w, Word))
                return self.runner().function(name, Assign(0, "", False, words, inner), self.state())
            return expand(f"$({inner})", self.ctx)
        except (ExpandError, cmdlang.CmdSyntaxError) as e:
            raise ScriptError(f"$({inner}): {e}") from None

    def words_of(self, text: str) -> str:
        words = [w for w in cmdlang.tokenize(text, 0) if isinstance(w, Word)]
        return " ".join(self.word(w) for w in words)

    def command_line(self, text: str) -> str:
        body = cmdlang.parse(text, 0)
        if len(body) != 1 or not isinstance(body[0], AndOr):
            raise ScriptError(f"not a command line: {text!r}")
        return self.and_or(body[0])

    # ---------------------------------------------------------- commands

    def simple(self, cmd: Simple) -> str:
        words = [self.word(w) for w in cmd.words]
        first = cmdlang._word_text(cmd.words[0]) if cmd.words else ""
        if first in ("return", "exit"):
            words[0] = "return" if self.in_function and first == "return" else "exit"
        elif first == "copy":
            words[0] = "cp -r"
        elif first == "check-versions":
            self.helpers.add("versions")
            words[0] = "_scbi_check_versions"
        elif first in self.r.functions:
            self.called.add(first)
        out = " ".join(words)
        for r in cmd.redirects:
            out += f" {r.op}" + (f" {self.word(r.target)}" if r.target is not None else "")
        return out

    def pipeline(self, p: Pipeline) -> str:
        return " | ".join(self.simple(c) for c in p.commands)

    def and_or(self, s: AndOr) -> str:
        out = self.pipeline(s.first)
        for op, p in s.rest:
            out += f" {op} {self.pipeline(p)}"
        return out

    def assign(self, s: Assign, ind: str) -> list[str]:
        name, export = s.name, "export " if s.export else ""
        first = cmdlang._word_text(s.words[0]) if s.words else ""
        quoted = s.words and any(qt for _, qt in s.words[0].parts)
        lines: list[str] = []
        if first in FUNCTIONS and not quoted:
            rest = s.text.strip()[len(first):].strip()
            if first == "config-options":
                lines.append(f'{name}=("${{CONFIG_OPTIONS[@]}}")')
                self.lists.add(name)
            elif first == "output":
                lines.append(f"{name}=$({self.command_line(rest)})")
                self.lists.discard(name)
            elif first == "output-words":
                lines.append(f"{name}=($({self.command_line(rest)}))")
                self.lists.add(name)
            elif first == "status":
                lines.append(f"{name}=$?")
                self.lists.discard(name)
            elif first == "if":
                lines += self.assign_if(name, rest, ind)
            elif not self.uses_dynamic(rest) and first not in ("all-modules", "hook-output"):
                value = self.static_function(first, s.text.strip())
                if isinstance(value, list):
                    lines.append(f"{name}=(" + " ".join(q(v) for v in value) + ")")
                    self.lists.add(name)
                else:
                    lines.append(f"{name}={q(value)}")
                    self.lists.discard(name)
            else:
                lines.append(f"{name}={self.substitution(s.text.strip(), quoted=True)}")
                self.lists.discard(name)
        else:
            words = [self.word(w) for w in s.words]
            whole_list = len(s.words) == 1 and re.fullmatch(r'"\$\{\w+\[@\]\}"', words[0] or "")
            if len(words) > 1 or whole_list:
                lines.append(f"{name}=(" + " ".join(words) + ")")
                self.lists.add(name)
            else:
                lines.append(f"{name}={words[0] if words else ''}")
                self.lists.discard(name)
        self.dynamic.add(name)
        if export:
            ref = f'"${{{name}[*]}}"' if name in self.lists else f'"${name}"'
            lines.append(f"export {name}={ref}" if name in self.lists else f"export {name}")
        return [ind + ln for ln in lines]

    def assign_if(self, name: str, text: str, ind: str) -> list[str]:
        cond, then, other = _split_if("if " + text, text)
        self.lists.add(name)
        return [f"if {self.condition(cond)}; then",
                f"    {name}=({self.words_of(then)})",
                "else",
                f"    {name}=({self.words_of(other)})",
                "fi"]

    # -------------------------------------------------------- conditions

    def condition(self, text: str) -> str:
        try:
            node = expr.parse(text)
        except expr.ExprError as e:
            raise ScriptError(str(e)) from None
        return self.cond(node)

    def is_static(self, node) -> bool:
        if isinstance(node, expr.BoolOp):
            return all(self.is_static(i) for i in node.items)
        if isinstance(node, expr.Not):
            return self.is_static(node.expr)
        if isinstance(node, expr.Cmp):
            return self.is_static(node.left) and self.is_static(node.right)
        if isinstance(node, expr.Var):
            return node.name != "status"
        if isinstance(node, expr.Lit):
            return not self.uses_dynamic(node.value)
        if isinstance(node, expr.Call):
            if node.name in _WALK_CALLS:
                raise ScriptError(f"{node.name}() is not available in a replay")
            return node.name not in _DYNAMIC_CALLS and not self.uses_dynamic(node.arg)
        return True  # on <discriminants>

    def cond(self, node) -> str:
        if self.is_static(node):
            value = expr.evaluate_node(node, GuardContext(self.ctx))
            return "true" if value else "false"
        if isinstance(node, expr.BoolOp):
            sep = " && " if node.op == "and" else " || "
            return "{ " + sep.join(self.cond(i) for i in node.items) + "; }"
        if isinstance(node, expr.Not):
            return "! " + self.cond(node.expr)
        if isinstance(node, expr.Cmp):
            left, right = self.operand(node.left), self.operand(node.right)
            if node.op == "=~":
                return f"[[ {left} =~ $(printf '%s' {right}) ]]"
            if node.op in ("==", "!="):
                return f"[[ {left} {node.op} {right} ]]"
            self.helpers.add("versions")
            return f"_scbi_check_versions {left} {q(node.op)} {right}"
        if isinstance(node, expr.Var):  # status
            return '[[ "$?" != 0 ]]'
        if isinstance(node, expr.Lit):
            return f"[[ -n {self.operand(node)} ]]"
        if isinstance(node, expr.Call):
            arg = self.operand(expr.Lit(node.arg))
            if node.name in _FILE_TESTS:
                return f"[[ {_FILE_TESTS[node.name]} {arg} ]]"
            if node.name == "empty":
                return f"[[ -z {arg} ]]"
            if node.name == "ok":
                return "{ " + self.command_line(node.arg) + "; } > /dev/null"
        raise ScriptError(f"cannot translate the condition {node}")

    def operand(self, node) -> str:
        if isinstance(node, expr.Var):
            if node.name == "status":
                return '"$?"'
            return q(str(GuardContext(self.ctx).variable(node.name)))
        if isinstance(node, expr.Lit):
            if not self.uses_dynamic(node.value):
                return q(expand(node.value, self.ctx))
            return '"' + self.inner(node.value, quoted=True) + '"'
        if isinstance(node, expr.Call) and self.is_static(node):
            value = GuardContext(self.ctx).function(node.name, expand(node.arg, self.ctx))
            return q(("true" if value else "false") if isinstance(value, bool) else str(value))
        raise ScriptError(f"cannot translate the operand {node}")

    # -------------------------------------------------------------- body

    def body(self, steps: tuple, depth: int) -> list[str]:
        ind = "    " * depth
        out: list[str] = []
        for s in steps:
            if isinstance(s, AndOr):
                out.append(ind + self.and_or(s))
            elif isinstance(s, Assign):
                out += self.assign(s, ind)
            elif isinstance(s, If):
                for k, (cond, body) in enumerate(s.branches):
                    c = self.condition(cond)
                    #  resolved when generated: the condition as a comment
                    note = f"  # {cond}" if c in ("true", "false") else ""
                    out.append(f"{ind}{'if' if k == 0 else 'elif'} {c}; then{note}")
                    out += self.body(body, depth + 1) or [ind + "    :"]
                if s.orelse is not None:
                    out.append(ind + "else")
                    out += self.body(s.orelse, depth + 1) or [ind + "    :"]
                out.append(ind + "fi")
            elif isinstance(s, For):
                out.append(f"{ind}for {s.name} in {' '.join(self.word(w) for w in s.words)}; do")
                self.dynamic.add(s.name)
                self.lists.discard(s.name)
                out += self.body(s.body, depth + 1) or [ind + "    :"]
                out.append(ind + "done")
            elif isinstance(s, Write):
                op = ">>" if s.append else ">"
                text = s.text if s.raw else self.heredoc_text(s.text)
                delim = "SCBI_EOF"
                while delim in text:
                    delim += "_"
                out.append(f"{ind}cat {op} {self.word(s.path)} <<{f"'{delim}'" if s.raw else delim}")
                out += text.rstrip("\n").split("\n") + [delim]
            else:
                raise ScriptError(f"unsupported step {s!r}")
        return out

    def heredoc_text(self, text: str) -> str:
        """An expanded write block: $VAR as in a here-document, $(f ...)
        translated, \\$ \\` \\\\ kept (here-document escapes)."""
        out, i = [], 0
        while i < len(text):
            if text.startswith("\\", i) and i + 1 < len(text):
                out.append(text[i : i + 2])
                i += 2
                continue
            if text.startswith("$(", i):
                j = _closing(text, i + 1)
                out.append(self.dq(text[i + 2 : j]))
                i = j + 1
                continue
            out.append(text[i])
            i += 1
        return "".join(out)

    # -------------------------------------------------------------- main

    def script(self) -> str:
        r = self.r
        body = self.body(cmdlang.parse(r.run, r.line), 0)
        functions: list[str] = []
        done: set[str] = set()
        while self.called - done:
            fname = sorted(self.called - done)[0]
            done.add(fname)
            f = r.functions[fname]
            params = list(f.get("params") or ())
            saved, self.in_function = self.in_function, True
            saved_dynamic = set(self.dynamic)
            self.dynamic |= set(params)
            fbody = self.body(cmdlang.parse(f.get("run") or "", int(f.get("line") or 1)), 1)
            self.dynamic, self.in_function = saved_dynamic, saved
            functions += [f"{fname}()", "{"]
            functions += [f"    local {p}=${k + 1}" for k, p in enumerate(params)]
            functions += (fbody or ["    :"]) + ["}", ""]

        head = ["#!/bin/bash", "",
                f"#  {r.module} [{r.variant}] {r.hook}: the {r.function} hook of",
                f"#  {r.plugin_file}, line {r.line}",
                "#  (generated by scbi replay --script)", "",
                "#  Environment of the hook"]
        head += [f"export {k}={q(v)}" for k, v in sorted(r.environment.items())]
        head += ["", "#  Driver variables"]
        head += [f"{k}={q(v)}" for k, v in sorted(r.driver.items()) if k not in r.environment]
        head += ["", "#  Parameters of the hook"]
        head += [f"{k}={q(v)}" for k, v in r.params.items()]
        if r.variables:
            head += ["", "#  Plug-in variables"]
            for k, v in r.variables.items():
                head.append(f"{k}=(" + " ".join(q(x) for x in v) + ")" if isinstance(v, list) else f"{k}={q(v)}")
        head += ["", "#  Configuration options of the module",
                 "CONFIG_OPTIONS=(" + " ".join(q(o) for o in r.config_options) + ")", ""]
        if "versions" in self.helpers:
            head += [_VERSIONS_HELPER]
        if functions:
            head += ["#  Plug-in functions", ""] + functions
        head += [f"cd {q(r.cwd)} || exit 1", ""]
        return "\n".join(head + body) + "\n"


def _closing(text: str, open_paren: int) -> int:
    depth, j = 0, open_paren
    while j < len(text):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise ScriptError(f"unterminated $( in {text!r}")


def _balanced(text: str) -> bool:
    depth = 0
    for c in text:
        depth += c == "("
        depth -= c == ")"
        if depth < 0:
            return False
    return depth == 0


def script(r: replay.Replay) -> str:
    """The Bash script of the replay file ``r``."""
    return _Translator(r).script()
