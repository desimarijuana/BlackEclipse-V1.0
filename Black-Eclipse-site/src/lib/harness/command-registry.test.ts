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

  it("exposes the whole catalog to the palette (more than an arbitrary cap)", () => {
    // Guards the composer palette: it must not cap the list so low that real
    // commands become unreachable.
    expect(allCommands().length).toBeGreaterThan(20);
    // A bare search returns every command (the palette filters by relevance).
    expect(searchCommands("").length).toBe(allCommands().length);
  });

  it("resolves commands by name, alias, and a leading slash", () => {
    expect(resolveCommand("skills")?.id).toBe("skills.list");
    expect(resolveCommand("/skill")?.id).toBe("skill.author");
    expect(resolveCommand("help")?.id).toBe("runtime.help");
    expect(resolveCommand("health")?.name).toBe("status");
    expect(resolveCommand("esdk")?.name).toBe("eclipsesdk");
    expect(resolveCommand("nope")).toBeUndefined();
  });

  it("exposes every registered command as runnable (all handler-backed)", () => {
    expect(allCommands().length).toBeGreaterThan(20);
    expect(allCommands().every((c) => isCommandAvailable(c))).toBe(true);
    // Every handler target is implemented (no unsupported placeholders).
    expect(allCommands().every((c) => c.handler.type !== "unsupported")).toBe(true);
  });

  it("wires the research/markets/quant/dev commands to real handlers", () => {
    expect(resolveCommand("quote")?.handler.target).toBe("markets.quote");
    expect(resolveCommand("research")?.handler.target).toBe("research.run");
    expect(resolveCommand("deep-research")?.handler.target).toBe("research.run");
    expect(resolveCommand("web")?.handler.target).toBe("research.web");
    expect(resolveCommand("read")?.handler.target).toBe("research.read");
    expect(resolveCommand("backtest")?.handler.target).toBe("quant.backtest");
    expect(resolveCommand("code")?.handler.target).toBe("code.task");
    expect(resolveCommand("terminal")?.handler.target).toBe("runtime.terminal");
    // `/run` is an alias of `/terminal`.
    expect(resolveCommand("run")?.name).toBe("terminal");
    expect(resolveCommand("sh")?.name).toBe("terminal");
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
    expect(commandArgHint(resolveCommand("skill")!)).toBe("[name] [description…] [--category <string>]");
  });

  it("exposes the profile command with a forced edit profile", () => {
    const spec = allCommands().find((c) => c.name === "eclipsesdk")!;
    expect(spec.handler.type).toBe("profile");
    expect(spec.profile).toEqual({ autonomy: "edit_verify", analysisEnabled: true });
  });

  it("marks /skill as an agent-turn command that authors a skill", () => {
    const spec = resolveCommand("skill")!;
    expect(spec.handler.type).toBe("agent");
    expect(spec.handler.target).toBe("agent.skill.author");
  });
});
