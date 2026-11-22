"""The JSON Schema of the YAML plug-ins (``scbi schema``), for the editors:
completion of the hook names and of the keys of the records, help on
hover, structure checks.

Generated from the catalog of the hooks (scbi.plugin.catalog) and the
records (scbi.plugin.construct). It is permissive (the bodies are
strings, the guarded items any mapping with an ``if`` key): the checks
of the content are those of ``scbi lint``. Unknown keys are allowed too
(``scbi lint`` reports them, with the closest hook name).
"""

from __future__ import annotations

from scbi.plugin import catalog, construct

SCHEMA_ID = "https://github.com/TurboGit/scbi/plugin.schema.json"

_STRING_LIST = {"type": "array", "items": {"type": "string"}}

#  an item guarded by a condition: {"if <condition>": item | [items]}
_GUARDED = {
    "type": "object",
    "minProperties": 1,
    "maxProperties": 1,
    "propertyNames": {"pattern": "^if "},
}


def _list_body(item: dict) -> dict:
    """A list of items (or a single one), items possibly guarded."""
    one = {"anyOf": [item, {"$ref": "#/definitions/guarded"}]}
    return {"anyOf": [one, {"type": "array", "items": one}]}


def _value_body(hook: str) -> dict:
    scalar = {"type": ["string", "number", "boolean"]}
    body = _list_body(scalar)
    choices = {"out-of-tree": ["true", "false"], "only-explicit-build": ["true", "false"],
               "aggregate": ["direct", "recursive", "no"],
               "propagate-version": ["version", "variant", "both", "no"]}
    if hook in choices:
        body = {"anyOf": [{"enum": choices[hook] + ([True, False] if "true" in choices[hook] else [])}, body]}
    if hook in construct.RECORDS:
        fields = construct.RECORDS[hook]
        record = {
            "type": "object",
            "properties": {f: {"type": "string"} for f in fields},
            "required": list(fields[: construct.RECORD_MIN[hook]]),
            "additionalProperties": False,
        }
        body = {"anyOf": [record, body]}
    return body


_SOURCE_ENTRY = {
    "type": "object",
    "minProperties": 1,
    "additionalProperties": False,
    "properties": {
        "from": {"type": "string", "description": "A dependency of the module (depends, build-depends) whose"
                                                  " sources are copied; none: the sources of this module."},
        "to": {"type": "string", "description": "The target in the source tree of the build (default .)."},
        "exclude": {"anyOf": [{"type": "string"}, _STRING_LIST],
                    "description": "Paths relative to the root of the sources, not copied."},
    },
}


def _body(hook: str) -> dict:
    if hook == "source-tree":
        return _list_body(_SOURCE_ENTRY)
    kind = catalog.spec(hook).kind
    if kind == catalog.COMMAND:
        return {"type": "string"}
    if kind == catalog.VALUE:
        return _value_body(hook)
    return _list_body({"type": "string"})


def _hook(hook: str) -> dict:
    """A hook: its body, or a mapping of qualifiers (the plain one ``_``, a
    variant, ``default``, ``common`` for a cumulative hook, ``cross``)."""
    spec = catalog.spec(hook)
    body = _body(hook)
    qualifiers: dict = {
        construct.DEFAULT: {**body, "description": "The hook of the default variant."},
        "_": {**body, "description": "The plain hook (no variant)."},
        "cross": {"description": "The hooks used when cross-compiling.",
                  "anyOf": [body, {"type": "object", "additionalProperties": body}]},
    }
    if spec.cumulative:
        qualifiers[construct.COMMON] = {**body, "description": "Used whatever the variant."}
    qualified = {"type": "object", "properties": qualifiers, "additionalProperties": body}
    params = " ".join(f"${p}" for p in spec.params) or "none"
    text = catalog.description(hook)
    kind = {"command": "commands", "value": "values", "env": "environment actions"}[spec.kind]
    more = f"{kind}; parameters: {params}" + ("; cumulative (common, then each variant)" if spec.cumulative else "")
    return {
        "description": f"{text}\n({more})",
        "markdownDescription": f"{text}\n\n*{more}*",
        "anyOf": [body, qualified],
    }


def schema() -> dict:
    """The JSON Schema (draft-07) of a YAML plug-in."""
    props: dict = {
        "plugin": {"type": "string", "description": catalog.description("plugin")},
        "vars": {"type": "object", "description": catalog.description("vars"),
                 "additionalProperties": {"type": ["string", "number", "boolean", "null"]}},
        "variants": {"type": "object", "description": catalog.description("variants"),
                     "additionalProperties": _STRING_LIST},
        "inherit": {
            "type": "array", "description": catalog.description("inherit"),
            "items": {"type": "object", "required": ["from"], "additionalProperties": False,
                      "properties": {"from": {"type": "string"}, "hooks": _STRING_LIST,
                                     "custom-hooks": _STRING_LIST,
                                     "no-variant": {"type": ["boolean", "string"]},
                                     "name": {"type": "string"}}},
        },
        "with-variants": {
            "type": "object", "description": catalog.description("with-variants"),
            "additionalProperties": {
                "type": ["object", "null"], "additionalProperties": False,
                "properties": {"packages": _STRING_LIST, "env": _list_body({"type": "string"})}},
        },
        "functions": {
            "type": "object", "description": catalog.description("functions"),
            "additionalProperties": {"anyOf": [
                {"type": "string"},
                {"type": "object", "required": ["run"], "additionalProperties": False,
                 "properties": {"params": _STRING_LIST, "run": {"type": "string"}}}]},
        },
    }
    for hook in catalog.step_names():
        props[hook] = _hook(hook)
    #  build-<target>, not a hook (build-depends, build-env)
    others = "|".join(h[len("build-"):] for h in catalog.HOOKS if h.startswith("build-"))
    target = f"^build-(?!({others})$)[A-Za-z0-9_]+(-[A-Za-z0-9_]+)*$"
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": SCHEMA_ID,
        "title": "SCBI plug-in",
        "type": "object",
        "definitions": {"guarded": _GUARDED},
        "properties": props,
        "patternProperties": {target: {**_hook("build-target"),
                                       "description": "The build step run for --build-target=<target>.",
                                       "markdownDescription": "The build step run for `--build-target=<target>`."}},
    }
