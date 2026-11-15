"""Canonical writer of YAML plug-ins (scbi format, scbi.convert).

The canonical form:
- keys in the order of catalog.FORMAT_ORDER; inside a hook the
  qualifiers ``_``, ``common``, ``default``, the variants (alphabetical),
  then ``cross``; the fields of vcs/archive in their order;
- block style, mappings indented by 2, list items "  - " under their key;
  multi-line strings as literal blocks; scalars quoted only when needed;
- one blank line between the top-level keys, none inside.

Comments are kept: a comment line goes with the key or list item it
precedes (it moves with it when the keys are reordered), an end-of-line
comment with the key or item of its line; the comments before the first
key separated from it by a blank line stay at the top of the file, those
after the last key at the end. Comments are located with the line numbers
of the YAML nodes (PyYAML composer); the lines of literal blocks are
content, not comments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from scbi.plugin import catalog, construct, yamlfmt

QUALIFIER_RANK = {yamlfmt.PLAIN_KEY: 0, "common": 1, "default": 2}
INHERIT_ORDER = ("from", "hooks", "custom-hooks", "no-variant", "name")
FUNCTION_ORDER = ("params", "run")
OS_VARIANT_ORDER = ("packages", "env")


class WriteError(Exception):
    pass


@dataclass
class Comments:
    header: list[str] = field(default_factory=list)  # top of the file
    footer: list[str] = field(default_factory=list)  # end of the file
    before: dict[tuple, list[str]] = field(default_factory=dict)  # path -> lines
    inline: dict[tuple, str] = field(default_factory=dict)  # path -> "# ..."


# ------------------------------------------------------------ comments


def _inline_comment(line: str) -> str | None:
    """The end-of-line comment of a YAML line (outside quotes)."""
    quote = None
    for i, c in enumerate(line):
        if quote:
            if c == quote:
                quote = None
        elif c in "'\"" and (i == 0 or line[i - 1] in " \t:-[{,"):
            quote = c
        elif c == "#" and i > 0 and line[i - 1] in " \t":
            return line[i:].rstrip()
    return None


def _anchors(node, path: tuple, out: dict, blocks: list) -> None:
    """Line -> path of the keys and list items; ranges of block scalars."""
    if isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            p = path + (k.value,)
            out.setdefault(k.start_mark.line, p)
            _anchors(v, p, out, blocks)
    elif isinstance(node, yaml.SequenceNode):
        for i, item in enumerate(node.value):
            p = path + (i,)
            out.setdefault(item.start_mark.line, p)
            _anchors(item, p, out, blocks)
    elif isinstance(node, yaml.ScalarNode) and node.style in ("|", ">"):
        #  the lines of the block, after its indicator line
        blocks.append((node.start_mark.line + 1, node.end_mark.line))


def collect_comments(text: str) -> Comments:
    node = yaml.compose(text, Loader=yamlfmt._Loader)
    result = Comments()
    if node is None:
        result.header = [ln.rstrip() for ln in text.splitlines() if ln.strip().startswith("#")]
        return result
    anchors: dict[int, tuple] = {}
    blocks: list[tuple[int, int]] = []
    _anchors(node, (), anchors, blocks)

    def in_block(n: int) -> bool:
        return any(a <= n < b for a, b in blocks)

    lines = text.splitlines()
    first = min(anchors) if anchors else len(lines)
    pending: list[str] = []
    blank_after_pending = False
    last_anchor: tuple | None = None
    for n, line in enumerate(lines):
        if in_block(n):
            continue
        stripped = line.strip()
        if not stripped:
            if pending:
                blank_after_pending = True
            continue
        if stripped.startswith("#"):
            if n < first and blank_after_pending:
                result.header += pending
                pending = []
            blank_after_pending = False
            pending.append(stripped)
            continue
        if n <= first and pending and blank_after_pending:
            result.header += pending
            pending = []
        anchor = anchors.get(n)
        if anchor is not None:
            if pending:
                result.before.setdefault(anchor, []).extend(pending)
                pending = []
            last_anchor = anchor
        blank_after_pending = False
        comment = _inline_comment(line)
        if comment:
            target = anchor if anchor is not None else last_anchor
            if target is not None:
                result.inline[target] = comment
    result.footer = pending
    return result


# ------------------------------------------------------------ ordering


def _top_rank(key: str) -> tuple:
    return (catalog.format_rank(key), key)


def _qualifier_rank(key: str) -> tuple:
    if key == yamlfmt.CROSS_KEY:
        return (4, "")
    return (QUALIFIER_RANK.get(key, 3), key)


def _ordered(items: list, rank) -> list:
    return sorted(items, key=lambda kv: rank(str(kv[0])))


def _field_order(order: tuple):
    def rank(key: str) -> tuple:
        return (order.index(key) if key in order else len(order), key)
    return rank


def _keys_order(path: tuple, value: dict):
    """How the keys of the mapping at ``path`` are ordered (None: as is)."""
    if not path:
        return _top_rank
    top = str(path[0])
    if top in ("vars", "variants"):
        return None
    if top == "functions":
        return _field_order(FUNCTION_ORDER) if len(path) == 2 else None
    if top == "with-variants":
        return _field_order(OS_VARIANT_ORDER) if len(path) == 2 else None
    if top == "inherit":
        return _field_order(INHERIT_ORDER)
    if construct.is_record(top, value):
        return _field_order(construct.RECORDS[top])
    if catalog.is_hook(top) and yamlfmt._is_qualifier_map(top, value):
        return _qualifier_rank
    return None


# ------------------------------------------------------------ emitter


def _scalar(value: str) -> str:
    """A single-line scalar, quoted when needed (PyYAML)."""
    if value == "":
        return "''"
    text = yaml.dump(value, Dumper=yamlfmt._Dumper, width=100000, allow_unicode=True)
    text = text[:-len("\n...\n")] if text.endswith("\n...\n") else text.rstrip("\n")
    if "\n" in text:
        raise WriteError(f"cannot write {value!r} on a single line")
    return text


def _literal(value: str, indent: int) -> list[str]:
    """A multi-line string as a literal block, [] when it cannot be one
    (leading blank, several final newlines, trailing blanks in a line:
    written as a quoted scalar then)."""
    if value.startswith((" ", "\t", "\n")) or value.endswith("\n\n"):
        return []
    chomp = "" if value.endswith("\n") else "-"
    lines = (value[:-1] if value.endswith("\n") else value).split("\n")
    if any(line != line.rstrip() for line in lines):
        return []
    pad = " " * indent
    return [f"|{chomp}"] + [(pad + line) if line else "" for line in lines]


class _Writer:
    def __init__(self, comments: Comments):
        self.c = comments
        self.out: list[str] = []

    def comments_before(self, path: tuple, indent: int) -> None:
        for line in self.c.before.get(path, []):
            self.out.append(" " * indent + line)

    def inline(self, path: tuple) -> str:
        comment = self.c.inline.get(path)
        return f"  {comment}" if comment else ""

    def value(self, prefix: str, value, path: tuple, indent: int) -> None:
        """``prefix`` ("key:" or "-") then the value."""
        if isinstance(value, dict):
            if not value:
                self.out.append(f"{prefix} {{}}{self.inline(path)}")
                return
            self.out.append(f"{prefix}{self.inline(path)}")
            self.mapping(value, path, indent + 2)
        elif isinstance(value, list):
            if not value:
                self.out.append(f"{prefix} []{self.inline(path)}")
                return
            self.out.append(f"{prefix}{self.inline(path)}")
            self.sequence(value, path, indent + 2)
        else:
            text = "" if value is None else str(value)
            if "\n" in text:
                block = _literal(text, indent + 2)
                if block:
                    self.out.append(f"{prefix} {block[0]}{self.inline(path)}")
                    self.out.extend(block[1:])
                    return
                quoted = yaml.dump(text, Dumper=yaml.SafeDumper, default_style='"', width=100000)
                quoted = quoted[:-len("\n...\n")] if quoted.endswith("\n...\n") else quoted.rstrip("\n")
                self.out.append(f"{prefix} {quoted}{self.inline(path)}")
                return
            self.out.append(f"{prefix} {_scalar(text)}{self.inline(path)}")

    def mapping(self, data: dict, path: tuple, indent: int, top: bool = False) -> None:
        items = list(data.items())
        rank = _keys_order(path, data)
        if rank is not None:
            items = _ordered(items, rank)
        pad = " " * indent
        for i, (k, v) in enumerate(items):
            p = path + (k,)
            if top and i > 0:
                self.out.append("")
            self.comments_before(p, indent)
            self.value(f"{pad}{_scalar(str(k))}:", v, p, indent)

    def sequence(self, data: list, path: tuple, indent: int) -> None:
        pad = " " * indent
        for i, item in enumerate(data):
            p = path + (i,)
            self.comments_before(p, indent)
            if isinstance(item, dict) and item:
                #  "- key: value" then the other keys aligned
                items = list(item.items())
                rank = _keys_order(path, item)
                if rank is not None:
                    items = _ordered(items, rank)
                first = True
                for k, v in items:
                    kp = p + (k,)
                    lead = f"{pad}- " if first else f"{pad}  "
                    if not first:
                        self.comments_before(kp, indent + 2)
                    start = len(self.out)
                    self.value(f"{lead}{_scalar(str(k))}:", v, kp, indent + 2)
                    if first and self.c.inline.get(p) and not self.c.inline.get(kp):
                        self.out[start] += f"  {self.c.inline[p]}"
                    first = False
            else:
                self.value(f"{pad}-", item, p, indent)


def write(data: dict, comments: Comments | None = None) -> str:
    """The canonical text of the plug-in ``data``."""
    w = _Writer(comments or Comments())
    if w.c.header:
        w.out += w.c.header + [""]
    w.mapping(data, (), 0, top=True)
    if w.c.footer:
        w.out += [""] + w.c.footer
    text = "\n".join(line.rstrip() for line in w.out) + "\n"
    return re.sub(r"\n{3,}", "\n\n", text)


def load_data(text: str):
    return yaml.load(text, Loader=yamlfmt._Loader)


def format_text(name: str, text: str) -> str:
    """The canonical form of the YAML plug-in ``name`` (its text). Raises
    yamlfmt.FormatError for an invalid plug-in, WriteError if the result
    would not hold the same data."""
    try:
        data = load_data(text) or {}
    except yaml.YAMLError as e:
        raise yamlfmt.FormatError(f"{name}: {' '.join(str(e).split())}") from None
    if not isinstance(data, dict):
        raise yamlfmt.FormatError(f"{name}: a mapping is expected")
    yamlfmt.from_data(name, data, name)
    result = write(data, collect_comments(text))
    if load_data(result) != data:
        raise WriteError(f"{name}: internal error, the formatted plug-in differs")
    return result
