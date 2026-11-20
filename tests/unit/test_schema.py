"""The JSON Schema of the YAML plug-ins (scbi.plugin.schema)."""

import pytest
import yaml

from corpus import REPO_ROOT, yaml_plugin_files
from scbi.plugin import catalog, yamlfmt
from scbi.plugin.schema import schema

jsonschema = pytest.importorskip("jsonschema")


@pytest.fixture(scope="module")
def validator():
    s = schema()
    jsonschema.Draft7Validator.check_schema(s)
    return jsonschema.Draft7Validator(s)


def test_every_key_described():
    props = schema()["properties"]
    for key in list(catalog.step_names()) + list(catalog.HEADER_KEYS):
        assert props[key]["description"], key


def test_plugins_valid(validator):
    """The plug-ins of the repository and of the tests are valid."""
    files = yaml_plugin_files() + sorted((REPO_ROOT / "tests" / "scripts.d").glob("[!.]*.yaml"))
    assert len(files) > 250
    for f in files:
        data = yaml.load(f.read_text(), Loader=yamlfmt._Loader)
        assert [e.message for e in validator.iter_errors(data)] == [], f


@pytest.mark.parametrize("data", [
    {"inherit": [{"hooks": ["config"]}]},             # from is mandatory
    {"config": ["make"]},                             # commands: a string
    {"depends": ["a", {"cross": "b"}]},               # a mapping item: guarded only
    {"functions": {"f": {"params": ["A"]}}},          # run is mandatory
    {"with-variants": {"native": {"package": ["x"]}}},
])
def test_invalid(validator, data):
    assert list(validator.iter_errors(data))


def test_build_target(validator):
    #  build-<target>, but build-depends is not one
    props = schema()["patternProperties"]
    [pattern] = props
    import re
    assert re.search(pattern, "build-doc") and not re.search(pattern, "build-depends")
    assert not list(validator.iter_errors({"build-doc": "make doc", "build-depends": ["x"]}))
