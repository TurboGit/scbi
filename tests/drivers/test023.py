def test(t):
    # check for recursive dependencies

    t.sh("""\
mkdir -p .root/builds/reca
mkdir -p .root/builds/recb
mkdir -p .root/builds/recc
""")

    # ========== deps A
    t.nruns('./scbi --deps reca')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building recc [default] (n/a)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ recb
xxxx/xx/xx xx:xx:xx :   ↳ reca
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : recc (FAILED) recursive dependencies detected
xxxx/xx/xx xx:xx:xx : recc (FAILED)  ⦁ recc → reca
xxxx/xx/xx xx:xx:xx : recc (FAILED)  ⦁ reca → recb
xxxx/xx/xx xx:xx:xx : recc (FAILED)  ⦁ recb → recc
""")

    # ========== list-depends A
    t.nruns('./scbi show --depends reca')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : reca (FAILED) recursive dependencies detected
xxxx/xx/xx xx:xx:xx : reca (FAILED)  ⦁ reca → recb
xxxx/xx/xx xx:xx:xx : reca (FAILED)  ⦁ recb → recc
xxxx/xx/xx xx:xx:xx : reca (FAILED)  ⦁ recc → reca
""")

    # ========== list-depends B
    t.nruns('./scbi show --depends recb')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : recb (FAILED) recursive dependencies detected
xxxx/xx/xx xx:xx:xx : recb (FAILED)  ⦁ recb → recc
xxxx/xx/xx xx:xx:xx : recb (FAILED)  ⦁ recc → reca
xxxx/xx/xx xx:xx:xx : recb (FAILED)  ⦁ reca → recb
""")
