def test(t):
    # ====== list all deps listDA
    t.runs('./scbi show --depends listDA')

    t.clean_diff("""\
buildA
listDA
listDB
listDC
listDD
""")

    # ====== list all deps (explicit) listDA
    t.runs('./scbi show --depends --filter:all listDA')

    t.clean_diff("""\
buildA
listDA
listDB
listDC
listDD
""")

    # ====== list dev deps listDA
    t.runs('./scbi show --depends --filter:dev listDA')

    t.clean_diff("""\
buildA
""")

    # ====== list run deps listDA
    t.runs('./scbi show --depends --filter:run listDA')

    t.clean_diff("""\
listDA
listDB
listDC
listDD
""")

    # ====== list run direct deps listDA
    t.runs('./scbi show --depends:direct --filter:run listDA')

    t.clean_diff("""\
listDB
""")

    # ====== list dev direct deps listDA
    t.runs('./scbi show --depends:direct --filter:dev listDA')

    t.clean_diff("""\
buildA
""")

    # ====== list all direct deps listDA
    t.runs('./scbi show --depends:direct --filter:all listDA')

    t.clean_diff("""\
buildA
listDB
""")
