def test(t):
    # Note that we transform all 1 to A and 2 to B to have a better check
    # of the final output.

    t.set('SCBI_OS_NAME', 'deb')
    t.set('SCBI_OS_VERSION', '9')
    t.set('SCBI_OS_MAJOR_VERSION', '9.3')

    # ========================= A
    t.runs('./scbi show --plan=group5 --build-plan lib1')

    t.trim_output()

    t.diff("""\
There is 5 module(s) in the plan
modA/mpi.fast:master
modB
modC
modG/mpi:master
modH/mpi:master
""")

    # ========================= B
    t.runs('./scbi show --plan=group5/mpi --build-plan lib1')

    t.trim_output()

    t.diff("""\
There is 5 module(s) in the plan
modA/mpi.fast:master
modB
modC
modG/mpi:master
modH/fast:rz
""")

    t.set('SCBI_OS_NAME', 'deb')
    t.set('SCBI_OS_VERSION', '11')
    t.set('SCBI_OS_MAJOR_VERSION', '11.1')

    # ========================= C
    t.runs('./scbi show --plan=group5/fast --build-plan lib1')

    t.trim_output()

    t.diff("""\
There is 5 module(s) in the plan
modA:master
modB
modC
modG:master
modH:master
""")

    t.unset('SCBI_OS_NAME')
    t.unset('SCBI_OS_VERSION')
    t.unset('SCBI_OS_MAJOR_VERSION')
