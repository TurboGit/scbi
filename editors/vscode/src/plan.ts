// The build plans (.plan-<name>, .scbi-plan-<name>): the completion (the
// highlighting is the grammar syntaxes/scbi-plan.tmLanguage.json).

import { readdirSync } from "node:fs";
import { homedir } from "node:os";
import * as path from "node:path";
import * as vscode from "vscode";
import { ItemKind, planCompletion, PlanData, planNames, planVariables, pluginNames } from "./plancomplete";

function list(dir: string): string[] {
  try {
    return readdirSync(dir);
  } catch {
    return [];
  }
}

/** The directory of the plug-ins: the one of the plan when it has
 * plug-ins (a plan beside its plug-ins), else $SCBI_PLUGINS, else the
 * default one. */
export function pluginsDir(planFile: string): string {
  const here = path.dirname(planFile);
  if (pluginNames(list(here)).length) {
    return here;
  }
  return process.env.SCBI_PLUGINS || path.join(homedir(), ".config", "scbi");
}

function data(doc: vscode.TextDocument): PlanData {
  const plugins = pluginsDir(doc.uri.fsPath);
  const here = path.dirname(doc.uri.fsPath);
  return {
    plugins: pluginNames(list(plugins)),
    plans: [...new Set([...planNames(list(plugins)), ...planNames(list(here))])].sort(),
    variables: planVariables(doc.getText()),
  };
}

const KINDS: Record<ItemKind, vscode.CompletionItemKind> = {
  directive: vscode.CompletionItemKind.Keyword,
  snippet: vscode.CompletionItemKind.Snippet,
  keyword: vscode.CompletionItemKind.Keyword,
  module: vscode.CompletionItemKind.Module,
  plan: vscode.CompletionItemKind.File,
  variant: vscode.CompletionItemKind.EnumMember,
  version: vscode.CompletionItemKind.Constant,
  variable: vscode.CompletionItemKind.Variable,
};

export function registerPlans(context: vscode.ExtensionContext): void {
  context.subscriptions.push(vscode.languages.registerCompletionItemProvider(
    { language: "scbi-plan" },
    {
      provideCompletionItems(doc, position) {
        const before = doc.lineAt(position.line).text.slice(0, position.character);
        const result = planCompletion(before, data(doc));
        const range = new vscode.Range(position.line, result.start, position.line, position.character);
        return result.items.map((it) => {
          const item = new vscode.CompletionItem(it.label, KINDS[it.kind]);
          item.insertText = it.kind === "directive" || it.kind === "snippet"
            ? new vscode.SnippetString(it.insert) : it.insert;
          item.filterText = it.kind === "snippet" ? "[" : it.insert.replace(/\$\{\d+:[^}]*\}|\$\d/g, "");
          item.range = range;
          item.detail = it.detail;
          return item;
        });
      },
    },
    "@", "/", ":", "$", "{", " ", "=",
  ));
}
