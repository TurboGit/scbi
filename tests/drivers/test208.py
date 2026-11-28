def test(t):
    # --parallel: the modules handled by several driver processes, the
    # dependencies first, one build step at a time, the output of each
    # module printed as one block

    # a diamond: pa -> pb, pc -> pd
    #  - the config steps of pb and pc wait for each other: they must run
    #    at the same time
    #  - a build step takes a lock directory, failing if it exists: two
    #    build steps never run at the same time
    t.sh('''cat > scripts.d/meet.sh <<'XEOF'
touch "$1/$2.started"
n=0
while [ $n -lt 100 ]; do
  [ -e "$1/$3.started" ] && exit 0
  sleep 0.1
  n=$((n+1))
done
echo "$2: $3 not started"
exit 1
XEOF
cat > scripts.d/excl.sh <<'XEOF'
mkdir "$1/build.lock" || { echo "two build steps at the same time"; exit 1; }
sleep 0.3
rmdir "$1/build.lock"
XEOF
for m in pd pb pc pa; do
  case $m in
    pd) deps=""; config="config: echo config pd" ;;
    pb) deps="depends: [pd]"; config="config: sh \\$SCBI_PLUGINS/meet.sh \\$SCBI_BDIR pb pc" ;;
    pc) deps="depends: [pd]"; config="config: sh \\$SCBI_PLUGINS/meet.sh \\$SCBI_BDIR pc pb" ;;
    pa) deps="depends: [pb, pc]"; config="config: echo config pa" ;;
  esac
  printf "plugin: $m\\n$deps\\n$config\\nbuild: sh \\$SCBI_PLUGINS/excl.sh \\$SCBI_BDIR\\n" > scripts.d/$m.yaml
done''')

    t.runs('./scbi --parallel=3 -d pa')
    t.sh('cp $TEST_OUTPUT build.out')

    # needed by: as in a sequential build (the path of the walk to the
    # module, the closest first); none for the module of the command line
    t.sh('sed -n "/Building pd/,/End Building pd/p" build.out > pd.out')
    t.runs('grep -A2 "needed by:" pd.out | cut -d: -f4-')
    t.clean_diff("""\
 needed by:
   ↳ pb
   ↳ pa
""")
    t.sh('sed -n "/Building pa/,/End Building pa/p" build.out > pa.out')
    t.runs('grep -c "needed by:" pa.out || true')
    t.clean_diff("""\
0
""")

    # pd first, pa last, pb and pc (pX) in any order, each block whole
    t.runs('grep -E "Building|parallel build: " build.out | sed "s/ p[bc] / pX /"')
    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : parallel build: 4 module(s), 3 at a time, 1 build slot(s)
xxxx/xx/xx xx:xx:xx : Building pd [default] (n/a)
xxxx/xx/xx xx:xx:xx : End Building pd [default] (n/a)
xxxx/xx/xx xx:xx:xx : Building pX [default] (n/a)
xxxx/xx/xx xx:xx:xx : End Building pX [default] (n/a)
xxxx/xx/xx xx:xx:xx : Building pX [default] (n/a)
xxxx/xx/xx xx:xx:xx : End Building pX [default] (n/a)
xxxx/xx/xx xx:xx:xx : Building pa [default] (n/a)
xxxx/xx/xx xx:xx:xx : End Building pa [default] (n/a)
""")

    # the same build ids as a sequential build: nothing to rebuild
    t.runs('./scbi -d pa')
    t.sh('grep -c "no build needed" $TEST_OUTPUT > x; mv x $TEST_OUTPUT')

    t.clean_diff("""\
4
""")

    # nothing to rebuild in parallel either
    t.runs('./scbi --parallel -d pa')
    t.sh('grep -c "no build needed" $TEST_OUTPUT > x; mv x $TEST_OUTPUT')

    t.clean_diff("""\
4
""")

    # a failure: pa is not built, pc is, the build fails
    t.sh('printf "post-build: exit 2\\n" >> scripts.d/pb.yaml')
    t.nruns('./scbi --parallel --force -d pa')
    t.grep('End Building pc')
    t.ngrep('Building pa')

    # without --deps: sequential
    t.runs('./scbi --parallel pd')
    t.grep('parallel build: needs --deps, building sequentially')

    # a meta-module: its modules first, then its wrapup; then nothing to
    # rebuild sequentially
    t.sh('printf "plugin: pall\\nmodules: [pa, pd]\\n" > scripts.d/pall.yaml')
    t.sh('sed -i "/post-build/d" scripts.d/pb.yaml')
    t.runs('./scbi --parallel -d pall')
    t.grep('Metamodule pall \\[default\\] wrapup')
    t.runs('./scbi -d pall')
    t.ngrep('trigger:')

    # a meta-module with an aggregate hook: sequential
    t.runs('./scbi --parallel --dry-run -d metaagg')
    t.grep('parallel build: not with --dry-run')
    t.runs('./scbi --parallel -d metaagg')
    t.grep('parallel build: meta-module metaagg (aggregate hook), building sequentially')

    # what the parallel build did: a summary, a timeline
    t.runs('./scbi --parallel=3 --force -d pa')
    t.sh('cp $TEST_OUTPUT summary.out')
    t.runs('grep -A4 "parallel build finished" summary.out | cut -d: -f4- | sed -E "s/[0-9]+:[0-9]+:[0-9]+/H:MM:SS/g; s/[0-9]+%/N%/g"')
    t.clean_diff("""\
 parallel build finished in H:MM:SS, 4 module(s)
   running: 1 module N%, 2 modules N% of the time
   a free place, the modules waiting for their dependencies: H:MM:SS (N%)
   build and tests steps waiting for a build slot (SCBI_BUILD_SLOTS=1): H:MM:SS
   timeline: <pwd>/.root/builds/.logs/x86_64-linux-gnu-parallel.log
""")
    t.runs('grep -c "build slot taken" .root/builds/.logs/x86_64-linux-gnu-parallel.log')
    t.clean_diff("""\
4
""")
