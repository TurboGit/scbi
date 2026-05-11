# AGENTS.md — SCBI (Setup Configure Build Install)

## What this is

SCBI is a Bash-based build orchestrator for building large projects with complex dependency chains. The driver (`scbi`) loads **plugin scripts** (`scripts.d/c-*`) that define hook functions for each module (vcs, config, build, install, etc.).

**Version**: v12.1 — [Copyright Pascal Obry 2007-2025](scbi:3)

## Build, test, lint

```
make            # installs to ~/.local/bin, scripts to ~/.config/scbi/
make test       # runs ~1320 osht tests (tests/run)
make lint       # scbi lint --error scripts.d/c-*
make doc        # LaTeX PDF in doc/
```

- **Run a single test**: `make -C tests test && ./tests/run test042` (accepts globs like `test0??`)
- **Test framework**: [osht](tests/osht) (Cory Bennett, Apache 2.0). Each driver at `tests/drivers/testNNN` is sourced, its stdout compared against `tests/drivers/expected/testNNN.exp`.
- **Test cleanup**: builds wiped between each run. Patches reset from `.root/repos/*.patch`.
- **Prerequisites**: `rsync`, `sed`, `diff`, `gcc`, `patch`, `git`, `make`.
- **Install (no root)**: `make` copies to `~/.local/bin/`.

## Key architecture

- `scbi` — the driver, a single Bash script. Entrypoint for all subcommands.
- `scbi-lint`, `scbi-format`, `scbi-show`, `scbi-shell`, `scbi-store`, `scbi-source-archive` — subcommands invoked as `scbi <subcommand>`. Each checks `$1 == "subcommand"` at the top.
- `scbi-patch` — standalone helper to create patches against git branches.
- `scripts.d/0_runtime` — core runtime (hook dispatch, `$SCBI_ALL_HOOKS`).
- `scripts.d/5_tools` — dependency resolution, module loading utilities.
- `scripts.d/7_modgen` — patch application, source management.
- `scripts.d/c-*` — **module definitions** (one file per project). Bash scripts exporting hook functions named `<module>-<hook>`.
- `scripts.d/.plan-*` — **build plans** listing modules with variant:version (`c-gmp:#6.2.1`).
- `scripts.d/.pkgs-*` — OS package lists per distro (`.pkgs-deb`, `.pkgs-ubt`, etc.).
- `scripts.d/patches/` — patch files applied by modules.

## Module (plugin) conventions

Each file in `scripts.d/c-*` defines Bash functions. Hooks are called in this canonical order (`$SCBI_ALL_HOOKS` from `0_runtime:13`):

```
plan|vcs|archive|patches|version|only-explicit-build|out-of-tree|modules|aggregate|propagate-version|build-depends|tests-depends|depends|external-env|build-env|tests-env|env|setup|config-options|config|build|install|wrapup|prefix|tests|run
```

- `-<variant>` suffix selects variant hook (e.g., `lcms-release-config`).
- `cross-` prefix for cross-compilation hooks.
- `pre-`/`post-` prefixes for pre/post hooks around any step.
- Modules declare VCS via `<module>-vcs` hook: `echo default; echo none; echo git; echo <url>`.
- Define `out-of-tree` returning `true`/`false` (default: out-of-tree).
- Hooks receive `($PREFIX, $TARGET, $VARIANT)`.
- Build directory is `$TVDIR/build` (or `$TVDIR/src` for in-tree builds).

## Essential commands

```bash
scbi <module>                     # build default variant from repo main
scbi <module>/<variant>           # build variant
scbi <module>:<branch>            # build from branch/tag
scbi <module>:dev                  # build from local checkout ($GIT_REPO)
scbi <module>:#<version>          # build from tarball version
scbi --update <module>            # fetch latest sources and rebuild
scbi --tests <module>             # run module tests (build first if needed)
scbi --tests:only <module>        # run tests without rebuilding
scbi --deps <module>              # check/build dependencies
scbi --purge <module>             # remove build dir (--purge:only to skip rebuild)
scbi --force <module>             # force rebuild ignoring build-id
scbi --plan=<name> <module>       # use a specific plan file
scbi --env=<name> <module>        # load ~/.scbi-<name> environment
scbi --stat <module>              # show stats/build dirs
scbi --dry-run <module>           # list what would be built
scbi --ini=<section> <module>     # load ini file with given section
scbi --prefix=<dir> <module>      # override global install prefix
scbi --jobs=<N> <module>          # parallel jobs
scbi --flat <module>              # flatter directory structure
```

**Step control**: `-s` (setup), `-c` (config), `-b` (build), `-i` (install), `-w` (wrapup), `-S` (no-setup), `-I` (no-install).

## Configuration

- **INI files** loaded in order: `$HOME/.scbi` → `.scbi` (cwd) → `--ini=<file>`. Section-based (`[section]`).
- **User module dir**: `$HOME/.config/scbi/` (plugin scripts live here after `make install`).
- **Plans**: `scripts.d/.plan-*` with `@alias`, `@for` directives. Loaded via `--plan=<name>` or `$SCBI_PLAN`.
- **Env files**: `~/.scbi-<name>`, `.scbi-<name>`, `scripts.d/.<name>` searched in order.
- **Defaults** set in `scripts.d/.env`: plan=default, clang-version=16, gtk-version=3.0.

## Build layout

```
$SCBI_BDIR/<module>/                 # build root per module
  source-id, build-id, source-ref    # build cache keys
  x86_64-linux-gnu-default/          # <target>-<variant> dir
    src/                             # source tree
    build/                           # out-of-tree build dir
    install/                         # module-local install
    logs/                            # step logs + cmd files
```

Global install copied from module install to `$SCBI_PREFIX` via rsync (uses `sudo` if needed).

## Tests quirks

- Test runner patches `scripts.d/7_modgen` to use `rsync -c` (checksum) and `ilog` for logging.
- `$HOME/.scbi` ini loading is **disabled** in tests via sed.
- `$SCBI_CACHE_DIR=no` for most tests (cache tests set it to `.root/.cache`).
- Tests require `TESTREPOS` pointing to `.root/repos/`.
- Test templates use `CLEAN-DIFF` which normalizes timestamps, paths, and versions.

## Gotchas

- `scbi` has `@VERSION@` placeholder — resolved by `make` via `sed "s/@VERSION@/$(CORE_VER)/"`.
- Async builds NOT supported (`sync-os-deps` has `.NOTPARALLEL`).
- Using `:dev` requires `GIT_REPO` env or ini setting pointing to local checkouts.
- `--enable-<name>` enables features, checked as `$SCBI_<NAME>_SET=true`.
- Circular dependencies resolved by `c-sandbox` virtual plugin that provides env hooks from global sandbox.
