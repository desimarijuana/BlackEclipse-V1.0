import { describe, it, expect } from "vitest";

import { buildAgentInstruction } from "./command-agent";

describe("buildAgentInstruction", () => {
  it("rewrites /skill into a skill-authoring directive", () => {
    const cmd = buildAgentInstruction("/skill crypto-onchain-research Research tokenomics for a token")!;
    expect(cmd.command).toBe("skill");
    expect(cmd.instruction).toContain("crypto-onchain-research");
    expect(cmd.instruction).toContain("Research tokenomics for a token");
    expect(cmd.instruction).toContain("skill_create");
    expect(cmd.instruction).toContain("Skills page");
  });

  it("asks for details when only a name is given", () => {
    const cmd = buildAgentInstruction("/skill my-skill")!;
    expect(cmd.command).toBe("skill");
    expect(cmd.instruction).toMatch(/ask the\s+user|not given/i);
  });

  it("passes the category flag through", () => {
    const cmd = buildAgentInstruction("/skill r-review Review risk --category finance")!;
    expect(cmd.instruction).toContain("finance");
  });

  it("returns null for non-agent commands and ordinary text", () => {
    expect(buildAgentInstruction("/skills run foo")).toBeNull();
    expect(buildAgentInstruction("/eclipsesdk build a page")).toBeNull();
    expect(buildAgentInstruction("hello there")).toBeNull();
    expect(buildAgentInstruction(null)).toBeNull();
  });
});
