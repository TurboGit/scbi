def test(t):
    #  Check config-options with cross support

    t.runs('./scbi crossmod')

    t.runs("grep -h '^@@@' .root/builds/.logs/*linux**crossmod*build*")

    t.diff("""\
@@@ make prefix=/toto BUILD=native
""")

    t.runs('./scbi --target=x86_64-mingw32 crossmod')

    t.runs("grep -h '^@@@' .root/builds/.logs/*mingw*crossmod*build*")

    t.diff("""\
@@@ make prefix=/toto BUILD=cross
""")
