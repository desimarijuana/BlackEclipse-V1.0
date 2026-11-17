import { describe, it, expect } from "vitest";

import {
  bindArgs,
  parseAndBind,
  parseCommandInvocation,
  tokenizeArgs,
} from "./command-parser";
import { resolveCommand, type CommandSpec } from "./command-registry";

describe("tokenizeArgs", () => {
  it("splits on whitespace and preserves quoted strings", () => {
    const { tokens, errors } = tokenizeArgs(`"NVIDIA competitive position" --depth deep`);
    expect(tokens).toEqual(["NVIDIA competitive position", "--depth", "deep"]);
    expect(errors).toEqual([]);
  });

  it("preserves single-quoted and empty-quoted tokens", () => {
    expect(tokenizeArgs(`'a b' "" c`).tokens).toEqual(["a b", "", "c"]);
  });

  it("supports backslash escapes", () => {
    expect(tokenizeArgs(`a\\ b c`).tokens).toEqual(["a b", "c"]);
    expect(tokenizeArgs(`"say \\"hi\\""`).tokens).toEqual(['say "hi"']);
  });

  it("preserves Unicode and filenames with spaces", () => {
    expect(tokenizeArgs(`"my report — Q3.csv" café`).tokens).toEqual(["my report — Q3.csv", "café"]);
  });

  it("reports an unterminated quote", () => {
    const { errors } = tokenizeArgs(`"open`);
    expect(errors[0].code).toBe("UNTERMINATED_QUOTE");
  });
});

describe("parseCommandInvocation", () => {
  it("returns null for ordinary text", () => {
    expect(parseCommandInvocation("build me a page")).toBeNull();
    expect(parseCommandInvocation("")).toBeNull();
    expect(parseCommandInvocation(null)).toBeNull();
  });

  it("does not treat an absolute path as a command", () => {
    expect(parseCommandInvocation("/usr/bin/python")).toBeNull();
  });

  it("resolves a known command and keeps the rest", () => {
    const inv = parseCommandInvocation("/skills search crypto")!;
    expect(inv.spec?.id).toBe("skills.list");
    expect(inv.name).toBe("skills");
    expect(inv.rest).toBe("search crypto");
    expect(inv.unknown).toBe(false);
  });

  it("flags an unknown command token", () => {
    const inv = parseCommandInvocation("/frobnicate now")!;
    expect(inv.spec).toBeNull();
    expect(inv.unknown).toBe(true);
    expect(inv.name).toBe("frobnicate");
  });
});

describe("bindArgs", () => {
  const skills = resolveCommand("skills")!;
  const skillTest = resolveCommand("skill-test")!;
  const skillExplain = resolveCommand("skill-explain")!;
  // A synthetic spec exercising pass-through flags independently of the
  // shipped `skills` command (which now enables pass-through for `run` inputs).
  const passthrough = {
    ...skills,
    id: "test.passthrough",
    name: "passthrough",
    aliases: [],
    args: [{ name: "target", description: "Target.", required: true }],
    flags: [],
    passThroughFlags: true,
  } as CommandSpec;

  it("maps positionals onto declared args with a default", () => {
    const bound = bindArgs(skills, tokenizeArgs(""));
    expect(bound.positionals.action).toBe("list");
    expect(bound.positionals.subject).toEqual([]);
    expect(bound.errors).toEqual([]);
  });

  it("captures a variadic subject and validates the enum", () => {
    const bound = bindArgs(skills, tokenizeArgs("search on-chain activity"));
    expect(bound.positionals.action).toBe("search");
    expect(bound.positionals.subject).toEqual(["on-chain", "activity"]);
    expect(bound.errors).toEqual([]);
  });

  it("rejects an invalid enum value", () => {
    const bound = bindArgs(skills, tokenizeArgs("bogus subj"));
    expect(bound.errors.some((e) => e.code === "INVALID_ENUM")).toBe(true);
  });

  it("reports a missing required argument", () => {
    const bound = bindArgs(skillExplain, tokenizeArgs(""));
    expect(bound.errors.some((e) => e.code === "MISSING_ARG" && e.arg === "skillId")).toBe(true);
  });

  it("passes unknown --key value flags through as skill input", () => {
    const bound = bindArgs(passthrough, tokenizeArgs("crypto-onchain-research --asset BTC --period 90d"));
    expect(bound.positionals.target).toBe("crypto-onchain-research");
    expect(bound.input).toEqual({ asset: "BTC", period: "90d" });
    expect(bound.errors).toEqual([]);
  });

  it("parses --key=value and recognized boolean flags", () => {
    const bound = bindArgs(resolveCommand("skill")!, tokenizeArgs("x --category=finance"));
    expect(bound.flags.category).toBe("finance");
    expect(bindArgs(skillTest, tokenizeArgs("x --regression")).flags.regression).toBe(true);
  });

  it("rejects an unknown flag when pass-through is off", () => {
    const bound = bindArgs(resolveCommand("skill")!, tokenizeArgs("x --nope"));
    expect(bound.errors.some((e) => e.code === "UNKNOWN_FLAG")).toBe(true);
  });

  it("accumulates a repeatable valued flag instead of keeping only the last", () => {
    const goal = resolveCommand("goal")!;
    const bound = bindArgs(goal, tokenizeArgs("ship it --gate typecheck --gate unit_test=src/a.test.ts"));
    expect(bound.flags.gate).toEqual(["typecheck", "unit_test=src/a.test.ts"]);
    expect(bound.errors).toEqual([]);
    // A non-repeatable flag keeps the last value, as before.
    const one = bindArgs(goal, tokenizeArgs("ship it --workspace a --workspace b"));
    expect(one.flags.workspace).toBe("b");
  });
});

describe("parseAndBind", () => {
  it("returns null for prose and a bound result for a command", () => {
    expect(parseAndBind("hello there")).toBeNull();
    const parsed = parseAndBind("/status")!;
    expect(parsed.invocation.spec?.name).toBe("status");
    expect(parsed.args.errors).toEqual([]);
  });
});
