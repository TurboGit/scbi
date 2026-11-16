def test(t):
    t.runs('./scbi show --plan=meta-meta-2 --build-plan meta-meta:v1')

    t.clean_output()
    t.trim_output()

    t.diff("""\
There is 4 module(s) in the plan
depA/toto:v9
dmod/x:v9
meta-meta:v1
oot:v9
""")

    t.runs('./scbi show --plan=meta-meta-2 --build-plan dmod/cl:123 meta-meta/variant:v1')

    t.clean_output()
    t.trim_output()

    t.diff("""\
There is 4 module(s) in the plan
depA/toto:123
dmod/cl:123
meta-meta/variant:v1
oot:123
""")

    t.runs('./scbi show --plan=meta-meta-2 --build-plan dmod/variant.cl:123 meta-meta/variant:v1')

    t.clean_output()
    t.trim_output()

    t.diff("""\
There is 4 module(s) in the plan
depA/toto
dmod/variant.cl:123
meta-meta/variant:v1
oot/variant.cl
""")

    t.runs('./scbi show --plan=meta-meta-2 --build-plan dmod/both.cl:123 meta-meta/both:v1')

    t.clean_output()
    t.trim_output()

    t.diff("""\
There is 4 module(s) in the plan
depA/toto:123
dmod/both.cl:123
meta-meta/both:v1
oot/both.cl:123
""")

    t.runs('./scbi show --plan=meta-meta --build-plan meta-meta/both:v2')

    t.clean_output()
    t.trim_output()

    t.diff("""\
There is 4 module(s) in the plan
depA/both:v2
dmod/both:v2
meta-meta/both:v2
oot/both:v2
""")
