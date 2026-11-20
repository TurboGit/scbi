// Smoke test: the extension loaded in VSCode (an existing VSCode binary,
// SCBI_VSCODE or code from the PATH; a temporary profile), on a
// workspace with a plug-in and an ini file, the driver of the repository
// as scbi. Run with: npm run smoke (xvfb-run without a display).

import { execFileSync } from "node:child_process";
import { chmodSync, mkdirSync, mkdtempSync, realpathSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { runTests } from "@vscode/test-electron";

async function main(): Promise<void> {
  const root = path.resolve(__dirname, "../../..");
  const repo = path.resolve(root, "../..");
  const tmp = mkdtempSync(path.join(tmpdir(), "scbi-smoke-"));
  const ws = path.join(tmp, "ws");
  mkdirSync(path.join(ws, "scripts.d"), { recursive: true });
  mkdirSync(path.join(ws, ".vscode"));
  //  the driver of the repository as the scbi command
  const scbi = path.join(tmp, "scbi");
  writeFileSync(scbi, `#!/bin/sh\nPYTHONPATH='${repo}/src' exec python3 -m scbi "$@"\n`);
  chmodSync(scbi, 0o755);
  writeFileSync(path.join(ws, ".vscode", "settings.json"), JSON.stringify({ "scbi.path": scbi }));
  writeFileSync(path.join(ws, "scripts.d", "smoke.yaml"),
    "config: |-\n  cmake $NOPE ../src\nplugin: smoke\n");
  writeFileSync(path.join(ws, ".scbi"), "[smoke]\n   modules = smoke\n[run-smoke]\n   run = echo hi\n");
  const code = process.env.SCBI_VSCODE
    ?? realpathSync(execFileSync("sh", ["-c", "command -v code"]).toString().trim());
  //  /usr/bin/code is a script: the Electron binary is next to resources/
  const binary = path.basename(code) === "code" && code.endsWith("/bin/code")
    ? path.resolve(path.dirname(code), "../code") : code;
  //  set when run from a terminal of VSCode: the binary would start as Node
  delete process.env.ELECTRON_RUN_AS_NODE;
  await runTests({
    vscodeExecutablePath: binary,
    extensionDevelopmentPath: root,
    extensionTestsPath: path.join(__dirname, "suite.js"),
    launchArgs: [ws, "--disable-extensions", `--user-data-dir=${path.join(tmp, "user")}`,
                 `--extensions-dir=${path.join(tmp, "ext")}`, "--disable-workspace-trust"],
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
