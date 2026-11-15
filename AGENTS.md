# AGENTS.md — SCBI

SCBI (Source Code Build Infrastructure) builds software from sources (VCS
checkouts or archives), handles dependencies, variants, versions, build
plans and developers' local checkouts. The driver is Python (`src/scbi`,
python3 + PyYAML, no compile step); the plug-ins are YAML files. The
former Bash driver is on the master branch only.

## Repository layout

| Path | What it is |
|------|------------|
| `src/scbi/` | **The driver** (Python package, `python3 -m scbi`), installed by `make` as `~/.local/bin/scbi`. See *Python driver* below. |
| `scripts.d/c-*.yaml` | **Plug-ins**: one YAML file per buildable project/module. |
| `scripts.d/patches/` | Patches referenced by plug-ins' `patches` hooks. |
| `scripts.d/.env.py`, `.plan-default`, `.pkgs-<distrib>` | Default environment (Python), default build plan, mapping of `os@-<name>` dependencies to distribution packages. |
| `bash_completion.d/scbi` | Bash completion. |
| `doc/scbi.tex` | Reference manual (LaTeX). The authoritative spec for hooks, options, env variables, plans and ini files. |
| `tests/` | Regression testsuite (see below). |

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

```bash
make test      # all the drivers (tests/run)
make unit      # pytest unit tests (tests/unit)
cd tests && ./run test001 test092   # some drivers
```

- `tests/run` writes a `tests/scbi` wrapper running the driver of
  `src/scbi`, copies `.pkgs-*` into
  `tests/scripts.d/` (git-ignored copies, never edit them), exports the
  testsuite settings (`SCBI_TESTSUITE=yes`, `SCBI_ROOT=tests/.root`...),
  then sources each `tests/drivers/testNNN`.
- Tests use the `osht` TAP framework (`RUNS`, `IS`, `DIFF`, ...). Expected
  output is inline in the driver as a heredoc passed to `CLEAN-DIFF`, which
  masks time-stamps, `$PWD`, and hashes.
- `tests/scripts.d/` holds the test-only YAML plug-ins (no `c-` prefix),
  plans and Python environment files; `tests/.root/repos` holds the small
  Git/SVN/Mercurial repositories and archives they build from. A driver
  changing a plug-in edits its `.yaml` file (and restores it).
- Test knobs of the driver are under `SCBI_TESTSUITE=yes`: no
  `$HOME/.scbi`, `SCBI_OS_MODULE`, fake OS `SCBI_OS_NAME=test` with
  `SCBI_TEST_PKGS`, `TODAY` from the environment.
- When adding a test, create `tests/drivers/testNNN` with the next free
  number and bump the `PLAN <n>` count in `tests/run` by the number of new
  assertions. The `PLAN` count is only applied when running the whole
  suite.
- A behavior change in the driver usually changes expected output in
  several drivers; update them and say which in the commit.
- `tests/fixtures/` holds the inputs of the YAML tools (`lint`, `format`)
  and, in `tests/fixtures/bash`, Bash plug-ins used by the unit tests of
  the converter only.

### Python driver

The driver (`src/scbi/`) runs no Bash at all: it reads YAML plug-ins and
Python environment files only (start-up settings in `src/scbi/setup.py`).

- With the Python driver `scbi lint` and `scbi format` handle YAML
  plug-ins only (`plugin/lint.py`, `plugin/yamlwrite.py`, canonical key
  order `catalog.FORMAT_ORDER`); Bash plug-ins are converted with
  `python3 -m scbi.convert`.
- The driver only uses the plug-in model (`plugin/model.py`). YAML is
  confined to its reader/writer (`plugin/yamlfmt.py`, `plugin/yamlwrite.py`)
  and the YAML tools (lint, format, converter). Readers find files through
  `plugin/formats.py` (suffix → reader; add a format there) and build the
  model with `plugin/construct.py` (checks common to all formats).
- Command hooks and functions of YAML plug-ins are in the command
  language (`hooks/cmdlang.py`), run by the interpreter, never by Bash
  (`steps/interp.py`, isolated environment `steps/hookenv.py`, replay
  files `steps/replay.py` / `scbi replay`). Steps are run by
  `steps/wrapper.py` and `steps/generic.py`.
- The environment files are Python (`.env-<name>.py`,
  `src/scbi/envpy.py`: settings, `PASSTHROUGH`, hooks `define_var`,
  `rewrite_vcs`, `rewrite_archive`, `proxy`, `module_final_step` with
  `steps/final.py`); Bash ones are converted with
  `python3 -m scbi.envconvert`.
- The module environment is `steps/modenv.py`, the OS packages and auto
  variants `ospkg.py`, `--standalone` `standalone.py`, `scbi shell`
  `tools/shell.py` (spawns the user's `$SHELL`). Bash runs only in the
  migration tools (`scbi.convert`, `scbi.envconvert`, `plugin/legacy.py`,
  `plugin/lift*.py`); `tests/unit/test_no_bash.py` checks it.
- Some code keeps Bash semantics (word splitting, `read`, associative
  array order...) of the former driver: helpers are in
  `src/scbi/bashcompat.py`.

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
- Test drivers (Bash, osht): `#!/bin/bash` style, 4-space indentation,
  `[[ ... ]]` tests.
- Commit messages: short imperative subject, prefixed by the component when
  scoped, e.g. `c-polyorb: Disable global install.`, `scbi lint: Add more
  hook checks.`, `test104: Update expected output (archive hook).`
- The `Makefile` derives the core version from the last commit touching
  `src/scbi`, `pyproject.toml`, `scripts.d/.pkgs-*` and the completion
  file, and the plug-in version
  from `scripts.d/c-*` and `scripts.d/patches`. Keep core and plug-in
  changes in separate commits.

## Repository hygiene

- Untracked artefacts may exist in the tree: never add them to git.
- Do not commit unless asked.
- Never ever push.
