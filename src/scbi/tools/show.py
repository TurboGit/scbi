"""scbi show: information about modules and the build plan (port of
scbi-show).

Ported: --build-plan[:history][=regex], --module-ref[:version|:variant|
:full], usage. The options based on the dependency walker (--depends,
--externals, --rdepends) still run the reference Bash script (the walker
is not ported yet): main() returns None for them.
"""

from __future__ import annotations

import subprocess
import sys

from scbi.bashcompat import words
from scbi.planview import display_build_plan

USAGE = """
SCBI-SHOW {version}

{argv0} show [options] plug-in1 [plug-in2...]

   -h | --help             this help message
   -v | --version          display driver & plug-ins versions
      | --plugins=<dir>    specify the plugins' directory
   -e | --env=<name>       environment file ~/.scbi-<name>
      | --depends:n        list module's dependencies (direct, full)
   -r | --rdepends         list module's reverse dependencies
      | --externals:n      list module's external dependencies
      | --no-version       do not display modules/externals version
      | --filter:n         filter depends/external for dev or runtime
      | --build-plan:n     list current plan
      | --module-ref:n     display variant/version of specific module
      | --stat             display some status of current setup"""


def main(driver, args: list[str]) -> int | None:
    #  getopt -u ... -- $* (unquoted) then set -- $ALLOPTS
    proc = subprocess.run(
        ["getopt", "-u", "-o", "kld",
         "-l", "depends:direct,depends:full,depends,rdepends,build-plan::",
         "-l", "build-plan:history::,externals,externals:only,no-version",
         "-l", "filter:all,filter:dev,filter:runtime,module-ref",
         "-l", "module-ref:version,module-ref:variant,module-ref:full",
         "--", *words(" ".join(args))],
        capture_output=True, text=True, env=driver.base_env())
    if proc.returncode != 0:
        sys.stdout.write(proc.stderr)
        print('try "scbi show --help" for more information.')
        return 1
    opts = words(proc.stdout)

    walker = False
    do_plan, plan_filter, do_mod_ver = "no", "", "no"
    i = 0
    while i < len(opts):
        a = opts[i]
        nxt = opts[i + 1] if i + 1 < len(opts) else ""
        if a in ("--depends:direct", "--depends:full", "--depends", "--rdepends",
                 "--externals:only", "--externals"):
            walker = True
        elif a in ("--build-plan:history", "--build-plan"):
            do_plan = "history" if a.endswith("history") else "yes"
            if nxt != "--":
                plan_filter = nxt
        elif a in ("--module-ref", "--module-ref:version", "--module-ref:variant", "--module-ref:full"):
            do_mod_ver = {"--module-ref": "full", "--module-ref:version": "ver",
                          "--module-ref:variant": "var", "--module-ref:full": "full"}[a]
            i += 1
        i += 1

    if driver.get("DO_HELP") == "yes":
        print(USAGE.format(version=driver.get("SCBI_VERSION"), argv0=driver.argv0))
        return 0

    if walker:
        return None

    plan = driver.plan
    if do_mod_ver != "no":
        modules = words(" ".join(driver.modules))
        out = []
        for n, module in enumerate(modules):
            info = (plan.module_ref(module) + [""] * 4)[:4]
            _, variant, kind, ref = info
            if kind == "VERSION":
                ref = f"#{ref}"
            if do_mod_ver == "ver":
                text = ref
            elif do_mod_ver == "var":
                text = variant
            else:
                if ref == "NONE":
                    ref = ""
                text = (f"/{variant}" if variant else "") + (f":{ref}" if ref else "")
            #  echo -n $x (unquoted)
            out.append(" ".join(words(text)))
            if len(modules) > 1 and module != modules[-1]:
                out.append("\n")
        sys.stdout.write("".join(out))
        sys.stdout.flush()
        return 0

    if do_plan != "no":
        regex = f"({plan_filter.replace(',', '|')})" if plan_filter else ""
        for line in display_build_plan(plan, do_plan if do_plan == "history" else "yes", regex):
            print(line)
        return 0

    print(USAGE.format(version=driver.get("SCBI_VERSION"), argv0=driver.argv0))
    return 0
