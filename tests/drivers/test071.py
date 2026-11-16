def test(t):
    # Check for [ = barrier ] matching the discriminants

    # ========================= A

    t.set('SCBI_OS_NAME', 'deb')
    t.set('SCBI_OS_VERSION', '9')
    t.set('SCBI_OS_MAJOR_VERSION', '9.3')

    t.runs('./scbi show --plan=autobar --build-plan lib1')

    t.trim_output()

    t.diff("""\
There is 7 module(s) in the plan
modA/deb
modB/deb9
modC/deb9.3
modD
modE/just9
modF
modG
""")

    # ========================= B

    t.set('SCBI_OS_MAJOR_VERSION', '9.1')

    t.runs('./scbi show --plan=autobar --build-plan lib1')

    t.trim_output()

    t.diff("""\
There is 7 module(s) in the plan
modA/deb
modB/deb9
modC
modD
modE/just9
modF
modG
""")

    # ========================= C

    t.set('SCBI_OS_NAME', 'deb')
    t.set('SCBI_OS_VERSION', '10')
    t.set('SCBI_OS_MAJOR_VERSION', '10.4')

    t.runs('./scbi show --plan=autobar --build-plan lib1')

    t.trim_output()

    t.diff("""\
There is 7 module(s) in the plan
modA/deb
modB/deb10
modC
modD
modE
modF
modG/notdeb9
""")

    # ========================= D

    t.set('SCBI_OS_NAME', 'win')
    t.set('SCBI_OS_VERSION', '3')
    t.set('SCBI_OS_MAJOR_VERSION', '3.1')

    t.runs('./scbi show --plan=autobar --build-plan lib1')

    t.trim_output()

    t.diff("""\
There is 7 module(s) in the plan
modA
modB
modC
modD/win
modE
modF/notdeb
modG/notdeb9
""")

    t.unset('SCBI_OS_NAME')
    t.unset('SCBI_OS_VERSION')
    t.unset('SCBI_OS_MAJOR_VERSION')
