"""Conversion of the Bash command hooks (and plug-in functions) of legacy
plug-ins to the command language (scbi.hooks.cmdlang).

The input is the body of a ``declare -f`` definition (one command per
line, ``; then`` / ``do`` layout of Bash). What has no equivalent is
reported (CmdUnliftable) and converted by hand.
"""

from __future__ import annotations

import re

from scbi.hooks.cmdlang import CmdSyntaxError, parse
from scbi.plugin import expr
from scbi.plugin.runtimefuncs import RUNTIME_FUNCTIONS

#  $(...) kept inline (scbi.hooks.expand built-ins)
INLINE = ("get-version", "get-build-type", "is-enabled", "last-modified-directory", "get-os-inc-dir",
          "get-os-lib", "get-os-lib-dir", "get-os-bin", "get-os-bin-dir", "store-key", "basename", "ls")
#  runtime functions lifted (built-ins of the command language, or
#  gprbuild-project rewritten as the gprbuild command line)
RUNTIME_BUILTINS = frozenset(("get-version", "get-build-type", "is-enabled", "last-modified-directory",
                              "get-os-inc-dir", "get-os-lib", "get-os-lib-dir", "get-os-bin", "get-os-bin-dir",
                              "get-config-options", "gprbuild-project", "all-variants",
                              "check-versions"))
#  shell built-ins with no equivalent
UNSUPPORTED = ("eval", "source", ".", "set", "shift", "declare", "typeset", "read", "pushd", "popd",
               "trap", "wait", "let", "while", "until", "case", "select", "function", "exec")

_ASSIGN = re.compile(r"^(local\s+|export\s+)?([A-Za-z_][A-Za-z0-9_]*)(\+?)=(.*)$")
_HEREDOC = re.compile(r"^cat\s+(?:(>>?)\s*(\S+)\s+)?<<(-?)\s*(['\"]?)(\w+)\4(?:\s+(>>?)\s*(\S+))?$")
_ARRAY_ALL = re.compile(r'"?\$\{([A-Za-z_]\w*)\[[@*]\]\}"?')
_SUPPORTED_BRACE = re.compile(r"\$\{[A-Za-z_]\w*(?:(?:%%|%|##|#|:-|:\+|//|/)[^{}$]*|\[[^\]\"']+\])?\}")
_ARRAY_KEY = re.compile(r"""\$\{([A-Za-z_]\w*)\[["']([^"'\]]+)["']\]\}""")


def _single_word(text: str) -> bool:
    """``text`` is one shell word (VAR="a b" alone, not VAR="a b" cmd)."""
    from scbi.bashcompat import ShellSyntaxError, shell_words

    try:
        return len(shell_words(text)) <= 1
    except ShellSyntaxError:
        return True


class CmdUnliftable(Exception):
    pass


class _Lifter:
    def __init__(self, params: dict[str, str]):
        #  $1.. of a function -> its parameter name
        self.params = params
        self.out: list[str] = []
        self.tmp = 0

    def emit(self, depth: int, text: str) -> None:
        self.out.append("    " * depth + text)

    def temp(self) -> str:
        self.tmp += 1
        return f"_S{self.tmp}"

    # ------------------------------------------------------- expansion

    def words_text(self, text: str, depth: int) -> str:
        """A command line or value with its substitutions converted."""
        from scbi.plugin.lift import map_functions

        text = map_functions(text)
        text = _ARRAY_ALL.sub(lambda m: f"${m.group(1)}", text)
        text = _ARRAY_KEY.sub(lambda m: f"${{{m.group(1)}[{m.group(2)}]}}", text)
        #  an escaped \$1 stays as it is (literal text)
        for n, name in self.params.items():
            text = re.sub(r"(?<!\\)\$\{?" + n + r"\}?(?![0-9])", "$" + name, text)
        if re.search(r"(?<!\\)\$[0-9#@*!-]", text):
            raise CmdUnliftable(f"positional or special parameter in {text!r}")
        if "$((" in text:
            raise CmdUnliftable(f"arithmetic in {text!r}")
        text = re.sub(r"(?<!\\)\$\?", "$_STATUS", text)
        for m in re.finditer(r"\$\{[^}]*\}", text):
            if not _SUPPORTED_BRACE.fullmatch(m.group(0)):
                raise CmdUnliftable(f"unsupported expansion {m.group(0)}")
        if "`" in text:
            raise CmdUnliftable(f"backquotes in {text!r}")
        return self.substitutions(text, depth)

    def substitutions(self, text: str, depth: int) -> str:
        """$(...) of commands hoisted to assignments before the line."""
        result, i = [], 0
        while True:
            j = text.find("$(", i)
            if j < 0:
                result.append(text[i:])
                break
            k, level = j + 1, 0
            while k < len(text):
                level += text[k] == "("
                level -= text[k] == ")"
                if level == 0:
                    break
                k += 1
            if k >= len(text):
                raise CmdUnliftable(f"unterminated $( in {text!r}")
            inner = text[j + 2:k].strip()
            quoted = text[:j].count('"') % 2 == 1
            first = inner.split()[0] if inner.split() else ""
            result.append(text[i:j])
            if first in INLINE:
                result.append(f"$({self.substitutions(inner, depth)})")
            else:
                var = self.temp()
                self.assign_function(var, inner, depth, split=not quoted)
                result.append(f"${var}")
            i = k + 1
        return "".join(result)

    def assign_function(self, var: str, inner: str, depth: int, split: bool) -> None:
        """VAR = <the value of $(inner)>."""
        words = inner.split()
        first = words[0] if words else ""
        if first == "get-config-options":
            self.emit(depth, f"{var} = config-options")
        elif first == "command" and len(words) == 3 and words[1] == "-v":
            self.emit(depth, f"{var} = command-path {words[2]}")
        elif first in ("get-build-type", "last-modified-directory", "is-enabled", "get-version", "basename",
                       "all-variants", "command-path"):
            self.emit(depth, f"{var} = {self.substitutions(inner, depth)}")
        elif first in INLINE:
            #  a function of values only
            self.emit(depth, f"{var} = $({self.substitutions(inner, depth)})")
        else:
            self.check_command(inner)
            self.emit(depth, f"{var} = {'output-words' if split else 'output'} {self.substitutions(inner, depth)}")

    # -------------------------------------------------------- commands

    def check_command(self, line: str) -> None:
        first = line.split()[0] if line.split() else ""
        if first in UNSUPPORTED:
            raise CmdUnliftable(f"unsupported shell command {first!r}")
        for part in re.split(r"&&|\|\||\||;", line):
            words = [w for w in part.split() if not re.match(r"^\w+=", w)]
            #  a loop or block after a pipe or a ';' (cat f | while read x; do)
            if words and words[0] in UNSUPPORTED + ("do", "done", "then", "fi", "esac"):
                raise CmdUnliftable(f"unsupported shell command {words[0]!r}")
            if words and words[0] in RUNTIME_FUNCTIONS and words[0] not in RUNTIME_BUILTINS:
                raise CmdUnliftable(f"runtime function {words[0]!r} is not a built-in")
        if first == "echo" and len(line.split()) > 1 and line.split()[1] in ("-e", "-ne", "-en"):
            raise CmdUnliftable("echo -e")
        if line.lstrip().startswith(("(", "{")):
            raise CmdUnliftable(f"sub-shell or group in {line!r}")
        if "<<" in line:
            raise CmdUnliftable(f"here-document in {line!r}")

    def command(self, line: str, depth: int) -> None:
        s = line.strip()
        if not s:
            return
        m = re.fullmatch(r"get-config-options\s+([A-Za-z_]\w*)(?:\s.*)?", s)
        if m:
            self.emit(depth, f"{m.group(1)} = config-options")
            return
        m = re.fullmatch(r"(\[\[.*\]\])\s*(&&|\|\|)\s*(.+)", s)
        if m:
            cond = self.condition(m.group(1), depth)
            self.emit(depth, f"if {cond if m.group(2) == '&&' else f'not ({cond})'}:")
            self.command(m.group(3), depth + 1)
            return
        if s.startswith("local ") and "=" not in s:
            return  # declaration only
        #  NAME+=" more" cmd: environment of the command only
        m = re.fullmatch(r"""([A-Za-z_]\w*)\+=("[^"]*"|'[^']*'|[^\s"']\S*)\s+(\S.*)""", s)
        if m:
            value = m.group(2)[1:-1] if m.group(2)[0] in "\"'" else m.group(2)
            self.command(f'{m.group(1)}="${m.group(1)}{value}" {m.group(3)}', depth)
            return
        m = _ASSIGN.match(s)
        if m and (not re.search(r"\s", m.group(4).strip()) or m.group(4).startswith("(")
                  or (m.group(4).startswith(('"', "'", "$(")) and _single_word(m.group(4)))):
            self.assignment(m, depth)
            return
        if s.startswith("local ") or s.startswith("export "):
            #  several assignments
            for part in re.findall(r"""[A-Za-z_]\w*=(?:"[^"]*"|'[^']*'|\S)*""", s.split(None, 1)[1]):
                self.command(("export " if s.startswith("export") else "") + part, depth)
            return
        if "$?" in s:
            self.emit(depth, "_STATUS = status")
        self.check_command(s)
        text = _gprbuild_project(_cp_to_copy(self.words_text(s, depth)))
        if text.startswith("return $_STATUS"):
            text = "return"
        self.emit(depth, text)

    def assignment(self, m: re.Match, depth: int) -> None:
        prefix, name, append, value = m.group(1) or "", m.group(2), m.group(3), m.group(4)
        export = "export " if prefix.startswith("export") else ""
        from scbi.plugin.lift import map_functions

        v = map_functions(value.strip())
        if v.startswith("(") and v.endswith(")"):
            items = v[1:-1].strip()
            value_text = (f"${name} " if append else "") + self.words_text(items, depth)
            self.emit(depth, f"{export}{name} = {value_text}".rstrip())
            return
        if append:
            #  X+=" a b": X becomes the list of its words and the new ones
            #  (as the unquoted $X a Bash command would use)
            if v[:1] in "\"'" and v[-1:] == v[:1]:
                v = v[1:-1]
            self.emit(depth, f"{export}{name} = ${name} {self.words_text(v, depth)}".rstrip())
            return
        whole = re.fullmatch(r'"?\$\((.*)\)"?', v)
        if whole and whole.group(1).count("$(") == 0:
            if whole.group(1).split()[0] in INLINE or whole.group(1).startswith(("get-config-options", "command -v")):
                self.assign_function(f"{export}{name}", whole.group(1), depth, split=False)
                return
            self.assign_function(f"{export}{name}", whole.group(1), depth, split=False)
            return
        if v in (f"${name}", f'"${name}"', f"${{{name}}}", f'"${{{name}}}"'):
            return  # X=$X (e.g. a parameter declaration)
        if "$?" in v:
            self.emit(depth, "_STATUS = status")
        text = self.words_text(v, depth) if v else ""
        if text and not (text[0] in "\"'" and text[-1] == text[0]) and re.search(r"\s", text):
            text = f'"{text}"'
        self.emit(depth, f"{export}{name} = {text}".rstrip())

    # ------------------------------------------------------ conditions

    def condition(self, cond: str, depth: int) -> str:
        c = cond.strip()
        if c.startswith("! "):
            return f"not ({self.condition(c[2:], depth)})"
        parts = re.split(r"\s+(&&|\|\|)\s+(?=\[\[|\[ |!)", c)
        if len(parts) > 1:
            out = [self.condition(parts[0], depth)]
            for op, part in zip(parts[1::2], parts[2::2]):
                out.append("and" if op == "&&" else "or")
                out.append(f"({self.condition(part, depth)})")
            return " ".join(out)
        m = re.fullmatch(r"\[\[\s+(.*)\s+\]\]|\[\s+(.*)\s+\]", c)
        if not m:
            #  a command: its status
            self.check_command(c)
            line = self.words_text(c, depth)
            return f'ok("{_escape(line)}")'
        return self.test(m.group(1) or m.group(2), depth)

    def test(self, inner: str, depth: int) -> str:
        inner = inner.strip()
        sub = re.split(r"\s+(&&|\|\|)\s+", inner)
        if len(sub) > 1:
            out = [self.test(sub[0], depth)]
            for op, part in zip(sub[1::2], sub[2::2]):
                out += ["and" if op == "&&" else "or", f"({self.test(part, depth)})"]
            return " ".join(out)
        if inner.startswith("! "):
            return f"not ({self.test(inner[2:], depth)})"
        m = re.fullmatch(r"-([dfhLezn])\s+(.+)", inner)
        if m:
            arg = self.operand(m.group(2), depth)
            return {"d": f"is-dir({arg})", "f": f"is-file({arg})", "h": f"is-link({arg})",
                    "L": f"is-link({arg})", "e": f"exists({arg})", "z": f"empty({arg})",
                    "n": f"not empty({arg})"}[m.group(1)]
        words = re.findall(r'"(?:[^"\\]|\\.)*"|\'[^\']*\'|\$\((?:[^()]|\([^()]*\))*\)|\S+', inner)
        if len(words) == 1:
            #  [[ word ]]: true when not empty
            return f"not empty({self.operand(words[0], depth)})"
        if len(words) != 3:
            raise CmdUnliftable(f"unsupported test [[ {inner} ]]")
        left, op, right = words
        if op in ("-eq", "-ne") and left.strip('"') == "$?":
            return f"status {'==' if op == '-eq' else '!='} {right}"
        op = {"=": "==", "-eq": "==", "-ne": "!="}.get(op, op)
        if op not in ("==", "!=", "=~"):
            raise CmdUnliftable(f"unsupported operator {op} in [[ {inner} ]]")
        if op in ("==", "!=") and re.search(r"[*?\[]", right.strip("\"'")) and not right.startswith(("'", '"')):
            raise CmdUnliftable(f"pattern matching in [[ {inner} ]]")
        lv = "status" if left.strip('"') == "$?" else self.operand(left, depth)
        rv = self.operand(right, depth)
        if {lv, rv} == {"$SCBI_HOST", "$TARGET"} and op in ("==", "!="):
            return "cross" if op == "!=" else "not cross"
        result = f"{lv} {op} {rv}"
        try:
            expr.parse(result)
        except expr.ExprError as e:
            raise CmdUnliftable(f"cannot translate [[ {inner} ]]: {e}") from None
        return result

    def operand(self, text: str, depth: int) -> str:
        t = text.strip()
        if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
            t = t[1:-1]
        elif '"' in t and "'" not in t and "\\" not in t and not re.search(r'"[^"]*\s[^"]*"', t):
            #  partly quoted word without blanks: "$PREFIX"/lib
            t = t.replace('"', "")
        t = self.words_text(t, depth)
        if t == "" or re.search(r"[\s()\"'<>=!]", t):
            return '"' + _escape(t) + '"'
        return t

    # ------------------------------------------------------------ main

    def case(self, word: str, lines: list[str], depth: int) -> None:
        """case WORD in pattern) ... ;; esac -> if/elif/else."""
        branches: list[tuple[list[str], list[str]]] = []
        current: list[str] | None = None
        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            if current is None:
                m = re.fullmatch(r"\(?(.+?)\)\s*(.*)", s)
                if not m:
                    raise CmdUnliftable(f"unsupported case pattern {s!r}")
                current = []
                branches.append(([p.strip() for p in m.group(1).split("|")], current))
                s = m.group(2).strip()
                if not s:
                    continue
            if s.endswith(";;"):
                rest = s[:-2].strip()
                if rest:
                    current.append(rest)
                current = None
            else:
                current.append(s)
        operand = self.operand(word, depth)
        first = True
        for patterns, body in branches:
            if patterns == ["*"]:
                header = "else:" if not first else None
            else:
                regex = "|".join(_glob_regex(p) for p in patterns)
                header = f'{"if" if first else "elif"} {operand} =~ "^(?:{regex})$":'
            if header is None:
                #  "*)" alone: unconditional
                self.body(body, depth)
                return
            self.emit(depth, header)
            if body:
                self.body(body, depth + 1)
            else:
                self.emit(depth + 1, "true")
            first = False

    def body(self, lines: list[str], start: int = 0) -> None:
        pos, depth = 0, start
        stack: list[str] = []
        while pos < len(lines):
            raw = lines[pos]
            s = raw.strip()
            pos += 1
            if not s:
                continue
            m = _HEREDOC.match(s)
            if m:
                delim = m.group(5)
                target = m.group(2) or m.group(7)
                mode = m.group(1) or m.group(6)
                if not target:
                    raise CmdUnliftable(f"here-document not written to a file: {s!r}")
                content = []
                while pos < len(lines) and lines[pos].strip() != delim:
                    content.append(lines[pos])
                    pos += 1
                pos += 1
                raw_mode = bool(m.group(4))
                text = "\n".join(content)
                if not raw_mode and ("$(" in text or "`" in text):
                    raise CmdUnliftable("command substitution in a here-document")
                kind = ("append" if mode == ">>" else "write") + ("-raw" if raw_mode else "")
                self.emit(depth, f"{kind} {self.words_text(target, depth)}:")
                margin = min((len(c) - len(c.lstrip()) for c in content if c.strip()), default=0)
                for c in content:
                    self.emit(depth + 1, c[margin:] if c.strip() else "")
                continue
            m = re.fullmatch(r"(if|elif)\s+(.+?);\s*then", s)
            if m:
                if m.group(1) == "elif":
                    depth -= 1
                cond = self.condition(m.group(2), depth)
                self.emit(depth, f"{m.group(1)} {cond}:")
                if m.group(1) == "if":
                    stack.append("if")
                depth += 1
                continue
            if s == "else":
                self.emit(depth - 1, "else:")
                continue
            if s == "fi":
                if not stack or stack.pop() != "if":
                    raise CmdUnliftable("unbalanced fi")
                depth -= 1
                continue
            m = re.fullmatch(r"for\s+([A-Za-z_]\w*)\s+in\s+(.*?)(;\s*do)?;?", s)
            if m:
                if not m.group(3) and pos < len(lines) and lines[pos].strip() == "do":
                    pos += 1
                self.emit(depth, f"for {m.group(1)} in {self.words_text(m.group(2), depth)}:")
                stack.append("for")
                depth += 1
                continue
            if s == "done":
                if not stack or stack.pop() != "for":
                    raise CmdUnliftable("unbalanced done")
                depth -= 1
                continue
            #  a sub-shell, printed "( first" ... "last )" by declare -f
            if s == "(" or s.startswith("( "):
                stack.append("(")
                s = s[1:].strip()
                if not s:
                    continue
            if stack and stack[-1] == "(" and (s == ")" or s.endswith(" )")):
                stack.pop()
                if any(ln.strip() for ln in lines[pos:]):
                    #  a sub-shell isolates the directory and variables
                    #  of the following steps: no equivalent
                    raise CmdUnliftable("sub-shell followed by other steps")
                s = s[:-1].strip()
                if s:
                    self.command(s, depth)
                continue
            m = re.fullmatch(r"case\s+(.+?)\s+in", s)
            if m:
                start = pos
                level = 1
                while pos < len(lines):
                    t = lines[pos].strip()
                    if re.match(r"case\s.*\sin$", t):
                        level += 1
                    elif t == "esac":
                        level -= 1
                        if level == 0:
                            break
                    pos += 1
                if pos >= len(lines):
                    raise CmdUnliftable("unterminated case")
                self.case(m.group(1), lines[start:pos], depth)
                pos += 1
                continue
            first = s.split()[0]
            if first in ("while", "until", "case", "(", "{", "}") or s.startswith(("(", "{")):
                raise CmdUnliftable(f"unsupported construct {first!r}")
            self.command(s, depth)
        if stack:
            raise CmdUnliftable("unterminated block")


_CP = re.compile(r"cp(?:\s+-[rR])?\s+(\S.*)")


def _cp_to_copy(text: str) -> str:
    """``cp [-r|-R] SOURCE... DEST`` commands of a lifted line (not in a
    pipeline, no other option, no redirection) as the built-in ``copy``."""
    if re.search(r"(?<!\|)\|(?!\|)", text):
        return text
    parts = re.split(r"(\s*(?:&&|\|\|)\s*)", text)
    for i in range(0, len(parts), 2):
        m = _CP.fullmatch(parts[i])
        if m and not re.search(r"(^|\s)-|[<>]", m.group(1)):
            parts[i] = f"copy {m.group(1)}"
    return "".join(parts)


_GPRBUILD_PROJECT = re.compile(r"(^|&&|\|\||\|)(\s*)gprbuild-project\s+(\S+)")


def _gprbuild_project(text: str) -> str:
    """The Bash runtime function ``gprbuild-project PRJ`` as the external
    command it runs (the built-in was removed)."""
    return _GPRBUILD_PROJECT.sub(
        lambda m: f"{m[1]}{m[2]}gprbuild -p -q $(if cross then --target=$TARGET) {m[3]}"
                  " -cargs -gnatwA > /dev/null 2>&1", text)


def _glob_regex(pattern: str) -> str:
    """A case pattern (glob) as a regular expression."""
    p = pattern.strip("\"'")
    out = []
    for c in p:
        out.append(".*" if c == "*" else "." if c == "?" else re.escape(c))
    return "".join(out)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _and_groups(lines: list[str]) -> list[str]:
    """``COND && {`` ... ``}`` [``|| true``] as ``if COND; then`` ... ``fi``
    (the group on its own lines, the ``{`` on the COND line or the next
    one)."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
        cond = None
        if s.endswith("&& {"):
            cond, body = s[: -len("&& {")].strip(), i + 1
        elif s.endswith("&&") and i + 1 < len(lines) and lines[i + 1].strip() == "{":
            cond, body = s[:-2].strip(), i + 2
        if cond is None:
            out.append(lines[i])
            i += 1
            continue
        depth, j = 1, body
        while j < len(lines):
            t = lines[j].strip()
            if t == "{" or t.endswith("&& {"):
                depth += 1
            elif re.fullmatch(r"\}(\s*\|\|\s*(true|:))?;?", t):
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= len(lines):
            raise CmdUnliftable(f"unterminated group after {s!r}")
        out.append(f"{indent}if {cond}; then")
        out += _and_groups(lines[body:j])
        out.append(f"{indent}fi")
        i = j + 1
    return out


def lift_commands(lines: list[str], params: dict[int, str] | None = None) -> str:
    """The command language text of a Bash body (``body_lines`` without
    the parameter declarations); ``params``: $n -> name for functions."""
    lifter = _Lifter({str(n): name for n, name in (params or {}).items()})
    lifter.body(_and_groups(lines))
    text = "\n".join(lifter.out) + ("\n" if lifter.out else "")
    try:
        parse(text)
    except CmdSyntaxError as e:
        raise CmdUnliftable(f"internal: {e}") from None
    return text
