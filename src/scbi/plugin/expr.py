"""Guard conditions of plug-in values and environment actions.

A list item of a value or env hook can be guarded::

    patches:
      - fix-common.diff
      - if ref =~ ^7.8: fix-7.8.diff
      - if version(lib2) > 1.9: [a.diff, b.diff]

Grammar (evaluated by Python, no shell involved)::

    expr    := and ("or" and)*
    and     := not ("and" not)*
    not     := "not" not | cmp
    cmp     := operand [OP operand]        OP: == != < > <= >= =~
    operand := "(" expr ")"
             | "on" WORD                   discriminants, comma separated
             | NAME "(" WORD ")"           version(m) build-type(K) enabled(f)
                                           exists(path) dir(m); in command
                                           hooks also is-dir(p) is-file(p)
                                           is-link(p) empty(v) ok("command")
             | NAME                        ref target host variant kind cross
                                           (status in command hooks)
             | WORD | "quoted string"

``< > <= >=`` compare versions (as ``check-module-version``), ``=~`` is a
regular expression search, ``== !=`` compare strings. An operand alone is
true when it is a true boolean or a non-empty string.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from scbi.vercmp import check_versions

OPERATORS = ("==", "!=", "<=", ">=", "<", ">", "=~")
VARIABLES = ("ref", "target", "host", "variant", "kind", "cross", "status")
FUNCTIONS = ("version", "build-type", "enabled", "exists", "dir",
             #  command hooks (scbi.hooks.cmdlang)
             "is-dir", "is-file", "is-link", "empty", "ok")


class ExprError(Exception):
    pass


class Context(Protocol):
    """Values a condition can refer to (provided by the driver)."""

    def variable(self, name: str) -> str | bool: ...

    def function(self, name: str, arg: str) -> str | bool: ...

    def has_discriminants(self, discs: list[str]) -> bool: ...

    def expand(self, value: str) -> str: ...


# ------------------------------------------------------------------- AST


@dataclass(frozen=True)
class Lit:
    value: str


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Call:
    name: str
    arg: str


@dataclass(frozen=True)
class On:
    discs: tuple[str, ...]


@dataclass(frozen=True)
class Cmp:
    op: str
    left: object
    right: object


@dataclass(frozen=True)
class Not:
    expr: object


@dataclass(frozen=True)
class BoolOp:
    op: str  # "and" | "or"
    items: tuple


# ----------------------------------------------------------------- parser

_TOKEN = re.compile(
    r"""\s*(?:
        (?P<str>"(?:[^"\\]|\\.)*"|'[^']*')
      | (?P<op>==|!=|<=|>=|=~|<|>)
      | (?P<punct>[()])
      | (?P<word>[^\s()"'<>=!]+(?:[=!][^\s()"'<>=!]+)*)
    )""",
    re.X,
)


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens = []
    pos = 0
    text = text.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ExprError(f"invalid condition near {text[pos:]!r}")
        kind = m.lastgroup
        value = m.group(kind)
        if kind == "str":
            value = value[1:-1].replace('\\"', '"') if value[0] == '"' else value[1:-1]
        tokens.append((kind, value))
        pos = m.end()
        while pos < len(text) and text[pos].isspace():
            pos += 1
    return tokens


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.tokens = _tokenize(text)
        self.pos = 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def next(self) -> tuple[str, str]:
        tok = self.peek()
        if tok is None:
            raise ExprError(f"unexpected end of condition: {self.text!r}")
        self.pos += 1
        return tok

    def accept(self, kind: str, value: str | None = None) -> bool:
        tok = self.peek()
        if tok and tok[0] == kind and (value is None or tok[1] == value):
            self.pos += 1
            return True
        return False

    def parse(self):
        e = self.or_()
        if self.peek() is not None:
            raise ExprError(f"unexpected {self.peek()[1]!r} in condition {self.text!r}")
        return e

    def or_(self):
        items = [self.and_()]
        while self.accept("word", "or"):
            items.append(self.and_())
        return items[0] if len(items) == 1 else BoolOp("or", tuple(items))

    def and_(self):
        items = [self.not_()]
        while self.accept("word", "and"):
            items.append(self.not_())
        return items[0] if len(items) == 1 else BoolOp("and", tuple(items))

    def not_(self):
        if self.accept("word", "not"):
            return Not(self.not_())
        return self.cmp()

    def cmp(self):
        left = self.operand()
        tok = self.peek()
        if tok and tok[0] == "op":
            self.pos += 1
            right = self.operand(rhs=True)
            return Cmp(tok[1], left, right)
        return left

    def operand(self, rhs: bool = False):
        kind, value = self.next()
        if kind == "punct" and value == "(":
            e = self.or_()
            if not self.accept("punct", ")"):
                raise ExprError(f"missing ')' in condition {self.text!r}")
            return e
        if kind == "str":
            return Lit(value)
        if kind != "word":
            raise ExprError(f"unexpected {value!r} in condition {self.text!r}")
        if rhs:
            return Lit(value)
        if value == "on":
            _, discs = self.next()
            return On(tuple(d for d in discs.split(",") if d))
        if value in FUNCTIONS and self.accept("punct", "("):
            kind2, arg = self.next()
            if not self.accept("punct", ")"):
                raise ExprError(f"missing ')' after {value}( in {self.text!r}")
            return Call(value, arg)
        if value in VARIABLES:
            return Var(value)
        return Lit(value)


def parse(text: str):
    """Parse a condition, raising ExprError on syntax errors."""
    return _Parser(text).parse()


# -------------------------------------------------------------- evaluation


def _value(node, ctx: Context) -> str | bool:
    if isinstance(node, Lit):
        return ctx.expand(node.value)
    if isinstance(node, Var):
        return ctx.variable(node.name)
    if isinstance(node, Call):
        return ctx.function(node.name, ctx.expand(node.arg))
    if isinstance(node, On):
        return ctx.has_discriminants(list(node.discs))
    return evaluate_node(node, ctx)


def _truth(v: str | bool) -> bool:
    return v if isinstance(v, bool) else v != ""


def _str(v: str | bool) -> str:
    return ("true" if v else "false") if isinstance(v, bool) else v


def evaluate_node(node, ctx: Context) -> bool:
    if isinstance(node, BoolOp):
        if node.op == "and":
            return all(evaluate_node(i, ctx) for i in node.items)
        return any(evaluate_node(i, ctx) for i in node.items)
    if isinstance(node, Not):
        return not evaluate_node(node.expr, ctx)
    if isinstance(node, Cmp):
        left, right = _str(_value(node.left, ctx)), _str(_value(node.right, ctx))
        if node.op == "=~":
            return re.search(right, left) is not None
        if node.op == "==":
            return left == right
        if node.op == "!=":
            return left != right
        return check_versions(left, node.op, right)
    return _truth(_value(node, ctx))


def evaluate(text: str, ctx: Context) -> bool:
    return evaluate_node(parse(text), ctx)
