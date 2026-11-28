def test(t):
    # scbi show --freeze: a build plan pinned to the sources last built,
    # --json: the graph of the build, --sbom: CycloneDX SBOM

    t.set('TODAY', '2026-01-01')
    t.sh('printf "license: MIT\\n" >> scripts.d/lib1.yaml')

    t.runs('./scbi -d mainlib')

    t.runs('./scbi show --freeze mainlib')

    t.clean_diff("""\
# Build plan frozen by scbi show --freeze
# date: 2026-01-01
# plan: none
# target: x86_64-linux-gnu
# os: deb
# modules: mainlib

# lib1: git master
lib1:eb90bc4f3553280d80aef0250dc37ad2fd174636
# mainlib: git master
mainlib:b5113b39430774d426842b291555994da9aaa4b8
""")

    # the frozen plan builds the commits recorded
    t.sh('./scbi show --freeze mainlib > .scbi-plan-frozen')
    t.runs('./scbi show --plan=frozen --module-ref:version lib1')
    t.clean_diff("""\
eb90bc4f3553280d80aef0250dc37ad2fd174636""")
    t.runs('./scbi --plan=frozen -d mainlib')
    t.grep(*t.words('"lib1 git eb90bc4f3553280d80aef0250dc37ad2fd174636 sha-1 '
                    'eb90bc4f3553280d80aef0250dc37ad2fd174636" .root/builds/lib1/source-ref'))

    # a module last built from another reference (lib1 from an archive,
    # mainlib from a commit) is not pinned, an archive
    # is pinned to its version; skipped modules are kept
    t.runs('./scbi --no-patch --archive lib1:#v1.2')
    t.sh('printf "lib2:skip\\n" > .scbi-plan-sk')
    t.runs('./scbi show --plan=sk --freeze mainlib')
    t.clean_diff("""\
# Build plan frozen by scbi show --freeze
# date: 2026-01-01
# plan: sk
# target: x86_64-linux-gnu
# os: deb
# modules: mainlib

# lib1: last built from archive v1.2: not pinned
lib1
# mainlib: last built from git b5113b39430774d426842b291555994da9aaa4b8: not pinned
mainlib

lib2:skip
scbi show --freeze: 2 module(s) not pinned, see the comments
""")
    t.runs('./scbi show --freeze lib1:#v1.2')
    t.clean_diff("""\
# Build plan frozen by scbi show --freeze
# date: 2026-01-01
# plan: none
# target: x86_64-linux-gnu
# os: deb
# modules: lib1:#v1.2

# lib1: archive v1.2 sha-1 631429bf5f27d5aec4d7e41394e0d2eaa3a8da2d
lib1:#v1.2
""")

    t.runs('./scbi -d mainlib')
    t.runs('./scbi show --json mainlib')

    t.clean_diff("""\
{
  "format": 1,
  "plan": null,
  "target": "x86_64-linux-gnu",
  "os": {
    "name": "deb",
    "version": ""
  },
  "roots": [
    "mainlib"
  ],
  "modules": [
    {
      "id": "lib1",
      "name": "lib1",
      "type": "module",
      "variant": "default",
      "version": "",
      "license": "MIT",
      "source": {
        "type": "git",
        "url": "<pwd>/.root/repos/lib1.bundle",
        "ref": "master",
        "revision": "eb90bc4f3553280d80aef0250dc37ad2fd174636"
      },
      "built": true,
      "root": false,
      "depends": []
    },
    {
      "id": "mainlib",
      "name": "mainlib",
      "type": "module",
      "variant": "default",
      "version": "",
      "license": null,
      "source": {
        "type": "git",
        "url": "<pwd>/.root/repos/mainlib.bundle",
        "ref": "master",
        "revision": "b5113b39430774d426842b291555994da9aaa4b8"
      },
      "built": true,
      "root": true,
      "depends": [
        {
          "id": "lib1",
          "kind": "default"
        }
      ]
    }
  ]
}
""")

    t.sh('export SOURCE_DATE_EPOCH=0')
    t.runs('./scbi show --sbom mainlib')
    t.sh('sed -i "s/urn:uuid:[0-9a-f-]*/urn:uuid:UUID/" $TEST_OUTPUT')

    t.clean_diff("""\
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "serialNumber": "urn:uuid:UUID",
  "version": 1,
  "metadata": {
    "timestamp": "1970-01-01T00:00:00Z",
    "tools": {
      "components": [
        {
          "type": "application",
          "name": "scbi",
          "version": "@VERSION@"
        }
      ]
    },
    "properties": [
      {
        "name": "scbi:target",
        "value": "x86_64-linux-gnu"
      },
      {
        "name": "scbi:plan",
        "value": ""
      }
    ]
  },
  "components": [
    {
      "type": "library",
      "bom-ref": "lib1",
      "name": "lib1",
      "version": "master",
      "licenses": [
        {
          "expression": "MIT"
        }
      ],
      "externalReferences": [
        {
          "type": "vcs",
          "url": "<pwd>/.root/repos/lib1.bundle"
        }
      ],
      "properties": [
        {
          "name": "scbi:type",
          "value": "module"
        },
        {
          "name": "scbi:revision",
          "value": "eb90bc4f3553280d80aef0250dc37ad2fd174636"
        },
        {
          "name": "scbi:vcs",
          "value": "git"
        }
      ]
    },
    {
      "type": "application",
      "bom-ref": "mainlib",
      "name": "mainlib",
      "version": "master",
      "externalReferences": [
        {
          "type": "vcs",
          "url": "<pwd>/.root/repos/mainlib.bundle"
        }
      ],
      "properties": [
        {
          "name": "scbi:type",
          "value": "module"
        },
        {
          "name": "scbi:revision",
          "value": "b5113b39430774d426842b291555994da9aaa4b8"
        },
        {
          "name": "scbi:vcs",
          "value": "git"
        }
      ]
    }
  ],
  "dependencies": [
    {
      "ref": "lib1",
      "dependsOn": []
    },
    {
      "ref": "mainlib",
      "dependsOn": [
        "lib1"
      ]
    }
  ]
}
""")

    # the license is not part of the build id
    t.sh('sed -i "s/license: MIT/license: GPL-2.0-only/" scripts.d/lib1.yaml')
    t.runs('./scbi lib1')
    t.grep('no build needed')
