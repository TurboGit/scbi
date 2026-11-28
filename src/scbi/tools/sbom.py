"""scbi show --json / --sbom: the modules of a build and their
dependencies, machine-readable.

--json is the graph in the format of SCBI (documented in doc/scbi.tex,
"Show"); --sbom is a software bill of materials in the CycloneDX 1.5 JSON
format, for the audit and vulnerability tools.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid

from scbi.sources.data import archive_data, display_ref, vcs_data
from scbi.tools.planwalk import ROOT, Node, root_modules, source_ref, walk

#  format of scbi show --json (incremented on an incompatible change)
JSON_FORMAT = 1


def _public_url(url: str) -> str:
    """The URL without its credentials (user:password@)."""
    return re.sub(r"^([a-z][a-z0-9+.-]*://)[^/@]*@", r"\1", url)


def node_id(node: Node) -> str:
    if node.external:
        return f"os:{node.module}"
    return ("host@" if node.host else "") + node.plan_key


def _source(driver, builder, node: Node) -> dict | None:
    """The origin of the sources of a module: from the last build when
    recorded, else from its vcs or archive hook."""
    if node.meta or node.variant == "native":
        return None
    sr = source_ref(driver, node.module)
    if (sr is not None and sr.origin == "archive") or (sr is None and node.kind == "VERSION"):
        version = sr.ref if sr is not None else node.version
        data, rc = archive_data(builder, node.module, node.variant, version)
        src: dict = {"type": "archive", "version": version}
        if rc == 0 and len(data) >= 6:
            src["url"] = _public_url(data[4])
            src["file"] = data[5]
        if sr is not None and sr.id and sr.id != "NONE":
            src["sha1"] = sr.id
        path = os.path.join(driver.get("SCBI_ARCHIVES"), src.get("file", ""))
        if src.get("file") and os.path.isfile(path):
            from scbi.sources.archive.fetch import file_sha256

            src["sha256"] = file_sha256(path)
        return src
    data, rc = vcs_data(builder, node.module, node.variant)
    if rc != 0 or len(data) < 5 or data[3].upper() == "NONE":
        return None
    name = data[3]
    src = {"type": {"hg": "mercurial", "svn": "subversion"}.get(name, name),
           "url": _public_url(data[4]),
           "ref": "dev" if node.kind == "DEV" else display_ref(name, node.version)}
    if sr is not None and sr.origin != "none":
        src["ref"] = sr.ref
        if sr.id:
            src["revision"] = sr.id
    return src


def _license(builder, node: Node) -> str:
    if node.external:
        return ""
    try:
        value = builder.hook_value(node.module, node.variant, "license") or ""
    except Exception:  # noqa: BLE001 - a broken hook: no license reported
        return ""
    return " ".join(value.split())


def graph(driver, builder) -> tuple[dict, int]:
    """The graph of the build (the --json document)."""
    from scbi.walker import get_pkg_version

    roots = root_modules(driver)
    nodes, status = walk(driver, builder, roots)
    if status != 0:
        return {}, 1
    #  a plug-in name -> the id of its node (the parents are plug-in names)
    by_name: dict[str, str] = {}
    for n in nodes:
        if not n.external and not n.host:
            by_name.setdefault(n.module, node_id(n))
    depends: dict[str, list[dict]] = {}
    for n in nodes:
        for parent, kind in n.parents:
            if parent == ROOT:
                continue
            pid = by_name.get(parent, parent)
            entry = {"id": node_id(n), "kind": kind}
            if entry not in depends.setdefault(pid, []):
                depends[pid].append(entry)

    modules = []
    for n in nodes:
        nid = node_id(n)
        m: dict = {"id": nid, "name": n.module}
        if n.external:
            m["type"] = "os-package"
            m["version"] = get_pkg_version(driver, n.module)
        else:
            m["type"] = "meta-module" if n.meta else "module"
            m["variant"] = n.variant
            m["version"] = "" if n.version == "NONE" else ("#" if n.kind == "VERSION" else "") + n.version
            if n.host:
                m["host"] = True
            if "=" in n.plan_key:
                m["for"] = n.plan_key.split("=", 1)[0]
            m["license"] = _license(builder, n) or None
            m["source"] = _source(driver, builder, n)
            m["built"] = source_ref(driver, n.module) is not None or n.meta
        m["root"] = (ROOT, "default") in n.parents and not n.external
        m["depends"] = depends.get(nid, [])
        modules.append(m)

    doc = {
        "format": JSON_FORMAT,
        "plan": driver.get("SCBI_PLAN") or None,
        "target": driver.get("SCBI_TARGET"),
        "os": {"name": driver.get("SCBI_OS_NAME"), "version": driver.get("SCBI_OS_VERSION")},
        "roots": roots,
        "modules": modules,
    }
    return doc, 0


def cyclonedx(driver, doc: dict) -> dict:
    """The CycloneDX 1.5 document of a graph."""
    components = []
    for m in doc["modules"]:
        c: dict = {"type": "application" if m["root"] else "library",
                   "bom-ref": m["id"], "name": m["name"]}
        src = m.get("source") or {}
        version = m.get("version", "")
        if src.get("type") == "archive":
            version = src.get("version", version)
        elif src.get("ref"):
            version = src["ref"]
        if version:
            c["version"] = version.lstrip("#")
        if m.get("license"):
            c["licenses"] = [{"expression": m["license"]}]
        hashes = [{"alg": alg, "content": src[key]} for alg, key in (("SHA-1", "sha1"), ("SHA-256", "sha256"))
                  if src.get(key)]
        if hashes:
            c["hashes"] = hashes
        refs = []
        if src.get("type") == "archive" and src.get("url"):
            refs.append({"type": "distribution", "url": f"{src['url'].rstrip('/')}/{src.get('file', '')}"})
        elif src.get("url"):
            refs.append({"type": "vcs", "url": src["url"]})
        if refs:
            c["externalReferences"] = refs
        props = [{"name": "scbi:type", "value": m["type"]}]
        if m.get("variant") and m["variant"] != "default":
            props.append({"name": "scbi:variant", "value": m["variant"]})
        if src.get("revision"):
            props.append({"name": "scbi:revision", "value": src["revision"]})
        if src.get("type") and src["type"] != "archive":
            props.append({"name": "scbi:vcs", "value": src["type"]})
        c["properties"] = props
        components.append(c)

    dependencies = [{"ref": m["id"], "dependsOn": sorted({d["id"] for d in m["depends"]})}
                    for m in doc["modules"]]
    #  reproducible: SOURCE_DATE_EPOCH, and a serial number derived from
    #  the content
    epoch = driver.get("SOURCE_DATE_EPOCH")
    try:
        now = time.gmtime(int(epoch)) if epoch else time.gmtime()
    except ValueError:
        now = time.gmtime()
    content = json.dumps([components, dependencies], sort_keys=True)
    serial = uuid.uuid5(uuid.NAMESPACE_URL, f"scbi:{content}")
    metadata: dict = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", now),
        "tools": {"components": [{"type": "application", "name": "scbi",
                                  "version": driver.get("SCBI_VERSION") or "unknown"}]},
        "properties": [{"name": "scbi:target", "value": doc["target"]},
                       {"name": "scbi:plan", "value": doc["plan"] or ""}],
    }
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": metadata,
        "components": components,
        "dependencies": dependencies,
    }


def show(driver, builder, what: str) -> int:
    doc, status = graph(driver, builder)
    if status != 0:
        return 1
    if what == "sbom":
        doc = cyclonedx(driver, doc)
    sys.stdout.write(json.dumps(doc, indent=2) + "\n")
    sys.stdout.flush()
    return 0

