"""Translation of guard conditions (scbi.plugin.expr) to Bash.

Hooks of plug-in definitions run in a Bash shell (when called from Bash code, e.g. by
``plugin-call-env-hooks`` from a user hook) are rendered as Bash functions;
their guards are translated to Bash conditions using the runtime helpers,
so that they are evaluated when the hook is called, with its arguments,
exactly like the Python evaluation (scbi.hooks.evaluate) does.

Operands:
    ref         $REF if set, else $(get-version)
    target      $TARGET (hook parameter) else $SCBI_TARGET
    host        $SCBI_HOST
    variant     $VARIANT
    kind        $KIND
    cross       [[ $SCBI_HOST != $SCBI_TARGET ]]
    version(m)  $(get-module-version m)
    build-type(K[,D])  $(get-build-type K D)
    enabled(f)  is-enabled f
    exists(p)   [[ -e p ]] (or a symbolic link)
    dir(m)      get-target-dir m default
    on d1,d2    has-discriminant d1 && has-discriminant d2
"""

from __future__ import annotations

from scbi.plugin import expr


def _q(text: str) -> str:
    """Double quoted Bash word keeping $ expansions (text of a definition)."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`") + '"'


def _value(node) -> str:
    """Bash word for an operand used as a value."""
    if isinstance(node, expr.Lit):
        return _q(node.value)
    if isinstance(node, expr.Var):
        return {
            "ref": '"${REF:-$(get-version)}"',
            "target": '"${TARGET:-$SCBI_TARGET}"',
            "host": '"$SCBI_HOST"',
            "variant": '"$VARIANT"',
            "kind": '"$KIND"',
            "cross": '"$([[ $SCBI_HOST != $SCBI_TARGET ]] && echo true || echo false)"',
        }[node.name]
    if isinstance(node, expr.Call):
        arg = node.arg
        if node.name == "version":
            return f'"$(get-module-version {_q(arg)})"'
        if node.name == "build-type":
            kind, _, default = arg.partition(",")
            return f'"$(get-build-type {_q(kind)} {_q(default)})"'
        if node.name == "enabled":
            return f'"$(is-enabled {_q(arg)} >/dev/null && echo true || echo false)"'
        if node.name == "exists":
            p = _q(arg)
            return f'"$([[ -e {p} || -L {p} ]] && echo true || echo false)"'
        if node.name == "dir":
            return f'"$(__scbi_d=; get-target-dir __scbi_d {_q(arg)} default; echo "$__scbi_d")"'
    if isinstance(node, expr.On):
        return f'"$({_cond(node)} && echo true || echo false)"'
    #  a nested condition used as a value
    return f'"$({_cond(node)} && echo true || echo false)"'


def _cond(node) -> str:
    """Bash command list true when ``node`` is true."""
    if isinstance(node, expr.BoolOp):
        op = " && " if node.op == "and" else " || "
        return "{ " + op.join(_cond(i) for i in node.items) + "; }"
    if isinstance(node, expr.Not):
        return f"! {_cond(node.expr)}"
    if isinstance(node, expr.On):
        if not node.discs:
            return "true"
        return "{ " + " && ".join(f"has-discriminant {_q(d)}" for d in node.discs) + "; }"
    if isinstance(node, expr.Cmp):
        left, right = _value(node.left), _value(node.right)
        if node.op == "=~":
            return f'{{ __scbi_re={right}; [[ {left} =~ $__scbi_re ]]; }}'
        if node.op in ("==", "!="):
            return f"[[ {left} {node.op} {right} ]]"
        return f"check-versions {left} '{node.op}' {right}"
    if isinstance(node, expr.Var) and node.name == "cross":
        return "[[ $SCBI_HOST != $SCBI_TARGET ]]"
    if isinstance(node, expr.Call) and node.name == "enabled":
        return f"is-enabled {_q(node.arg)} >/dev/null"
    if isinstance(node, expr.Call) and node.name == "exists":
        p = _q(node.arg)
        return f"[[ -e {p} || -L {p} ]]"
    #  any other operand (string): true when not empty
    return f"[[ -n {_value(node)} ]]"


def to_bash(cond: str) -> str:
    """Bash condition (command list) for the guard ``cond``."""
    return _cond(expr.parse(cond))
