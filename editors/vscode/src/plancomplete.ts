// Completion in the build plans: what can be written at the cursor, from
// the text of the line before it (independent of the VSCode API).

export type ItemKind = "directive" | "snippet" | "keyword" | "module" | "plan" | "variant" | "version" | "variable";

export interface PlanItem {
  label: string;
  kind: ItemKind;
  /** The text inserted (a snippet for kind "snippet" and the directives). */
  insert: string;
  detail?: string;
}

export interface PlanCompletion {
  /** The column where the replaced text starts (the word being typed). */
  start: number;
  items: PlanItem[];
}

/** What the completion offers, from the plug-ins and plans found and the
 * variables of the file. */
export interface PlanData {
  plugins: string[];
  plans: string[];
  variables: string[];
}

export const DIRECTIVES: PlanItem[] = [
  { label: "@load", kind: "directive", insert: "@load ${1:plan}", detail: "load another build plan as the base" },
  { label: "@set", kind: "directive", insert: "@set ${1:NAME} = ${2:value}", detail: "set a variable ($NAME)" },
  { label: "@ref", kind: "directive", insert: "@ref ${1:module} as ${2:module}",
    detail: "the variant and version of another module" },
  { label: "@on", kind: "directive", insert: "@on ${1:discriminants} use ${2:module}",
    detail: "a module reference on some OS only" },
  { label: "@for", kind: "directive", insert: "@for ${1:plug-in} use ${2:module}",
    detail: "a module reference when a dependency of a plug-in" },
  { label: "@alias", kind: "directive", insert: "@alias ${1:plug-in} use ${2:plug-in}",
    detail: "a plug-in used when another one is not found" },
];

const GROUP: PlanItem = {
  label: "[ group ]", kind: "snippet", insert: "[ ${1:= barrier}\n\t$0\n] /${2:variant}:${3:version}",
  detail: "modules sharing a variant and a version",
};

const VARIANTS: PlanItem[] = [
  { label: "native", kind: "variant", insert: "native", detail: "the packages of the distribution" },
  { label: "auto", kind: "variant", insert: "auto", detail: "native when its packages are available" },
];

const VERSIONS: PlanItem[] = [
  { label: "dev", kind: "version", insert: "dev", detail: "the sources of the user's checkout" },
  { label: "keep", kind: "version", insert: "keep", detail: "not rebuilt, kept as built last time" },
  { label: "skip", kind: "version", insert: "skip", detail: "ignored, as if not a dependency" },
  { label: "force", kind: "version", insert: "force", detail: "enabled even if skipped elsewhere" },
];

function keyword(word: string, detail: string): PlanItem {
  return { label: word, kind: "keyword", insert: word, detail };
}

function modules(data: PlanData): PlanItem[] {
  return data.plugins.map((p) => ({ label: p, kind: "module", insert: p }));
}

/** The completion at the end of `before` (the line up to the cursor). */
export function planCompletion(before: string, data: PlanData): PlanCompletion {
  const none = { start: before.length, items: [] };
  //  in a comment
  if (/(^|\s)#/.test(before.replace(/:#/g, ":"))) {
    return none;
  }
  //  a variable: $NAME or ${NAME
  let m = /\$\{?(\w*)$/.exec(before);
  if (m) {
    const brace = m[0].startsWith("${");
    return {
      start: m.index,
      items: data.variables.map((v) => ({ label: `$${v}`, kind: "variable", insert: brace ? `\${${v}}` : `$${v}` })),
    };
  }
  //  the word being typed (no blank, no / nor :)
  const word = /[^\s/:=]*$/.exec(before)![0];
  const start = before.length - word.length;
  const token = /\S*$/.exec(before)![0];
  const line = before.trimStart();

  //  a version or a variant of a module reference or of a group
  if (token.includes(":")) {
    return { start: start + (word.startsWith("#") ? 1 : 0), items: VERSIONS };
  }
  if (token.includes("/") && !line.startsWith("@ref") || /^\]\s*\/\S*$/.test(line)) {
    //  the variant after the last . of a multi-variant (fast.mpi), or a +/-
    const v = /[/.][+-]?([^\s/:=.]*)$/.exec(before);
    return { start: before.length - (v ? v[1].length : 0), items: VARIANTS };
  }
  if (line.startsWith("[")) {
    return none; // a barrier: variants of the plan, discriminants
  }
  //  directives
  if ((m = /^@load\s+(\S*)$/.exec(line))) {
    return { start, items: data.plans.map((p) => ({ label: p, kind: "plan", insert: p })) };
  }
  if (/^@set\s/.test(line)) {
    return none;
  }
  if (/^@ref\s+\S+\s+$/.test(line)) {
    return { start, items: [keyword("as", "the module giving the variant and version")] };
  }
  if (/^@ref\s+\S+\s+as\s+\S+\s+$/.test(line)) {
    return { start, items: [keyword("version", "a pattern computing the version: prefix/regex/suffix")] };
  }
  if (/^@ref\s+\S*$/.test(line) || /^@ref\s+\S+\s+as\s+\S*$/.test(line)) {
    return { start, items: modules(data) };
  }
  if (/^@(on|for|alias)\s+\S+\s+$/.test(line)) {
    return { start, items: [keyword("use", "the module reference used")] };
  }
  if (/^@(for|alias)\s+\S*$/.test(line) || /^@(on|for|alias)\s+\S+\s+use\s+\S*$/.test(line)) {
    return { start, items: modules(data) };
  }
  if (/^@on\s+\S*$/.test(line)) {
    return none; // discriminants
  }
  //  the start of a line: a directive, a group or a module reference
  if (/^@?[\w.+-]*$/.test(line)) {
    const directives = line.startsWith("@") ? DIRECTIVES : [...DIRECTIVES, GROUP, ...modules(data)];
    return { start: before.length - line.length, items: directives };
  }
  //  for_module=name
  if (/^[\w.+-]+=[\w.+-]*$/.test(line)) {
    return { start, items: modules(data) };
  }
  return none;
}

/** The variables set in a build plan (@set NAME = ...). */
export function planVariables(text: string): string[] {
  const names = new Set<string>();
  for (const m of text.matchAll(/^\s*@set\s+([A-Za-z_]\w*)/gm)) {
    names.add(m[1]);
  }
  return [...names];
}

/** The plug-in names of the file names of a directory (<name>.yaml). */
export function pluginNames(files: string[]): string[] {
  return files.filter((f) => f.endsWith(".yaml") && !f.startsWith(".")).map((f) => f.slice(0, -5)).sort();
}

/** The plan names of the file names of a directory (.plan-<name>,
 * .scbi-plan-<name>; not the backups). */
export function planNames(files: string[]): string[] {
  const names = new Set<string>();
  for (const f of files) {
    const m = /^\.(?:scbi-)?plan-(.+)$/.exec(f);
    if (m && !m[1].endsWith("~")) {
      names.add(m[1]);
    }
  }
  return [...names].sort();
}
