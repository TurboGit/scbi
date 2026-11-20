// Tests of the parts independent of VSCode (node --test), the last ones
// running the driver of this repository (python3 -m scbi).

import * as assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import { formatArgs, isPluginText, lintArgs, parseLintOutput, run, wordEnd } from "../src/core";

test("parseLintOutput: the JSON list after other output", () => {
  const issues = parseLintOutput('\x1b[37m[\n {"file": "p.yaml", "line": 2, "column": 3, "level": "warning",'
    + ' "hook": "config", "message": "m"}\n]\n');
  assert.deepEqual(issues, [{ file: "p.yaml", line: 2, column: 3, level: "warning", hook: "config", message: "m" }]);
  assert.deepEqual(parseLintOutput("[]\n"), []);
  assert.throws(() => parseLintOutput("error: x\n"));
});

test("isPluginText: a top-level plugin key", () => {
  assert.ok(isPluginText("# c\nplugin: c-foo\nconfig: make\n"));
  assert.ok(!isPluginText("config:\n  plugin: x\n"));
  assert.ok(!isPluginText("plugin:\n"));
});

test("wordEnd: a variable, a key, a word", () => {
  assert.equal(wordEnd("  cmake $NOPE ../src", 8), 13);
  assert.equal(wordEnd("  x=${NOPE}y", 4), 11);
  assert.equal(wordEnd("out-of-tre: true", 0), 10);
  assert.equal(wordEnd("", 0), 1);
});

const REPO = path.resolve(__dirname, "../../../..");
const SCBI = ["-m", "scbi"];

function driver(args: string[], input: string, cwd: string) {
  process.env.PYTHONPATH = path.join(REPO, "src");
  return run("python3", [...SCBI, ...args], input, cwd);
}

test("lint and format with the driver", async () => {
  const dir = mkdtempSync(path.join(tmpdir(), "scbi-vscode-"));
  const file = path.join(dir, "edit.yaml");
  writeFileSync(file, "plugin: edit\nconfig: make\n");
  //  the text given (unsaved buffer), not the file
  const lint = await driver(lintArgs(file), "plugin: edit\nconfig: |-\n  cmake $NOPE ../src\n", dir);
  assert.equal(lint.status, 0, lint.stderr);
  const issues = parseLintOutput(lint.stdout);
  assert.deepEqual(issues.map((i) => [i.line, i.column, i.level, i.message]),
    [[3, 9, "warning", "variable NOPE is not known in this hook"]]);
  const fmt = await driver(formatArgs(file), "config: |-\n  make\nplugin: edit\n", dir);
  assert.equal(fmt.status, 0, fmt.stderr);
  assert.equal(fmt.stdout, "plugin: edit\n\nconfig: make\n");
  assert.equal(readFileSync(file, "utf8"), "plugin: edit\nconfig: make\n");
  //  invalid YAML: not formatted, status 1
  const bad = await driver(formatArgs(file), "config: [\n", dir);
  assert.equal(bad.status, 1);
  assert.equal(bad.stdout, "");
});
