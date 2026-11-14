# AGENTS.md — SCBI

SCBI (Source Code Build Infrastructure) builds software from sources (VCS
checkouts or archives), handles dependencies, variants, versions, build
plans and developers' local checkouts. The driver is Python (`src/scbi`,
python3 + PyYAML, no compile step); the plug-ins are YAML files. The
former Bash driver (`scbi`, `scbi-*`, runtime `scripts.d/[0-9]*`) is kept
for its testsuite, which is also the reference of the Python driver.

## Repository layout

| Path | What it is |
|------|------------|
| `src/scbi/` | **The driver** (Python package, `python3 -m scbi`), installed by `make` as `~/.local/bin/scbi`. See *Python driver* below. |
| `scbi` | Former Bash driver: kept for the Bash testsuite (reference); not installed. |
| `scbi-lint`, `scbi-format`, `scbi-show`, `scbi-shell`, `scbi-store`, `scbi-source-archive`, `scbi-patch` | Sub-commands of the Bash driver (sourced by `scbi <subcmd>`); the Python driver has its own (`src/scbi/tools/`). |
| `scripts.d/[0-9]_*` | **Runtime** of the Bash driver (copied by `tests/run`); the Python driver does not read them (`src/scbi/setup.py` computes their settings). |
| `scripts.d/_os_<name>` | OS-specific runtime overrides of the Bash driver (e.g. `_os_windows`). |
| `scripts.d/c-*.yaml` | **Plug-ins**: one YAML file per buildable project/module. |
| `scripts.d/patches/` | Patches referenced by plug-ins' `patches` hooks. |
| `scripts.d/.env.py`, `.plan-default`, `.pkgs-<distrib>` | Default environment (Python), default build plan, mapping of `os@-<name>` dependencies to distribution packages. |
| `bash_completion.d/scbi` | Bash completion. |
| `doc/scbi.tex` | Reference manual (LaTeX). The authoritative spec for hooks, options, env variables, plans and ini files. |
| `tests/` | Regression testsuite (see below). |

### Runtime files of the Bash driver (`scripts.d/[0-9]*`)

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

A plug-in file `scripts.d/<module>.yaml` maps hook names to their
definition, all optional (format: `doc/scbi.tex`, *Creating new
plug-ins → Plug-in format*):

```yaml
plugin: c-lcms2
vcs:
  proxy: default
  options: none
  protocol: git
  url: http://github.com/mm2/Little-CMS
config: ../src/configure --prefix=$PREFIX
build: make -j$SCBI_JOBS
install: make install
```

- Hooks: `vcs`, `archive`, `patches`, `depends`, `build-depends`,
  `tests-depends`, `env`, `build-env`, `tests-env`, `external-env`,
  `setup`, `out-of-tree`, `config`, `config-options`, `build`, `install`,
  `wrapup`, `prefix`, `tests`, `run`, `version`, `pre-<step>`/`post-<step>`;
  meta-modules use `modules`, `aggregate`, `propagate-version`, `plan`.
  A hook value is its body or a mapping of qualifiers (`_`, `common`,
  `default`, a variant, `cross:`). See *Hooks* in the doc for parameters
  and values before adding or changing one.
- Command hooks are in the command language (one command per line, run by
  the driver, no shell); value hooks are lists; env hooks are lists of
  actions (`add-to-var`, `set-var`...). Items can be guarded with
  `if <condition>:`.
- Hooks run already `cd`'d into the right place; the sources are always at
  `../src`. Do not `cd` around in hooks.
- In-repo plug-ins are named `c-<project>`; new ones should follow that.
- Plug-ins may inherit others' hooks (`inherit:`, see *Inheritance*).

After editing plug-ins, run the linter (and the formatter for the
canonical form):

```bash
make lint                                        # scbi lint --error scripts.d/c-*.yaml
PYTHONPATH=src python3 -m scbi format --replace scripts.d/c-foo.yaml
```

## Building, installing, testing

```bash
make              # install the driver (~/.local/lib/scbi + ~/.local/bin/scbi), plug-ins to ~/.config/scbi
make test         # full regression testsuite (tests/run)
make doc          # build doc/scbi.pdf (latex, bibtex, makeindex, pdflatex)
make sync-os-deps # propagate/sort .pkgs-* files across distributions
```

`make` overwrites files in `~/.config/scbi` (tracked in
`~/.config/scbi/.core.plugins`), `~/.local/lib/scbi` and `~/.local/bin`
(it removes the old Bash `scbi-*` tools there); do not run it unless the
user asks (`make HOME=<tmp>` installs into a temporary directory).

### Testsuite

- Run all with the Bash driver: `cd tests && ./run`. Run some: `cd tests &&
  ./run test001 test092`. The test plug-ins (`tests/scripts.d`) are Bash
  ones, converted to YAML at test time for the Python driver.
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

### Python driver

The driver (`src/scbi/`) is the port of the Bash driver, which remains the
reference of the testsuite and must stay green. It runs no Bash at all: it
reads YAML plug-ins and Python environment files only, not the runtime
files (their settings are computed by `src/scbi/setup.py`), and nothing
can be redefined in Bash.

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
- With `SCBI_IMPL=python`, `tests/run` converts the test plug-ins to YAML
  (`scripts.d/<name>.yaml`, removed at the end). A driver changing a
  plug-in must call `PLG-UPDATE <name>` after the change (or use
  `PLG-TOUCH <name>`). The settings of `tests/scripts.d/1_setup` are
  exported by `tests/run`; test knobs of the Python driver are under
  `SCBI_TESTSUITE=yes` (`SCBI_OS_MODULE`, fake OS `SCBI_OS_NAME=test`
  with `SCBI_TEST_PKGS`).
- Drivers specific to one implementation are listed in
  `tests/python-only.txt` / `tests/bash-only.txt` (skipped with the other
  driver; the `PLAN` count of `tests/run` differs per implementation);
  `tests/python-deferred.txt` lists the drivers using a test plug-in that
  does not convert to YAML (skipped with Python, to be reviewed).
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
  7_modgen).
- With the Python driver the environment files are Python
  (`.env-<name>.py`, `src/scbi/envpy.py`: settings, `PASSTHROUGH`, hooks
  `define_var`, `rewrite_vcs`, `rewrite_archive`, `proxy`,
  `module_final_step` with `steps/final.py`); Bash ones are converted
  with `python3 -m scbi.envconvert`. Test env files exist in both forms
  in `tests/scripts.d` (`.env-x` and `.env-x.py`).
- The module environment (handle-env, handle-module-env,
  plugin-call-env-hooks) is `steps/modenv.py`, the OS packages and auto
  variants `ospkg.py`, `--standalone` `standalone.py`, `scbi shell`
  `tools/shell.py` (spawns the user's `$SHELL`). Bash runs only in the
  migration tools (`scbi.convert`, `scbi.envconvert`, `plugin/legacy.py`)
  and in the tests (oracle); `tests/unit/test_no_bash.py` checks it.
- Port Bash code literally (word splitting, `read`, associative array order
  ...): helpers for these semantics are in `src/scbi/bashcompat.py`.

## Documentation

`doc/scbi.tex` must be kept in sync with the code: any new or changed
hook, command-line option, environment variable (`SCBI_*`), ini/plan
directive or sub-command needs a matching update there (also check
`bash_completion.d/scbi` and the `usage` function in the driver). The
`README.md` is a short tutorial only.

## Conventions

- Python driver: Python >= 3.11, PyYAML only, no shell (`subprocess` with
  argument lists); report through `scbi.log` (`ilog`, `elog`...) so
  messages reach the build logs.
- Bash driver (testsuite reference): `#!/bin/bash`, 4-space indentation,
  `[[ ... ]]` tests, `local` for every function variable; in `scbi`,
  functions are preceded by a `############################## <name>`
  banner.
- Commit messages: short imperative subject, prefixed by the component when
  scoped, e.g. `c-polyorb: Disable global install.`, `scbi-lint: Add more
  hook checks.`, `test092: Update expected output (archive hook).`
- The `Makefile` derives the core version from the last commit touching
  `src/scbi`, `pyproject.toml`, `scripts.d/[0-9]*`, `scripts.d/_os_*`,
  `scripts.d/.pkgs-*` and the completion file, and the plug-in version
  from `scripts.d/c-*` and `scripts.d/patches`. Keep core and plug-in
  changes in separate commits.

## Repository hygiene

- Untracked artefacts may exist in the tree: never add them to git.
- Do not commit unless asked.
- Never ever push.
