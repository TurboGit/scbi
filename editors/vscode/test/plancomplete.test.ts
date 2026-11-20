// The completion in the build plans (src/plancomplete.ts).

import * as assert from "node:assert/strict";
import { test } from "node:test";
import { planCompletion, PlanData, planNames, planVariables, pluginNames } from "../src/plancomplete";

const DATA: PlanData = { plugins: ["c-gmp", "c-lcms2"], plans: ["base", "next"], variables: ["VER", "PV"] };

function labels(before: string): [number, string[]] {
  const r = planCompletion(before, DATA);
  return [r.start, r.items.map((i) => i.label)];
}

test("start of a line: directives, group, modules", () => {
  assert.deepEqual(labels(""), [0, ["@load", "@set", "@ref", "@on", "@for", "@alias", "[ group ]", "c-gmp", "c-lcms2"]]);
  assert.deepEqual(labels("  c-l")[0], 2);
  assert.deepEqual(labels("  @r"), [2, ["@load", "@set", "@ref", "@on", "@for", "@alias"]]);
});

test("directives: their arguments and keywords", () => {
  assert.deepEqual(labels("@load n"), [6, ["base", "next"]]);
  assert.deepEqual(labels("@ref "), [5, ["c-gmp", "c-lcms2"]]);
  assert.deepEqual(labels("@ref lib2 "), [10, ["as"]]);
  assert.deepEqual(labels("@ref lib2 as c-"), [13, ["c-gmp", "c-lcms2"]]);
  assert.deepEqual(labels("@ref lib2 as lib1 "), [18, ["version"]]);
  assert.deepEqual(labels("@on deb,9 "), [10, ["use"]]);
  assert.deepEqual(labels("@on deb,9 use c"), [14, ["c-gmp", "c-lcms2"]]);
  assert.deepEqual(labels("@for "), [5, ["c-gmp", "c-lcms2"]]);
  assert.deepEqual(labels("@alias p-gnat use "), [18, ["c-gmp", "c-lcms2"]]);
  assert.deepEqual(labels("@on de")[1], []);
  assert.deepEqual(labels("@set V = ")[1], []);
});

test("variants, versions, variables", () => {
  assert.deepEqual(labels("c-gmp/"), [6, ["native", "auto"]]);
  assert.deepEqual(labels("c-gmp/fast.a"), [11, ["native", "auto"]]);
  assert.deepEqual(labels("] /"), [3, ["native", "auto"]]);
  assert.deepEqual(labels("] /+a"), [4, ["native", "auto"]]);
  assert.deepEqual(labels("lib/variant-no")[0], 4);
  assert.deepEqual(labels("c-gmp/fast:d"), [11, ["dev", "keep", "skip", "force"]]);
  assert.deepEqual(labels("c-gmp:#"), [7, ["dev", "keep", "skip", "force"]]);
  assert.deepEqual(labels("@on deb use c-gmp:"), [18, ["dev", "keep", "skip", "force"]]);
  assert.deepEqual(labels("c-gmp:$V"), [6, ["$VER", "$PV"]]);
  assert.deepEqual(planCompletion("] :${", DATA).items.map((i) => i.insert), ["${VER}", "${PV}"]);
  assert.deepEqual(labels("mainlib=c-l"), [8, ["c-gmp", "c-lcms2"]]);
});

test("nothing in a comment nor a barrier", () => {
  assert.deepEqual(labels("# @r")[1], []);
  assert.deepEqual(labels("c-gmp:#1.2   # c")[1], []);
  assert.deepEqual(labels("[ = de")[1], []);
});

test("variables, plug-ins and plans of a directory", () => {
  assert.deepEqual(planVariables("@set VER = 1\n  @set  PV=2\n# @set NO = 3\n@set VER = 4\n"), ["VER", "PV"]);
  assert.deepEqual(pluginNames(["c-b.yaml", ".env.yaml", "c-a.yaml", "c-a", "x.yml"]), ["c-a", "c-b"]);
  assert.deepEqual(planNames([".plan-next", ".plan-base~", ".scbi-plan-local", ".plan-next", "plan-x"]),
    ["local", "next"]);
});
