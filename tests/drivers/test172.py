def test(t):
    t.runs('./scbi --plan=pattern show --build-plan')

    t.clean_diff("""\
There is 7 module(s) in the plan
m1:1.3.6
m2/variant1:v2.0|v1.4|9.2
m3:v1.2
mp1:v1.3
mp2/variant1:1.4-2
mp3:1.2
mp4:1.6
""")
