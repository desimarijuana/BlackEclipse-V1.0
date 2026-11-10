import { describe, it, expect } from "vitest";

import { allCommands, resolveCommand, type CommandSpec } from "./command-registry";
import { buildCommandPalette } from "./command-palette-model";

const projectBrief: CommandSpec = {
  ...resolveCommand("skill")!,
  id: "project.brief",
  name: "brief",
  aliases: [],
  summary: "Morning brief",
  description: "Produce a morning brief.",
  handler: { type: "agent", target: "agent.plugin" },
  source: "project",
};

describe("command palette ordering", () => {
  it("puts pinned commands first, then recent, then the categories", () => {
    const model = buildCommandPalette("", ["quote", "status"], ["skills", "help"]);
    expect(model.sections.map((s) => s.key)).toEqual([
      "pinned",
      "recent",
      "cat:runtime",
      "cat:skills",
      "cat:research",
      "cat:markets",
      "cat:portfolio",
      "cat:quant",
      "cat:visual",
      "cat:web",
      "cat:dev",
      "cat:memory",
      "cat:admin",
    ]);
    expect(model.sections[0].commands.map((c) => c.name)).toEqual(["skills", "help"]);
    expect(model.sections[1].commands.map((c) => c.name)).toEqual(["quote", "status"]);
  });

  it("does not duplicate a pinned command in Recent or its category", () => {
    const model = buildCommandPalette("", ["quote", "quote"], ["quote"]);
    const names = model.flat.map((c) => c.name);
    expect(names.filter((name) => name === "quote")).toHaveLength(1);
    expect(model.sections[0].key).toBe("pinned");
    // The only recent entry was the pinned command, so no Recent section exists.
    expect(model.sections.some((section) => section.key === "recent")).toBe(false);
  });

  it("ignores unknown history and pin names", () => {
    const model = buildCommandPalette("", ["does-not-exist"], ["also-missing"]);
    expect(model.sections.every((s) => s.key !== "pinned" && s.key !== "recent")).toBe(true);
  });

  it("renders every command exactly once in the empty-query catalog", () => {
    const model = buildCommandPalette("", ["quote"], ["help"]);
    const names = model.flat.map((c) => c.name);
    expect(names).toHaveLength(allCommands().length);
    expect(new Set(names).size).toBe(names.length);
  });

  it("keeps search results in one flat section", () => {
    const model = buildCommandPalette("quo", ["status"], []);
    expect(model.sections).toHaveLength(1);
    expect(model.sections[0].key).toBe("results");
    expect(model.flat[0].name).toBe("quote");
  });

  it("merges project commands into search and the grouped catalog", () => {
    const searched = buildCommandPalette("brie", [], [], [projectBrief]);
    expect(searched.flat[0].name).toBe("brief");
    const all = buildCommandPalette("", [], [], [projectBrief]);
    expect(all.flat.some((command) => command.name === "brief")).toBe(true);
    expect(all.flat).toHaveLength(allCommands().length + 1);
  });

  it("orders the flat list exactly like the rendered sections", () => {
    const model = buildCommandPalette("", ["status"], ["help"]);
    const fromSections = model.sections.flatMap((s) => s.commands.map((c) => c.name));
    expect(model.flat.map((c) => c.name)).toEqual(fromSections);
    expect(resolveCommand(model.flat[0].name)).toBeTruthy();
  });
});
