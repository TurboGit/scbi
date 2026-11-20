// The parts of the extension independent of the VSCode API: running the
// scbi command and reading its output (tested with plain Node).

import { spawn } from "node:child_process";

/** An issue of `scbi lint --json` (line and column 1-based, 0: unknown). */
export interface LintIssue {
  file: string;
  line: number;
  column: number;
  level: "error" | "warning";
  hook: string;
  message: string;
}

export interface RunResult {
  status: number;
  stdout: string;
  stderr: string;
}

/** The global options of every call: no colors (the escape codes of the
 * `color` setting of the ini file would break the JSON output). */
const GLOBAL = ["--color:no"];

export function lintArgs(file: string): string[] {
  return [...GLOBAL, "lint", "--json", "--stdin", file];
}

export function formatArgs(file: string): string[] {
  return [...GLOBAL, "format", "--stdin", file];
}

export function schemaArgs(): string[] {
  return [...GLOBAL, "schema"];
}

export function iniArgs(): string[] {
  return [...GLOBAL, "ini", "--json"];
}

/** A section of the ini files (`scbi ini --json`), started with
 * `scbi --ini=<name>`: a build of its modules, or its run command. */
export interface Section {
  name: string;
  file: string;
  modules: string;
  run: string;
  tests: string;
}

/** The JSON list of an output (without the escape sequences of the
 * colors, other output before it). */
function jsonList(stdout: string, what: string): unknown[] {
  stdout = stdout.replace(/\x1b\[[0-9;?]*[A-Za-z]/g, "");
  const start = stdout.indexOf("[");
  const end = stdout.lastIndexOf("]");
  if (start < 0 || end < start) {
    throw new Error(`no JSON list in the output of ${what}`);
  }
  const data = JSON.parse(stdout.slice(start, end + 1));
  if (!Array.isArray(data)) {
    throw new Error(`the output of ${what} is not a list`);
  }
  return data;
}

export function parseSections(stdout: string): Section[] {
  return jsonList(stdout, "scbi ini") as Section[];
}

/** The command line of the task of a section. */
export function sectionArgs(section: string, extra: string[] = []): string[] {
  return [`--ini=${section}`, ...extra];
}

/** The arguments of a shell in the environment of a section: its modules
 * (a section running a command gives no module: a plain scbi shell). */
export function shellArgs(section: Section | undefined): string[] {
  return section && !section.run && section.modules ? ["shell", ...section.modules.split(/\s+/)] : ["shell"];
}

/** The issues of the output of `scbi lint --json` (the JSON list may be
 * preceded by other output of the driver). */
export function parseLintOutput(stdout: string): LintIssue[] {
  return jsonList(stdout, "scbi lint") as LintIssue[];
}

/** A YAML text with a top-level `plugin:` key: an SCBI plug-in. */
export function isPluginText(text: string): boolean {
  return /^plugin:[ \t]*\S/m.test(text);
}

/** The end (exclusive, 0-based) of the word starting at `column` (0-based)
 * in `line`: a variable ($NAME, ${NAME}) or the text up to a blank or a
 * ':' (a key). */
export function wordEnd(line: string, column: number): number {
  const rest = line.slice(column);
  const m = /^\$\{[^}]*\}|^\$\w+|^[^\s:]+/.exec(rest);
  return m ? column + m[0].length : Math.max(line.length, column + 1);
}

/** Run `command args` with `input` on its standard input. */
export function run(command: string, args: string[], input: string, cwd: string,
                    signal?: AbortSignal): Promise<RunResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, signal, stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8").on("data", (d: string) => (stdout += d));
    child.stderr.setEncoding("utf8").on("data", (d: string) => (stderr += d));
    child.on("error", reject);
    child.on("close", (code) => resolve({ status: code ?? 1, stdout, stderr }));
    child.stdin.on("error", () => undefined); // the command may not read it all
    child.stdin.end(input);
  });
}
