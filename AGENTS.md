# AGENTS.md — SCBI

SCBI (Source Code Build Infrastructure) is a Bash tool that builds software
from sources (VCS checkouts or archives), handles dependencies, variants,
versions, build plans and developers' local checkouts. Everything is plain
Bash; there is no compile step.

## Repository layout

| Path | What it is |
|------|------------|
| `scbi` | Main driver: option parsing, ini/env/plan loading, dependency resolution, per-module step orchestration (`handle-module`, `handle-depends`, `handle-sources`, ...). |
| `scbi-lint`, `scbi-format`, `scbi-show`, `scbi-shell`, `scbi-store`, `scbi-source-archive`, `scbi-patch` | Sub-command drivers. They are not run directly: `scbi <subcmd> ...` sources `scbi-<subcmd>` with `subcommand` as first argument after setting up the generic environment (`setup-generic-tool-env`). |
| `scripts.d/[0-9]_*` | **Runtime** (core library), sourced in numeric order by the driver at start-up. |
| `scripts.d/_os_<name>` | OS-specific runtime overrides (e.g. `_os_windows`), sourced after the numbered runtime files. |
| `scripts.d/c-*` (and every other non-dot file) | **Plug-ins**: one Bash file per buildable project/module. |
| `scripts.d/patches/` | Patches referenced by plug-ins' `patches` hooks. |
| `scripts.d/.env`, `.plan-default`, `.pkgs-<distrib>` | Default environment, default build plan, mapping of `os@-<name>` dependencies to distribution packages. |
| `bash_completion.d/scbi` | Bash completion. |
| `doc/scbi.tex` | Reference manual (LaTeX). The authoritative spec for hooks, options, env variables, plans and ini files. |
| `tests/` | Regression testsuite (see below). |

### Runtime files (`scripts.d/[0-9]*`)

- `0_runtime` — core helpers: `fn-exists`, `copy-function`, `get-hook-value`, `is-hook-true`, `get-config-options`, `is-enabled`, ...
- `1_setup` — default values for `SCBI_ROOT`, `SCBI_BDIR`, `SCBI_PREFIX`, `SCBI_*_REPO`, archives/patches/logs dirs (all overridable via env).
- `2_log` — logging (`ilog`, `dlog`, `elog`, `clog`, ...).
- `3_path` — install prefix path fix-ups.
- `4_scm` — Git/SVN/Mercurial checkout, branch and submodule handling.
- `5_tools` — generic tooling: hook lookup (`get-hook`), timers, environment helpers (`define-var`, ...).
- `6_distpkg` — distribution detection, discriminants, OS package handling (`os@-*` dependencies).
- `7_modgen` — default implementation of module steps (`module-setup`, `module-patch`, `module-install`, `module-purge`, ...).
- `8_mail` — e-mail notification.
- `9_versions` — build plans, barriers, discriminants, auto-variants, module plan loading.

Runtime files are sourced in the same shell as the driver; they share global
state (`SCBI_*` variables, associative arrays). Keep functions in the
`lower-case-dash` naming style used throughout and prefix truly internal
helpers with `_internal_`.

## Plug-ins

A plug-in file `scripts.d/<module>` defines Bash functions (hooks) prefixed
with the module name, all optional:

```bash
function c-lcms2-vcs()      { echo default; echo none; echo git; echo http://github.com/mm2/Little-CMS; }
function c-lcms2-config()   { local PREFIX=$1 TARGET=$2 VARIANT=$3; ../src/configure --prefix=$PREFIX; }
function c-lcms2-build()    { local PREFIX=$1 TARGET=$2 VARIANT=$3; make -j$SCBI_JOBS; }
function c-lcms2-install()  { local PREFIX=$1 TARGET=$2 VARIANT=$3; make install; }
```

- Hook name: `<module>[-<variant>|-common]-<hook>`, e.g. `vcs`, `archive`,
  `patches`, `depends`, `build-depends`, `tests-depends`, `env`, `build-env`,
  `external-env`, `setup`, `out-of-tree`, `config`, `config-options`,
  `build`, `install`, `wrapup`, `prefix`, `tests`, `run`, `version`,
  `pre-<step>`/`post-<step>`; meta-modules use `modules`, `aggregate`,
  `propagate-version`, `plan`. See `doc/scbi.tex` section *Creating new
  plug-ins → Hooks* for parameters and return values before adding or
  changing one.
- Hooks receive `PREFIX TARGET VARIANT` (the `archive` hook gets
  `VERSION`). Declare them as `local PREFIX=$1`, `local TARGET=$2`,
  `local VARIANT=$3` in new hooks even if unused: `scbi-lint` warns
  otherwise (many existing plug-ins still trigger these warnings).
- Hooks run already `cd`'d into the right place; the sources are always at
  `../src`. Do not `cd` around in hooks.
- Value hooks return data by `echo`ing one value per line.
- In-repo plug-ins are named `c-<project>`; new ones should follow that.
- Plug-ins may inherit/reuse others' hooks (see *Inheritance* in the doc).

After editing plug-ins, run the linter:

```bash
make lint                       # scbi lint --error scripts.d/c-*
./scbi lint --plugins=$PWD/scripts.d c-foo   # a single plug-in
```

## Building, installing, testing

```bash
make              # install drivers to ~/.local/bin and runtime+plug-ins to ~/.config/scbi
make test         # full regression testsuite (tests/run)
make doc          # build doc/scbi.pdf (latex, bibtex, makeindex, pdflatex)
make sync-os-deps # propagate/sort .pkgs-* files across distributions
```

`make` overwrites files in `~/.config/scbi` (tracked in
`~/.config/scbi/.core.plugins`) and `~/.local/bin`; do not run it unless the
user asks. Note that `scbi-patch` is not installed by `make`.

### Testsuite

- Run all: `cd tests && ./run`. Run some: `cd tests && ./run test001 test092`.
- `tests/run` copies the top-level drivers and the runtime files
  (`0_runtime`, `[2-9]*`, `_os_*`, `.pkgs-*`) into `tests/` and
  `tests/scripts.d/`, patches a few things for determinism, then sources each
  `tests/drivers/testNNN`. Those copies are git-ignored; never edit them —
  edit the originals at the top level.
- Tests use the `osht` TAP framework (`RUNS`, `IS`, `DIFF`, ...). Expected
  output is inline in the driver as a heredoc passed to `CLEAN-DIFF`, which
  masks time-stamps, `$PWD`, and hashes.
- `tests/scripts.d/` holds test-only plug-ins (no `c-` prefix);
  `tests/.root/repos` holds the small Git/SVN repositories and archives they
  build from.
- When adding a test, create `tests/drivers/testNNN` with the next free
  number and bump the `PLAN <n>` count in `tests/run` by the number of new
  assertions.
- A behavior change in the driver/runtime usually changes expected output in
  several drivers; update them and say which in the commit.
- The `PLAN` count is only applied when running the whole suite.

### Python port (in progress)

The driver is being ported to Python in `src/scbi/`, step by step; the
Bash driver remains the reference and must stay green.

```bash
make unit      # pytest unit tests (tests/unit), no Bash involved
make oracle    # differential tests: Python results vs the Bash functions
make test-py   # tests/ratchet: each driver run with SCBI_IMPL=python
SCBI_IMPL=python ./run test001   # in tests/: one driver with the Python driver
```

- `tests/unit/oracle.py` loads the Bash driver functions and runtime so a
  test can call any Bash function on the same inputs as the Python code.
  Accepted divergences are documented in `tests/unit/known_diffs.py`.
- `tests/python-pass.txt` lists the drivers passing with the Python driver;
  `tests/ratchet` fails if one of them regresses and appends new passes.
- `SCBI_PLUGIN_FORMAT=yaml` (Python driver, `make test-py-yaml`, pass
  list `tests/python-yaml-pass.txt`) runs the drivers with YAML versions
  of the test plug-ins generated by `tests/run`. A driver changing a
  plug-in must call `PLG-UPDATE <name>` after the change (or use
  `PLG-TOUCH <name>`).
- Drivers specific to one implementation are listed in
  `tests/python-only.txt` / `tests/bash-only.txt` (skipped with the other
  driver; the `PLAN` count of `tests/run` differs per implementation).
- With the Python driver `scbi lint` and `scbi format` handle YAML
  plug-ins only (`plugin/lint.py`, `plugin/yamlwrite.py`, canonical key
  order `catalog.FORMAT_ORDER`); Bash plug-ins are converted with
  `python3 -m scbi.convert`. Their test fixtures are in `tests/fixtures/`
  (not in `tests/scripts.d`, which only holds valid plug-ins).
- The driver only uses the plug-in model (`plugin/model.py`). YAML is
  confined to its reader/writer (`plugin/yamlfmt.py`, `plugin/yamlwrite.py`)
  and the YAML tools (lint, format, converter). Readers find files through
  `plugin/formats.py` (suffix → reader; add a format there) and build the
  model with `plugin/construct.py` (checks common to all formats).
- Command hooks and functions of YAML plug-ins are in the command
  language (`hooks/cmdlang.py`), run by the interpreter, never by Bash
  (`steps/interp.py`, isolated environment `steps/hookenv.py`, replay
  files `steps/replay.py` / `scbi replay`). The converter
  (`plugin/liftcmd.py`) refuses what has no equivalent; `--closure DIR`
  keeps Bash the plug-ins inherited by Bash plug-ins. Steps are run by
  `steps/wrapper.py` and `steps/generic.py` (ports of module-wrapper and
  7_modgen, Bash fallback when redefined).
- With the Python driver the environment files are Python
  (`.env-<name>.py`, `src/scbi/envpy.py`: settings, `PASSTHROUGH`, hooks
  `define_var`, `rewrite_vcs`, `rewrite_archive`, `proxy`,
  `module_final_step` with `steps/final.py`); Bash ones are converted
  with `python3 -m scbi.envconvert`. Test env files exist in both forms
  in `tests/scripts.d` (`.env-x` and `.env-x.py`).
- The module environment (handle-env, handle-module-env,
  plugin-call-env-hooks) is `steps/modenv.py`, the OS packages and auto
  variants `ospkg.py` (both fall back to
  the Bash functions when a ported one is redefined: hashes in
  `hooks/reference.py`, checked by `tests/unit/test_hooks_policy.py`),
  `--standalone` `standalone.py`.
- Port Bash code literally (word splitting, `read`, associative array order
  ...): helpers for these semantics are in `src/scbi/bashcompat.py`.

## Documentation

`doc/scbi.tex` must be kept in sync with the code: any new or changed
hook, command-line option, environment variable (`SCBI_*`), ini/plan
directive or sub-command needs a matching update there (also check
`bash_completion.d/scbi` and the `usage` function in the driver). The
`README.md` is a short tutorial only.

## Conventions

- Bash only, `#!/bin/bash`, 4-space indentation, `[[ ... ]]` tests, `local`
  for every function variable. In `scbi`, functions are preceded by a
  `############################## <name>` banner; follow it there.
- Inside runtime and build steps, report through the logging helpers of
  `2_log` (`ilog`, `dlog`, `elog`) so messages reach the build logs.
- Commit messages: short imperative subject, prefixed by the component when
  scoped, e.g. `c-polyorb: Disable global install.`, `scbi-lint: Add more
  hook checks.`, `test092: Update expected output (archive hook).`
- The `Makefile` derives the core version from the last commit touching
  `scbi`, `scbi-*`, `scripts.d/[0-9]*`, `scripts.d/_os_*` and the completion
  file, and the plug-in version from `scripts.d/c-*` and
  `scripts.d/patches`. Keep core and plug-in changes in separate commits.

## Repository hygiene

- Untracked artefacts may exist in the tree: never add them to git.
- Do not commit unless asked.
- Never ever push.
