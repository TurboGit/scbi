# SCBI — the Python driver

Release notes of the Python driver (branch `po/python-driver`), compared
with the Bash driver of the `master` branch. The reference manual
(`doc/scbi.tex`) describes every feature in detail.

## Highlights

- **A new driver in Python**, with no Bash at all: the driver, the hooks
  and the steps run without a shell. It is faster and its errors are
  reported with the plug-in file and the line.
- **YAML plug-ins and environment files**: a declarative format, a small
  command language for the steps, checked by `scbi lint` and written in a
  canonical form by `scbi format`. The 107 plug-ins of `scripts.d` are
  converted.
- **Faster updates**: one network access per module with `--update`, none
  without it, and `--update:prefetch` fetching the sources ahead, in
  parallel, while the modules before them are built.
- **Better builds**: a progress bar, one report log per module, the build
  order of the command line computed from the dependencies, interrupted
  builds redone, fewer needless rebuilds.
- **Editor support**: a VSCode extension (lint, format, completion and
  help of the plug-ins, highlighting and completion of the build plans,
  the ini sections as build tasks).

## Requirements and installation

- Python 3.9 or later and PyYAML (`apt install python3-yaml`).
- `make` installs the driver in `~/.local/lib/scbi` with the command
  `~/.local/bin/scbi`, the plug-ins in `~/.config/scbi` and the Bash
  completion. The old Bash tools (`scbi-lint`, `scbi-show`...) are
  removed from `~/.local/bin`.
- SCBI is now distributed under the GNU GPL, version 3 or later.

## Upgrading from the Bash driver

- **Plug-ins**: the driver reads YAML plug-ins only (`<name>.yaml`). A
  Bash plug-in is converted once with

      python3 -m scbi.convert <plug-in>

  The converter writes `<name>.yaml` (canonical form) and reports what it
  cannot convert (code at the top level, loops after a pipe, `case`...),
  to be rewritten by hand. A Bash plug-in found by the driver is refused
  with this hint.
- **Environment files**: `.env-<name>` becomes `.env-<name>.yaml`, converted
  with `python3 -m scbi.envconvert .env-<name>` (settings to `vars`,
  `source` to `inherit`; functions and commands to rewrite by hand).
- **Renamed**: the `os-variants` key is now `with-variants`.
- **Removed**: the `gprbuild-project` built-in (use `ok("gprbuild ...")` in
  a condition), the Bash runtime files, the `module-src` link (where a
  plug-in put its own sources in the source tree): use the `source-tree`
  hook.
- **First build**: the build identifier of a module is now computed from
  its resolved plug-in (see below): the modules are rebuilt once after the
  upgrade.

## Plug-ins (YAML)

- A plug-in maps the hooks to their definition; a hook is a body or a
  mapping of qualifiers: `common`, `_` (the plain hook), `default`, a
  variant, `cross` (nested qualifiers when cross-compiling).
- Three kinds of hooks: command hooks (`config`, `build`...: the command
  language), value hooks (`depends`, `config-options`...: lists) and
  environment hooks (`env`, `build-env`...: lists of actions such as
  `set-var`, `add-to-var`). The items of a list can be guarded with
  `if <condition>:` (`if cross:`, `if on deb,12:`, `if enabled(doc):`,
  `if version(c-gcc) >= 13:`...).
- `vcs` and `archive` as records (`proxy`, `options`, `protocol`, `url`,
  `file`, `dir`).
- `inherit` (the hooks of other plug-ins), `with-variants` (variants using
  the OS packages, e.g. `native`), `variants` (a variant including
  others), `functions` (reusable functions in the command language),
  `vars`.
- **Plug-in variables** (`vars`) are expanded in the context of each hook
  (e.g. `DEBUG: $(is-enabled debug ON OFF)`) and available in all the
  hooks, value and environment hooks included; the inherited ones too.
- `build-<target>` hooks: the build step used with
  `--build-target=<target>`.
- An item of `config-options` expanding to nothing is dropped.

- **`archive-sha256`**: the SHA-256 of the archives (`sha256sum`
  lines); an archive of a different SHA-256 is not extracted, the build
  fails. Not part of the build id; checked by `scbi lint` (format, one
  SHA-256 per file, files of the `archive` hook).
- **`source-tree`**: the source tree of the build made of the sources of
  several modules (e.g. GCC, GNAT in `gcc/ada`, gcc-interface in
  `gcc/ada/gcc-interface`), entries applied in order, each one an exact
  copy of its sources (files removed upstream removed); each `from` must
  be a dependency of the module.

## The command language

The command hooks and the functions are run by the driver, without a
shell: one command per line, `&&`, `||`, pipes and redirections,
variables (`$VAR`, `${VAR:-default}`, `${VAR%pattern}`...).

- Blocks: `if <condition>:` / `elif` / `else`, `for NAME in <words>:` (also
  with several names), `write FILE:` / `append FILE:` (a text, expanded),
  `write-raw FILE:` / `append-raw FILE:` (not expanded).
- Built-in commands: `cd`, `echo`, `export`, `unset`, `return`, `copy`
  (recursive, replaces `cp`), `delete` and `delete-tree` (replace `rm`),
  `check-versions`, `apply-var`, `store-set-key <key> <value>` (records a
  key in the private store, read back with `$(store-key <key>)`), and
  `log <level> <message>` (a message of the driver for the module, on the
  console and in the report log).
- **Safe `copy`, `delete` and `delete-tree`**: they only work in the
  sandbox (`$SCBI_BDIR`, and the install prefix when it is elsewhere).
  Every path is checked first, at its real location (symbolic links
  resolved): a path outside the sandbox is an error of the plug-in,
  nothing is copied or deleted, the hook stops and the step fails, with
  the message on the console. `copy` may also read from the plug-ins directory
  (`$SCBI_PLUGINS`, never written), to copy a file shipped with the
  plug-ins. `delete` refuses a directory (an empty variable in
  `$DIR/$NAME` does not remove a whole tree, the hook stops): use
  `delete-tree`. The directories matched by a glob pattern are skipped
  (`delete dir/*` deletes the files of `dir` only).
  `scbi lint` reports the `cp` and `rm` commands these built-ins can
  replace.
- Functions, as `$(...)` in a word or `NAME = <function> <args>` in an
  assignment: `config-options`, `get-version [<plug-in>]`,
  `get-build-type`, `is-enabled`, `if <condition> then ... else ...`,
  `output` / `output-words` (the output of a command), `command-path`,
  `uppercase`, `lowercase`, `replace`, `first-line`, `basename`, `dirname`,
  `ls`, `last-modified-directory`, `get-os-lib`, `get-os-bin`...,
  `store-key`, `hook-output`, `all-variants`, `all-modules`, and
  `module-dir <module> [install|src|build]` (a directory of a module of
  the build, as `${SCBI_MODULES_DIR[<module>@<kind>]}`).
- Each step writes a replay file: `scbi replay <step>.cmd` reruns the
  step alone, `--trace` shows each command, `--script` (or
  `--script:inline`) writes an equivalent shell script.

## Environment files (YAML)

`.env-<name>.yaml` (and the local `.scbi-env*.yaml`): `inherit`, `vars`,
`passthrough`, `functions`, and the hooks of the driver (`define-var`,
`rewrite-vcs`, `rewrite-archive`, `proxy`, `module-final-step`), in the
command language.

## Builds

- **Progress**: `[n/N] module` with the elapsed time, in a status bar on
  the last row of the terminal (`--progress[:bar|line|no]`,
  `SCBI_PROGRESS`); the bar takes the whole width, the time on the right.
- **Build order**: without `--deps`, the modules of the command line are
  built after their dependencies (the order is displayed when changed).
- **Report log**: one report log per module, complete (no more
  truncation) and without color codes.
- **Interrupted builds**: a build interrupted or failed (Ctrl-C, a change
  of `out-of-tree`...) is redone at the next run, meta-modules included.
- **Build identifier**: computed from the resolved plug-in (the hooks
  selected for the variant and the target, the functions, the variables)
  and the environment of the dependencies. Reformatting a plug-in,
  reordering its keys, its variables, its functions or its dependencies,
  or changing its own `env` hook no longer triggers a rebuild.
- **Binary store** (replaces the build cache `SCBI_CACHE_DIR`): a module
  whose build is in a store (`SCBI_BINARY_STORE`, a directory or a NFS
  mount; `~/.cache/scbi/binaries` by default) is installed from it
  instead of built, its paths relocated to the sandbox; otherwise its
  installation is written to the store. The key covers the build id, the
  keys of the dependencies, the normalized environment of the build and
  the OS: builds are shared between sandboxes and users.
  `scbi binary-store --show-key` displays the keys.
- **Parallel build**: `--parallel[=k]` (with `--deps`) builds up to k
  independent modules at the same time, one `build` or `tests` step at a
  time (`SCBI_BUILD_SLOTS`), the output of each module printed as one
  block; the build ids are the ones of a sequential build.
- **Step times**: the wall and CPU time of each step are recorded in
  `<target>-steps.log`; `--stat:full` summarizes the last run (time in
  the steps using many cores, CPU used).
- **Dependency check**: `--check-deps[:error|:trace]` (ini key
  `check-deps`) reports the files a module uses (dependency files of the
  compilers and of Ninja, shared libraries of its ELF files, imports of
  its Python files) installed by a module of the sandbox which is not one
  of its dependencies, and the dependencies none of whose files is used;
  `:trace` records everything the steps open or run with `strace`
  (tools, data, Python imports).
- **Aggregation**: the dependencies of the modules aggregated by a direct
  aggregate meta-module are not aggregated; a `build-depends` on a
  meta-module never uses the aggregated mode.

## Cross compilation

- **The environment comes from the plug-ins only**: the driver adds no
  compiler environment of its own (the `system-compiler` setting and the
  driver cross environment are removed). The plug-in `c-sandbox`, first
  item of the `build-depends`, gives the base environment with its
  variants: `c-sandbox` (the native sandbox, or the target with
  `--target`: the cross compiler and binutils of the sandbox, `pkg-config`
  and `cmake` set for the target libraries), `c-sandbox/host` (the tools
  running on the host, e.g. to build a cross compiler) and
  `c-sandbox/system` (the compiler and tools of the system only).
- **`host@` dependencies**: as the `:native` build dependencies of Debian,
  `host@<module>` in `depends`, `build-depends` or `tests-depends` is a
  tool running on the build machine (`host@c-gprbuild`, `host@c-cmake`).
  In a native build it is the module itself; in a cross build the module
  is not built for the target, its build for the host is used: its
  environment, `$PREFIX` and `module-dir`, and its build id (a new build
  of the tool rebuilds the module). With `--deps` it is built for the
  host by a run of the driver without `--target`; a `host@` aggregate
  meta-module gives the environment of its modules.
- **`native` discriminant**: set for a native build, as `cross` for a
  cross build: `if on native:` in a plug-in, `@on native use ...` or a
  barrier in a build plan.
- Many plug-ins fixed for cross builds (binutils, GNAT tools, AWS,
  libadalang-tools, gpr2...).

## Sources and updates

- Git, Subversion, Mercurial and archives (download with `cp`, `scp`,
  `curl`, `wget`, `ftp`), with the proxy settings of the environment file.
- **`--update`**: one fetch per git module (the tags were fetched twice).
- **Without `--update` the remote is not accessed**: a module is built from
  the commits fetched last time (the Bash driver fetched the tags, and so
  the new commits, at every build). A module whose reference changes is
  still updated. The fetches use `origin` only.
- **`--update:prefetch`** (or `update = prefetch` in an ini file): the git
  clones and the archives of the modules of the build are updated ahead,
  in parallel (`SCBI_PREFETCH_JOBS`, default 4), while the modules before
  them are built; a module then only switches to its reference or
  extracts its archive. The result and the messages are those of
  `--update`. On a large project (143 modules, all up-to-date) the update
  went from 42 s to 15 s with the single fetch alone.

## Sub-commands

- `scbi lint`: checks the YAML plug-ins: unknown hooks and keys (with the
  closest name), structure, values, conditions, environment actions;
  warnings for empty hooks, `out-of-tree` in a meta-module, variables not
  known in a hook (knowing the variables of the environment file, of the
  dependencies — their `env` hooks and `with-variants` — and of the
  inherited plug-ins; not the text of the raw blocks), variables set but
  never used, invalid `log` levels. `--json` (issues with their line and
  column) and `--stdin` for the editors.
- `scbi format`: the canonical form (key order, `common` first, a body of
  one line inline); `--replace`, `--stdin`.
- `scbi show --resolved`: the plug-in of a module as the driver uses it
  for a variant and a target.
- `scbi show --freeze`: the build plan of the last build with every
  reference pinned (Git commits, archive versions), to rebuild the same
  sources later; the references not pinned are commented.
- `scbi show --json`: the graph of the build (modules, versions,
  sources, licenses, dependencies); `scbi show --sbom`: a CycloneDX 1.5
  SBOM. The new `license` hook (an SPDX expression) is not part of the
  build id.
- `scbi show --archive-sha256`: the `archive-sha256` lines of the
  archives of a build, to paste in the plug-ins.
- `scbi schema`: the JSON Schema of the plug-ins (completion and help in
  the editors).
- `scbi ini`: the sections of the ini files (`--json`).
- `scbi replay`: see *The command language*.
- `scbi store`, `scbi shell` (honours the `run` key of the ini files),
  `scbi source-archive`: ported.

## VSCode extension

In `editors/vscode` (`make vscode` builds the `.vsix`):

- plug-ins: diagnostics of `scbi lint` while typing, *Format Document* with
  `scbi format`, completion and help of the hooks (with the YAML
  extension);
- build plans (`.plan-*`, `.scbi-plan-*`): highlighting (directives,
  groups and barriers, variants and versions) and completion;
- the sections of the `.scbi` ini files as tasks (`Ctrl+Shift+B`), the
  selected section and a run button in the status bar, an *SCBI Shell*
  terminal.

## OS packages

The `.pkgs-<distrib>` lists (Debian, Ubuntu, Fedora, CentOS, Red Hat,
MinGW) are synchronized with the Debian one; MinGW uses the UCRT64
packages.

## Testsuite (contributors)

The regression testsuite is now pytest (`make test`, drivers
`tests/drivers/testNNN.py`, parallel with pytest-xdist), with unit tests
(`make unit`); `make lint` checks the plug-ins of `scripts.d`.
