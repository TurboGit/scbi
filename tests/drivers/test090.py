def test(t):
    t.sh("GVER=$(gcc --version | grep gcc | awk '{print $4}')")

    t.runs('./scbi show --plan=autov --build-plan mautov')

    t.clean_output()
    t.sort_output()
    t.trim_output()

    t.diff(t.text("""\
@for mainav use mautov/mainav:99.99
@for mainav2 use mautov/for2:99.99
There is 3 module(s) in the plan
mautov/native:$GVER
"""))

    t.runs('./scbi show --plan=autov --build-plan mainav=mautov/new mautov')

    t.clean_output()
    t.sort_output()
    t.trim_output()

    t.diff(t.text("""\
@for mainav use mautov/new
@for mainav2 use mautov/for2:99.99
There is 3 module(s) in the plan
mautov/native:$GVER
"""))

    t.runs('./scbi show --plan=autov --build-plan mautov/new mautov')

    t.clean_output()
    t.sort_output()
    t.trim_output()

    t.diff("""\
@for mainav use mautov/mainav:99.99
@for mainav2 use mautov/for2:99.99
There is 3 module(s) in the plan
mautov/new
""")
