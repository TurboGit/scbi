// SCBI for VSCode: the YAML plug-ins linted (diagnostics) and formatted
// (formatting provider) by the scbi command.

import * as path from "node:path";
import * as vscode from "vscode";
import { formatArgs, isPluginText, lintArgs, LintIssue, parseLintOutput, run, wordEnd } from "./core";

let diagnostics: vscode.DiagnosticCollection;
let output: vscode.OutputChannel;
//  the lint running for a document (cancelled by a newer one)
const running = new Map<string, AbortController>();
const timers = new Map<string, NodeJS.Timeout>();
let missingReported = false;

function config() {
  return vscode.workspace.getConfiguration("scbi");
}

function command(): string {
  return config().get<string>("path") || "scbi";
}

function patterns(): string[] {
  return config().get<string[]>("pluginPatterns") ?? [];
}

/** A YAML file matching the patterns, or with a top-level plugin: key. */
export function isPlugin(doc: vscode.TextDocument): boolean {
  if (doc.languageId !== "yaml" || doc.uri.scheme !== "file") {
    return false;
  }
  if (patterns().some((pattern) => vscode.languages.match({ pattern }, doc) > 0)) {
    return true;
  }
  return isPluginText(doc.getText());
}

/** The directory the command runs in: the workspace folder of the file
 * (its .scbi ini file, its environment), else the directory of the file. */
function cwdOf(doc: vscode.TextDocument): string {
  const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
  return folder ? folder.uri.fsPath : path.dirname(doc.uri.fsPath);
}

function reportFailure(err: unknown): void {
  const e = err as NodeJS.ErrnoException;
  if (e.name === "AbortError") {
    return;
  }
  if (e.code === "ENOENT") {
    if (!missingReported) {
      missingReported = true;
      void vscode.window.showErrorMessage(
        `SCBI: the command '${command()}' is not found: install SCBI or set 'scbi.path'.`);
    }
    return;
  }
  output.appendLine(`scbi: ${e.message ?? String(err)}`);
}

function toDiagnostic(doc: vscode.TextDocument, issue: LintIssue): vscode.Diagnostic {
  const lineNo = Math.min(Math.max(issue.line - 1, 0), Math.max(doc.lineCount - 1, 0));
  const text = doc.lineAt(lineNo).text;
  const start = Math.min(Math.max(issue.column - 1, 0), text.length);
  const range = new vscode.Range(lineNo, start, lineNo, Math.min(wordEnd(text, start), Math.max(text.length, start)));
  const severity = issue.level === "error" ? vscode.DiagnosticSeverity.Error : vscode.DiagnosticSeverity.Warning;
  const d = new vscode.Diagnostic(range, issue.message, severity);
  d.source = "scbi lint";
  d.code = issue.hook || undefined;
  return d;
}

async function lint(doc: vscode.TextDocument): Promise<void> {
  const key = doc.uri.toString();
  running.get(key)?.abort();
  const controller = new AbortController();
  running.set(key, controller);
  try {
    const res = await run(command(), lintArgs(doc.uri.fsPath), doc.getText(), cwdOf(doc), controller.signal);
    if (controller.signal.aborted) {
      return;
    }
    let issues: LintIssue[];
    try {
      issues = parseLintOutput(res.stdout);
    } catch (e) {
      output.appendLine(`scbi lint: ${(e as Error).message}\n${res.stdout}${res.stderr}`);
      return;
    }
    diagnostics.set(doc.uri, issues.filter((i) => i.line > 0).map((i) => toDiagnostic(doc, i)));
  } catch (err) {
    reportFailure(err);
  } finally {
    if (running.get(key) === controller) {
      running.delete(key);
    }
  }
}

function schedule(doc: vscode.TextDocument, delay: number): void {
  const key = doc.uri.toString();
  clearTimeout(timers.get(key));
  timers.set(key, setTimeout(() => {
    timers.delete(key);
    void lint(doc);
  }, delay));
}

async function format(doc: vscode.TextDocument): Promise<vscode.TextEdit[]> {
  try {
    const res = await run(command(), formatArgs(doc.uri.fsPath), doc.getText(), cwdOf(doc));
    if (res.status !== 0) {
      //  an invalid plug-in is not formatted: the lint tells why
      void vscode.window.setStatusBarMessage(`SCBI: not formatted: ${res.stderr.trim()}`, 5000);
      return [];
    }
    if (res.stdout === doc.getText()) {
      return [];
    }
    const all = new vscode.Range(doc.positionAt(0), doc.positionAt(doc.getText().length));
    return [vscode.TextEdit.replace(all, res.stdout)];
  } catch (err) {
    reportFailure(err);
    return [];
  }
}

export function activate(context: vscode.ExtensionContext): void {
  diagnostics = vscode.languages.createDiagnosticCollection("scbi");
  output = vscode.window.createOutputChannel("SCBI");
  context.subscriptions.push(diagnostics, output);

  const mode = () => config().get<string>("lint.mode") ?? "onType";
  const maybeLint = (doc: vscode.TextDocument) => {
    if (mode() !== "off" && isPlugin(doc)) {
      void lint(doc);
    }
  };

  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument(maybeLint),
    vscode.workspace.onDidSaveTextDocument(maybeLint),
    vscode.workspace.onDidChangeTextDocument((e) => {
      if (mode() === "onType" && e.contentChanges.length && isPlugin(e.document)) {
        schedule(e.document, 500);
      }
    }),
    vscode.workspace.onDidCloseTextDocument((doc) => {
      running.get(doc.uri.toString())?.abort();
      diagnostics.delete(doc.uri);
    }),
    //  Format Document / format on save: the plug-ins of the patterns
    //  (registering for all the YAML files would take over their formatting)
    ...patterns().map((pattern) =>
      vscode.languages.registerDocumentFormattingEditProvider(
        { language: "yaml", scheme: "file", pattern },
        { provideDocumentFormattingEdits: (doc) => (isPlugin(doc) ? format(doc) : []) })),
    vscode.commands.registerCommand("scbi.lint", () => {
      const doc = vscode.window.activeTextEditor?.document;
      if (doc && doc.languageId === "yaml") {
        void lint(doc);
      }
    }),
    vscode.commands.registerCommand("scbi.format", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.document.languageId !== "yaml") {
        return;
      }
      const edits = await format(editor.document);
      if (edits.length) {
        await editor.edit((b) => edits.forEach((e) => b.replace(e.range, e.newText)));
      }
    }),
  );

  vscode.workspace.textDocuments.forEach(maybeLint);
}

export function deactivate(): void {
  running.forEach((c) => c.abort());
  timers.forEach((t) => clearTimeout(t));
}
