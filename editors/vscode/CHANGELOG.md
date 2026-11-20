# Changelog

## 0.2.1

- Build plans: the directives and the variants are highlighted with the
  themes coloring `keyword` and not `keyword.control` (scopes
  `keyword.other.directive`, `entity.name.tag.variant`).

## 0.2.0

- Build plans (`.plan-<name>`, `.scbi-plan-<name>`): a language with its
  highlighting (directives and their keywords, groups and barriers,
  comments, the variant and the version of the module references) and
  its completion (directives, modules, plans, keywords, special variants
  and versions, variables).

## 0.1.0

First version.

- Plug-ins: diagnostics of `scbi lint` while typing, on open and on save;
  formatting with `scbi format` (*Format Document*, *Format on Save*);
  completion and help of the hooks with the YAML extension (`scbi schema`).
- Builds: the sections of the `.scbi` ini files as tasks (`scbi --ini=<section>`),
  the selected section on the status bar with a button to start it, the
  *SCBI Shell* terminal profile.
