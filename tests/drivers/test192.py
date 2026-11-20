def test(t):
    # scbi schema: the JSON Schema of the plug-ins, alone on the output

    t.runs("./scbi --color:no schema > schema.json")
    t.runs("""python3 -c '
import json
d = json.load(open("schema.json"))
print(d["title"])
print(d["properties"]["config"]["description"])
print(sorted(d["properties"]["build-env"]["anyOf"][1]["properties"]))
'""")

    t.diff("""\
SCBI plug-in
Configures the sources (configure, cmake...); the sources are in ../src.
(commands; parameters: $PREFIX $TARGET $VARIANT)
['_', 'common', 'cross', 'default']
""")
