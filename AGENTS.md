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
| `scripts.d/.env.yaml`, `.plan-default`, `.pkgs-<distrib>` | Default environment file (YAML), default build plan, mapping of `os@-<name>` dependencies to distribution packages. |
| `bash_completion.d/scbi` | Bash completion. |
| `editors/vscode/` | VSCode extension (TypeScript): calls `scbi lint --json`, `format --stdin`, `schema`, `ini --json`. `make vscode` (tests + `.vsix`), `make vscode-smoke` (loaded in VSCode). |
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
make test         # full regression testsuite (pytest, tests/drivers)
make doc          # build doc/scbi.pdf (latex, bibtex, makeindex, pdflatex)
make sync-os-deps # propagate/sort .pkgs-* files across distributions
```

`make` overwrites files in `~/.config/scbi` (tracked in
`~/.config/scbi/.core.plugins`), `~/.local/lib/scbi` and `~/.local/bin`
(it removes the old Bash `scbi-*` tools there); do not run it unless the
user asks (`make HOME=<tmp>` installs into a temporary directory).

### Testsuite

```bash
make test                    # all the drivers, JUnit report tests/junit.xml
make test T="test001 test092"   # some drivers (or tests/run test001 ...)
make unit                    # pytest unit tests (tests/unit)
python3 -m pytest tests/drivers/test001.py   # one driver directly
```

- The regression drivers are pytest tests, `tests/drivers/testNNN.py`,
  one test function `test(t)` each, with the harness `tests/harness.py`
  (fixture `t` in `tests/drivers/conftest.py`). Each driver runs in its
  own copy of the test root (`scripts.d`, `.root/repos`...) in a
  temporary directory, so drivers are independent; they run in parallel
  when pytest-xdist is installed (`-n auto`).
- `t.runs("./scbi ...")` / `t.nruns(...)` run a command (status 0 / not
  0); `./scbi` runs the driver in the test process
  (`SCBI_TEST_SUBPROCESS=1` runs it as a process, to debug), other
  commands with bash. Checks on the output of the last command:
  `t.clean_diff("""...""")` (masks time-stamps, the directory of the
  test, hashes), `t.diff`, `t.grep`, `t.ngrep`; on values: `t.ok`,
  `t.nok` (as `test`), `t.is_`, `t.isnt`. Output filters:
  `t.trim_output()`, `t.sort_output()`... Shell steps: `t.sh("...")`
  (variables, exported functions and directory kept, the output as the
  file `$TEST_OUTPUT`), `t.set`, `t.unset`, `t.cd`; `t.text("...")`
  expands a text as an unquoted here-document. A driver using an
  external tool is marked `@pytest.mark.requires("hg", ...)`: skipped
  when the tool is not installed.
- A failing check does not stop the driver: all failures are reported at
  the end with their line and a diff.
- `tests/scripts.d/` holds the test-only YAML plug-ins (no `c-` prefix),
  plans and YAML environment files; `tests/.root/repos` holds the small
  Git/SVN/Mercurial repositories and archives they build from. A driver
  may change the plug-ins of its copy freely.
- Test knobs of the driver are under `SCBI_TESTSUITE=yes`: no
  `$HOME/.scbi`, `SCBI_OS_MODULE`, fake OS `SCBI_OS_NAME=test` with
  `SCBI_TEST_PKGS`, `TODAY` from the environment, `SCBI_TEST_PROGRESS=yes`
  (the build progress printed as lines `progress [n/N] module`).
- When adding a test, create `tests/drivers/testNNN.py` with the next free
  number.
- A behavior change in the driver usually changes expected output in
  several drivers; update them and say which in the commit.
- `tests/fixtures/` holds the inputs of the YAML tools (`lint`, `format`)
  and, in `tests/fixtures/bash`, Bash plug-ins used by the unit tests of
  the converter only.

### Python driver

The driver (`src/scbi/`) runs no Bash at all: it reads YAML plug-ins and
YAML environment files only (start-up settings in `src/scbi/setup.py`).

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
- The environment files are YAML (`.env-<name>.yaml`,
  `src/scbi/envyaml.py`: `inherit`, `vars`, `passthrough`, `functions`
  `define-var`, `rewrite-vcs`, `rewrite-archive`, `proxy`,
  `module-final-step` in the command language, the final step context
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

- Python driver: Python >= 3.9 (no 3.10+ syntax or library features:
  `match`, runtime `X | Y` types, `glob(root_dir=)`, `zip(strict=)`...;
  `tests/unit/test_py39.py` checks some), PyYAML only, no shell (`subprocess` with
  argument lists); report through `scbi.log` (`ilog`, `elog`...) so
  messages reach the build logs.
- Test drivers: Python (pytest, `tests/harness.py`), expected outputs as
  triple-quoted strings; Bash code given to `t.sh` uses `[[ ... ]]` tests.
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
