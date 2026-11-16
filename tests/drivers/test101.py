def test(t):
    t.runs('./scbi show --plan=set --build-plan lib1')

    t.trim_output()

    t.diff(t.text("""\
There is 7 module(s) in the plan
@for main use module7:87
module1:12
module2:\\${UNKNOWN}
module3/kl:12
module4:12
module5:12
module6:12
"""))
