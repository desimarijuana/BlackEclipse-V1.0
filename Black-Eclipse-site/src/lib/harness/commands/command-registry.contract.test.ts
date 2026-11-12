import { describe, it, expect } from "vitest";

import { allCommands, type CommandHandlerType } from "./command-registry";
import { handlers } from "./command-handlers";

// Handlers that run as a normal agent turn (or switch the run profile) do not
// dispatch through the handler table; every other handler type MUST.
const NON_DISPATCHED: ReadonlySet<CommandHandlerType> = new Set(["agent", "profile"]);

// Completion providers the client knows how to resolve. Adding a provider means
// adding it here and to the palette's resolver.
const COMPLETION_PROVIDERS = new Set([
  "skills",
  "symbols",
  "portfolios",
  "workflows",
  "models",
]);

describe("command registry contract", () => {
  it("has unique stable ids", () => {
    const ids = allCommands().map((c) => c.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("every routed handler target is implemented", () => {
    const missing = allCommands()
      .filter((c) => !NON_DISPATCHED.has(c.handler.type))
      .filter((c) => !(c.handler.target in handlers))
      .map((c) => `${c.id} -> ${c.handler.target}`);
    expect(missing).toEqual([]);
  });

  it("every available command is runnable and self-describing", () => {
    for (const c of allCommands()) {
      expect(c.summary.trim(), `${c.id} summary`).not.toBe("");
      expect(c.description.trim(), `${c.id} description`).not.toBe("");
      expect(c.examples.length, `${c.id} examples`).toBeGreaterThan(0);
      expect(c.output.summary.trim(), `${c.id} output summary`).not.toBe("");
      expect(c.version, `${c.id} version`).toMatch(/^\d+\.\d+\.\d+$/);
      if (c.status === "available") {
        expect(c.handler.type, `${c.id} handler type`).not.toBe("unsupported");
        expect(c.unavailabilityReason, `${c.id} unavailable reason`).toBeUndefined();
      }
    }
  });

  it("high and critical risk commands declare an operator gate", () => {
    const unsafe = allCommands()
      .filter((c) => c.risk === "high" || c.risk === "critical")
      .filter((c) => c.permissions.approval !== "operator")
      .map((c) => c.id);
    expect(unsafe).toEqual([]);
  });

  it("high and critical risk commands declare the confirm flag", () => {
    const missing = allCommands()
      .filter((c) => c.risk === "high" || c.risk === "critical")
      .filter((c) => !c.flags.some((flag) => flag.name === "confirm"))
      .map((c) => c.id);
    expect(missing).toEqual([]);
  });

  it("only uses known completion providers", () => {
    const unknown = allCommands()
      .flatMap((c) => c.args.map((a) => ({ command: c.id, provider: a.completion })))
      .filter((a) => a.provider && !COMPLETION_PROVIDERS.has(a.provider))
      .map((a) => `${a.command} -> ${a.provider}`);
    expect(unknown).toEqual([]);
  });

  it("keeps deprecation and unavailability metadata coherent", () => {
    for (const c of allCommands()) {
      if (c.status === "deprecated") expect(c.deprecation, `${c.id} deprecation`).toBeTruthy();
      if (c.deprecation) {
        expect(c.deprecation.since, `${c.id} since`).not.toBe("");
        expect(c.deprecation.note, `${c.id} note`).not.toBe("");
      }
      if (c.status === "unavailable") {
        expect(c.unavailabilityReason, `${c.id} reason`).toBeTruthy();
      }
    }
  });

  it("gives /help a topic argument so command detail is reachable", () => {
    const help = allCommands().find((c) => c.id === "runtime.help")!;
    expect(help.args.map((a) => a.name)).toContain("command");
    expect(help.examples.some((e) => e.startsWith("/help "))).toBe(true);
  });
});
