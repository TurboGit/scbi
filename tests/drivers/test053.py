def test(t):
    # Note that we transform all 1 to A and 2 to B to have a better check
    # of the final output.

    # ========================= A
    t.runs('./scbi show --plan=group4 --build-plan lib1')

    t.trim_output()

    t.diff("""\
There is 5 module(s) in the plan
modA:master
modB
modC
modG:master
modH:master
""")

    # ========================= B
    t.runs('./scbi show --plan=group4/mpi --build-plan lib1')

    t.trim_output()

    t.diff("""\
There is 5 module(s) in the plan
modA/mpi.fast:master
modB
modC
modG/mpi:master
modH/mpi:master
""")

    # ========================= C
    t.runs('./scbi --plan=group4/mpi.fast show --build-plan lib1')

    t.trim_output()

    t.diff("""\
There is 5 module(s) in the plan
modA/mpi.fast:master
modB
modC
modG/mpi:master
modH/fast:rz
""")
