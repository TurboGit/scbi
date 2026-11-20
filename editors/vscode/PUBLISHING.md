# Publishing the extension

The extension is `turbogit.scbi`: publisher `turbogit`, name `scbi`
(`package.json`). This file is not part of the package.

## Before each release

1. Set the version in `package.json` (`npm version <x.y.z> --no-git-tag-version`)
   and add its entry to `CHANGELOG.md`.
2. `npm ci && npm test` (the tests run the driver of the repository).
3. `npm run package`: builds `scbi-<x.y.z>.vsix`; try it with
   `code --install-extension scbi-<x.y.z>.vsix`.
4. Commit, tag (e.g. `vscode-v<x.y.z>`).

## Visual Studio Marketplace (VSCode)

Once:

1. Sign in to <https://marketplace.visualstudio.com/manage> with a
   Microsoft account and create the publisher `turbogit`.
2. In Azure DevOps (<https://dev.azure.com>, same account), create a
   Personal Access Token: *Organization*: **All accessible organizations**,
   *Scopes*: **Marketplace → Manage**.

Each release:

```sh
npx vsce publish --packagePath scbi-<x.y.z>.vsix -p <token>
```

(or `npx vsce login turbogit` once, then `npx vsce publish --packagePath ...`;
the login stores the token with `keytar`, whose install script npm may
block: `npm install-scripts approve keytar`).

## Open VSX (VSCodium, Cursor, Gitpod...)

Once:

1. Sign in to <https://open-vsx.org> (with GitHub), sign the Eclipse
   Publisher Agreement (profile page), create an access token.
2. `npx ovsx create-namespace turbogit -p <token>`.

Each release:

```sh
npx ovsx publish scbi-<x.y.z>.vsix -p <token>
```

## Automation (optional)

Both commands can run in a CI job on a `vscode-v*` tag, the tokens
stored as secrets (`VSCE_PAT`, `OVSX_PAT`: the tools read them from the
environment, no `-p` needed).
