// Run inside VSCode (extensionTestsPath): the features on the workspace
// prepared by run.ts.

import * as assert from "node:assert/strict";
import * as path from "node:path";
import * as vscode from "vscode";

async function until<T>(what: string, get: () => T | undefined | Promise<T | undefined>, ms = 20000): Promise<T> {
  const end = Date.now() + ms;
  for (;;) {
    const value = await get();
    if (value !== undefined) {
      return value;
    }
    if (Date.now() > end) {
      throw new Error(`timeout: ${what}`);
    }
    await new Promise((r) => setTimeout(r, 200));
  }
}

export async function run(): Promise<void> {
  const ws = vscode.workspace.workspaceFolders![0].uri.fsPath;
  const uri = vscode.Uri.file(path.join(ws, "scripts.d", "smoke.yaml"));
  const doc = await vscode.workspace.openTextDocument(uri);
  await vscode.window.showTextDocument(doc);

  //  diagnostics at the variable
  const diags = await until("diagnostics", () => {
    const d = vscode.languages.getDiagnostics(uri);
    return d.length ? d : undefined;
  });
  assert.equal(diags[0].message, "variable NOPE is not known in this hook");
  assert.equal(diags[0].range.start.line, 1);
  assert.equal(doc.getText(diags[0].range), "$NOPE");
  console.log("ok: diagnostics");

  //  formatting: the canonical form
  const edits = await vscode.commands.executeCommand<vscode.TextEdit[]>(
    "vscode.executeFormatDocumentProvider", uri, { tabSize: 2, insertSpaces: true });
  assert.ok(edits?.length);
  const edit = new vscode.WorkspaceEdit();
  edit.set(uri, edits);
  assert.ok(await vscode.workspace.applyEdit(edit));
  assert.equal(doc.getText(), "plugin: smoke\n\nconfig: cmake $NOPE ../src\n");
  console.log("ok: formatting");

  //  the sections as tasks
  const tasks = await vscode.tasks.fetchTasks({ type: "scbi" });
  const mine = tasks.filter((t) => t.name === "smoke" || t.name === "run-smoke");
  assert.deepEqual(mine.map((t) => [t.name, t.group?.id ?? ""]).sort(),
    [["run-smoke", ""], ["smoke", vscode.TaskGroup.Build.id]]);
  const exec = mine.find((t) => t.name === "smoke")!.execution as vscode.ProcessExecution;
  assert.deepEqual(exec.args, ["--ini=smoke"]);
  console.log("ok: tasks");

  //  the commands are registered
  const commands = await vscode.commands.getCommands(true);
  for (const c of ["scbi.lint", "scbi.format", "scbi.selectSection", "scbi.runSection"]) {
    assert.ok(commands.includes(c), c);
  }
  console.log("ok: commands");
}
