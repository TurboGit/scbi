// The sections of the ini files (.scbi) as tasks: a build of their
// modules, or their run command (scbi --ini=<section>); the selected
// section on the status bar; a terminal in the environment of its modules.

import * as vscode from "vscode";
import { iniArgs, parseSections, run, Section, sectionArgs, shellArgs } from "./core";

const TYPE = "scbi";
const STATE_KEY = "scbi.section";

interface ScbiTaskDefinition extends vscode.TaskDefinition {
  section: string;
  args?: string[];
}

export class Sections {
  private select: vscode.StatusBarItem;
  private start: vscode.StatusBarItem;
  private known = new Map<string, Section[]>();

  constructor(private context: vscode.ExtensionContext, private command: () => string,
              private output: vscode.OutputChannel, private report: (err: unknown) => void) {
    this.select = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
    this.select.command = "scbi.selectSection";
    this.start = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 49);
    this.start.command = "scbi.runSection";
    this.start.text = "$(play)";
    context.subscriptions.push(
      this.select,
      this.start,
      vscode.tasks.registerTaskProvider(TYPE, {
        provideTasks: () => this.provideTasks(),
        resolveTask: (task) => this.resolveTask(task),
      }),
      vscode.commands.registerCommand("scbi.selectSection", () => this.pick()),
      vscode.commands.registerCommand("scbi.runSection", () => this.runSelected()),
      vscode.window.registerTerminalProfileProvider("scbi.shell", {
        provideTerminalProfile: () => this.shellProfile(),
      }),
      vscode.workspace.onDidChangeWorkspaceFolders(() => void this.refresh()),
    );
    const watcher = vscode.workspace.createFileSystemWatcher("**/.scbi");
    watcher.onDidChange(() => void this.refresh());
    watcher.onDidCreate(() => void this.refresh());
    watcher.onDidDelete(() => void this.refresh());
    context.subscriptions.push(watcher);
    void this.refresh();
  }

  private folder(): vscode.WorkspaceFolder | undefined {
    const doc = vscode.window.activeTextEditor?.document;
    return (doc && vscode.workspace.getWorkspaceFolder(doc.uri)) ?? vscode.workspace.workspaceFolders?.[0];
  }

  /** The sections of a workspace folder (its .scbi and $HOME/.scbi). */
  async sections(folder: vscode.WorkspaceFolder): Promise<Section[]> {
    try {
      const res = await run(this.command(), iniArgs(), "", folder.uri.fsPath);
      const found = parseSections(res.stdout);
      this.known.set(folder.uri.toString(), found);
      return found;
    } catch (err) {
      this.report(err);
      return [];
    }
  }

  private selected(): string | undefined {
    return this.context.workspaceState.get<string>(STATE_KEY);
  }

  async refresh(): Promise<void> {
    const folder = this.folder();
    const found = folder ? await this.sections(folder) : [];
    if (!found.length) {
      this.select.hide();
      this.start.hide();
      return;
    }
    const name = this.selected();
    const section = found.find((s) => s.name === name);
    this.select.text = `$(tools) ${section ? section.name : "SCBI"}`;
    this.select.tooltip = section ? `SCBI section: ${describe(section)}. Click to change.` : "Select an SCBI section";
    this.start.tooltip = section ? `scbi --ini=${section.name}` : "Select an SCBI section";
    this.select.show();
    this.start.show();
  }

  private task(folder: vscode.WorkspaceFolder, section: Section | undefined,
               definition: ScbiTaskDefinition): vscode.Task {
    const exec = new vscode.ProcessExecution(this.command(), sectionArgs(definition.section, definition.args),
      { cwd: folder.uri.fsPath });
    const task = new vscode.Task(definition, folder, definition.section, TYPE, exec, []);
    task.detail = section ? describe(section) : undefined;
    if (section && !section.run) {
      task.group = vscode.TaskGroup.Build;
    }
    task.presentationOptions = { reveal: vscode.TaskRevealKind.Always, clear: true };
    return task;
  }

  private async provideTasks(): Promise<vscode.Task[]> {
    const tasks: vscode.Task[] = [];
    for (const folder of vscode.workspace.workspaceFolders ?? []) {
      for (const section of await this.sections(folder)) {
        tasks.push(this.task(folder, section, { type: TYPE, section: section.name }));
      }
    }
    return tasks;
  }

  /** A task of tasks.json ({"type": "scbi", "section": ..., "args": [...]}). */
  private resolveTask(task: vscode.Task): vscode.Task | undefined {
    const definition = task.definition as ScbiTaskDefinition;
    const folder = typeof task.scope === "object" ? task.scope : this.folder();
    if (!definition.section || !folder) {
      return undefined;
    }
    const section = this.known.get(folder.uri.toString())?.find((s) => s.name === definition.section);
    return this.task(folder, section, definition);
  }

  private async pick(): Promise<Section | undefined> {
    const folder = this.folder();
    if (!folder) {
      return undefined;
    }
    const found = await this.sections(folder);
    if (!found.length) {
      void vscode.window.showInformationMessage("SCBI: no section in the ini files (.scbi).");
      return undefined;
    }
    const choice = await vscode.window.showQuickPick(
      found.map((s) => ({ label: s.name, description: describe(s), detail: s.file, section: s })),
      { placeHolder: "SCBI section (scbi --ini=<section>)" });
    if (choice) {
      await this.context.workspaceState.update(STATE_KEY, choice.section.name);
      await this.refresh();
    }
    return choice?.section;
  }

  private async runSelected(): Promise<void> {
    const folder = this.folder();
    if (!folder) {
      return;
    }
    let section = (await this.sections(folder)).find((s) => s.name === this.selected());
    section ??= await this.pick();
    if (section) {
      await vscode.tasks.executeTask(this.task(folder, section, { type: TYPE, section: section.name }));
    }
  }

  private async shellProfile(): Promise<vscode.TerminalProfile> {
    const folder = this.folder();
    const section = folder ? (await this.sections(folder)).find((s) => s.name === this.selected()) : undefined;
    const args = shellArgs(section);
    this.output.appendLine(`SCBI shell: ${this.command()} ${args.join(" ")}`);
    return new vscode.TerminalProfile({
      name: section ? `SCBI ${section.name}` : "SCBI",
      shellPath: this.command(),
      shellArgs: args,
      cwd: folder?.uri,
    });
  }
}

function describe(section: Section): string {
  return section.run ? `run: ${section.run}` : `build: ${section.modules || "(no module)"}`;
}
