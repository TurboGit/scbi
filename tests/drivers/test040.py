def test(t):
    # Note that we transform all 1 to A and 2 to B to have a better check
    # of the final output.

    # echo ========================= A
    t.runs('./scbi show --plan=group --build-plan lib1')

    t.trim_output()

    t.diff("""\
There is 10 module(s) in the plan
modA
modB
modC
modD:vA
modE/new:vB
modF/grp:vZ
modG/grp:vZ
modH/grp:vZ
modI/hybrid
modJ/speed
""")

    # echo ========================= B
    t.nruns('./scbi show --plan=group2 --build-plan lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : build (FAILED) build plan unexpected modB on group start
""")

    # echo ========================= C
    t.runs('./scbi show --plan=group3 --build-plan lib1')

    t.trim_output()

    t.diff("""\
There is 6 module(s) in the plan
modA
modB/new:vZ
modC/fast:vc
modD/fast:vA
modE/one:vV
modH/fast:vB
""")
