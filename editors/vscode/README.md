# SCBI for Visual Studio Code

Support of [SCBI](https://github.com/TurboGit/scbi) (Source Code Build
Infrastructure), the tool building software from sources with their
dependencies, variants and versions:

- **write plug-ins**: the YAML plug-ins are checked while you type, formatted
  in their canonical form, and the hooks are completed with their help;
- **build your projects**: the sections of your `.scbi` ini files are tasks,
  started from the status bar or with `Ctrl+Shift+B`.

All the work is done by the `scbi` command: the extension shows its
results.

## Requirements

- SCBI installed, the `scbi` command in your `PATH` (or set `scbi.path`).
  From a checkout of the repository: `make` installs it in `~/.local/bin`.
  The extension needs a driver with the `lint --json`, `format --stdin`,
  `schema` and `ini` sub-commands (the Python driver of 2026-11 or later).
- For the completion and the help of the hooks: the
  [YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml)
  (`redhat.vscode-yaml`). Everything else works without it.

## Features

### Plug-ins

A YAML file is an SCBI plug-in when it matches `scbi.pluginPatterns`
(default: the files of a `scripts.d` directory, not the `.env*` ones) or
has a top-level `plugin:` key.

- **Diagnostics**: `scbi lint` runs while you type (after a short pause),
  on open and on save. Errors and warnings are underlined where they are
  (the variable, the line of a command body, the hook) and listed in the
  Problems panel.
- **Formatting**: *Format Document* (and *Format on Save*) writes the
  plug-in in its canonical form (`scbi format`): the hooks in their
  order, a body of one line inline... Only the plug-ins are formatted by
  SCBI: your other YAML files keep their formatter.
- **Completion and help** (with the YAML extension): the hook names, their
  qualifiers (`common`, `_`, `default`, `cross`), the keys of the plug-in
  (`inherit`, `with-variants`, `functions`...), the fields of `vcs` and
  `archive`, and on hover what each hook is for, its parameters and its
  kind. The schema comes from your `scbi` (`scbi schema`): it follows its
  version.

### Builds

In a workspace with SCBI ini files (`.scbi` in the folder, or in your
home directory), each section is a task running `scbi --ini=<section>`:

```ini
[app]
   modules = c-myapp c-mylib

[run-app]
   run = myapp --verbose
```

- **Run Task** lists `scbi: app` (in the build group: it can be the default
  build task, `Ctrl+Shift+B`) and `scbi: run-app` (runs the command).
- **Status bar**: `🔧 <section>` selects the section (remembered for the
  workspace), `▶` builds or runs it.
- **tasks.json**: a task can be written by hand, with more options:

  ```json
  { "type": "scbi", "section": "app", "args": ["--force"] }
  ```

- **Terminal**: the *SCBI Shell* profile (terminal `+` menu) opens a shell
  in the environment of the modules of the selected section
  (`scbi shell <modules>`).

The builds run in the integrated terminal, with the SCBI progress bar.
When a module fails, the path of its log is displayed: click it to open
the log.

## Commands

| Command | |
|---|---|
| SCBI: Lint Plug-in | lint the current YAML file |
| SCBI: Format Plug-in | format the current YAML file |
| SCBI: Select Section | choose the section of the status bar |
| SCBI: Build or Run the Selected Section | start it |

## Settings

| Setting | Default | |
|---|---|---|
| `scbi.path` | `scbi` | the scbi command |
| `scbi.lint.mode` | `onType` | `onType`, `onSave` or `off` |
| `scbi.pluginPatterns` | `["**/scripts.d/[!.]*.yaml"]` | the plug-in files |

The `scbi` command runs in the workspace folder: the `.scbi` ini file of
the folder and your environment files are used, as on the command line.

## Installation

From the Visual Studio Marketplace or Open VSX: search for *SCBI*.

From a `.vsix` file (e.g. built from the repository):

```sh
cd editors/vscode
npm ci
npm run package                 # writes scbi-<version>.vsix
code --install-extension scbi-*.vsix
```

or `make vscode` at the top of the repository.

## Development

```sh
cd editors/vscode
npm ci
npm test        # compile and run the tests (some use the driver of the repository)
```

Open `editors/vscode` in VSCode and press `F5`: a window with the
extension loaded opens.

## License

GPL-3.0-or-later.
