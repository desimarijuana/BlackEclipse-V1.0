import { describe, it, expect } from "vitest";

import {
  COMMAND_REGISTRY,
  allCommands,
  commandArgHint,
  detectRegistryConflicts,
  isCommandAvailable,
  listCommands,
  resolveCommand,
  searchCommands,
} from "./command-registry";

describe("command registry", () => {
  it("has unique ids and no name/alias conflicts", () => {
    const ids = COMMAND_REGISTRY.map((c) => c.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(detectRegistryConflicts()).toEqual([]);
  });

  it("resolves commands by name, alias, and a leading slash", () => {
    expect(resolveCommand("skills")?.id).toBe("skills.list");
    expect(resolveCommand("/skill")?.id).toBe("skill.execute");
    expect(resolveCommand("help")?.id).toBe("runtime.help");
    expect(resolveCommand("health")?.name).toBe("status");
    expect(resolveCommand("esdk")?.name).toBe("eclipsesdk");
    expect(resolveCommand("nope")).toBeUndefined();
  });

  it("marks only handler-backed commands as available", () => {
    expect(isCommandAvailable(resolveCommand("skills")!)).toBe(true);
    expect(isCommandAvailable(resolveCommand("skill")!)).toBe(true);
    expect(isCommandAvailable(resolveCommand("help")!)).toBe(true);
    const backtest = resolveCommand("backtest")!;
    expect(backtest.status).toBe("unavailable");
    expect(isCommandAvailable(backtest)).toBe(false);
    expect(backtest.unavailabilityReason).toBeTruthy();
    // Newly wired commands are available.
    expect(isCommandAvailable(resolveCommand("market")!)).toBe(true);
    expect(isCommandAvailable(resolveCommand("portfolio")!)).toBe(true);
    expect(isCommandAvailable(resolveCommand("usage")!)).toBe(true);
  });

  it("searches by prefix, substring, tag, and fuzzy subsequence", () => {
    expect(searchCommands("rese")[0].name).toBe("research");
    expect(searchCommands("back")[0].name).toBe("backtest");
    expect(searchCommands("skill").map((c) => c.name)).toContain("skills");
    expect(searchCommands("skill").map((c) => c.name)).toContain("skill");
    // Fuzzy: "hp" is a subsequence of "help".
    expect(searchCommands("hp").some((c) => c.name === "help")).toBe(true);
    // Deterministic ordering for the same query.
    expect(searchCommands("skill").map((c) => c.name)).toEqual(searchCommands("skill").map((c) => c.name));
  });

  it("lists by category and status", () => {
    const skills = listCommands({ category: "skills" });
    expect(skills.length).toBeGreaterThanOrEqual(7);
    expect(skills.every((c) => c.category === "skills")).toBe(true);
    expect(listCommands({ status: "unavailable" }).every((c) => c.status === "unavailable")).toBe(true);
  });

  it("sorts a bare search alphabetically", () => {
    const names = searchCommands("").map((c) => c.name);
    expect(names).toEqual([...names].sort((a, b) => a.localeCompare(b)));
  });

  it("builds an argument hint from the schema", () => {
    expect(commandArgHint(resolveCommand("skills")!)).toBe("[action] [subject…] [--status <string>]");
    expect(commandArgHint(resolveCommand("skill")!)).toContain("<skillId>");
    expect(commandArgHint(resolveCommand("skill")!)).toContain("[--<key> <value>]…");
  });

  it("exposes the profile command with a forced edit profile", () => {
    const spec = allCommands().find((c) => c.name === "eclipsesdk")!;
    expect(spec.handler.type).toBe("profile");
    expect(spec.profile).toEqual({ autonomy: "edit_verify", analysisEnabled: true });
  });
});
