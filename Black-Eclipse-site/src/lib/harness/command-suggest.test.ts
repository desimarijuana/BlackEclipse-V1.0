import { describe, it, expect } from "vitest";

import { parseCommandCompletion } from "./command-suggest";

describe("command argument completion", () => {
  it("detects a skill id argument", () => {
    const context = parseCommandCompletion("/skill-explain cry");
    expect(context?.provider).toBe("skills");
    expect(context?.prefix).toBe("cry");
    expect(context?.arg.name).toBe("skillId");
  });

  it("offers the top candidates right after the command and space", () => {
    const context = parseCommandCompletion("/skill-explain ");
    expect(context?.provider).toBe("skills");
    expect(context?.prefix).toBe("");
    expect(context?.replaceStart).toBe("/skill-explain ".length);
  });

  it("replaces only the current symbol token for a variadic argument", () => {
    const context = parseCommandCompletion("/quote AAPL BT");
    expect(context?.provider).toBe("symbols");
    expect(context?.prefix).toBe("BT");
    expect(context?.replaceStart).toBe("/quote AAPL ".length);
  });

  it("does not suggest once a non-variadic argument is complete", () => {
    expect(parseCommandCompletion("/skill-explain a b")).toBeNull();
  });

  it("ignores flags and commands without a completion provider", () => {
    expect(parseCommandCompletion("/terminal --shell cmd dir")).toBeNull();
    expect(parseCommandCompletion("/help")).toBeNull();
    expect(parseCommandCompletion("/skills search crypto")).toBeNull();
  });

  it("ignores prose and a bare command word", () => {
    expect(parseCommandCompletion("quote AAPL")).toBeNull();
    expect(parseCommandCompletion("/quote")).toBeNull();
  });
});
