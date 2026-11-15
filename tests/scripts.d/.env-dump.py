"""Environment of test173: the env actions of lib1/dv (env and build-env
hooks) replayed through module_final_step, written to env.dump."""

import os


def module_final_step(ctx):
    if ctx.module != "m-lib1":
        return
    mdir = os.path.join(ctx.get("SCBI_BDIR"), "m-lib1")
    with open(os.path.join(mdir, "env.dump"), "w") as f:
        for hook in ("env", "build-env"):
            for action, var, value in ctx.env_actions(hook, "lib1/dv"):
                f.write(f"A:{action} {var} = {value.removeprefix(mdir)}\n")
