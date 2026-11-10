import { describe, it, expect } from "vitest";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { loadProjectCommands, parseProjectCommandPack } from "./command-plugins";

const validPack = {
  version: 1,
  commands: [
    {
      name: "morning-brief",
      aliases: ["brief"],
      summary: "Produce my morning market brief.",
      description: "Summarize overnight moves, my watchlist and the day's calendar.",
      category: "research",
      tags: ["brief", "markets"],
      args: [{ name: "focus", description: "Optional focus.", variadic: true }],
      flags: [{ name: "short", description: "Keep it short.", type: "boolean", alias: "s" }],
      examples: ["/morning-brief rates"],
      prompt: "Produce my morning brief. Focus: {{focus}}. Short: {{flag.short}}.",
    },
  ],
};

describe("project command packs", () => {
  it("loads a valid agent-turn command", () => {
    const { commands, errors } = parseProjectCommandPack(validPack);
    expect(errors).toEqual([]);
    expect(commands).toHaveLength(1);
    expect(commands[0]).toMatchObject({
      id: "project.morning-brief",
      name: "morning-brief",
      aliases: ["brief"],
      category: "research",
      source: "project",
      handler: { type: "agent", target: "agent.plugin" },
    });
    expect(commands[0].agentPrompt).toContain("{{focus}}");
  });

  it("refuses a name or alias that collides with a builtin", () => {
    const { commands, errors } = parseProjectCommandPack({
      commands: [
        { ...validPack.commands[0], name: "status", aliases: [] },
        { ...validPack.commands[0], name: "my-brief", aliases: ["help"] },
      ],
    });
    // The colliding name is refused; the second command loads with the
    // colliding alias dropped and the error reported.
    expect(commands).toHaveLength(1);
    expect(commands[0].name).toBe("my-brief");
    expect(commands[0].aliases).toEqual([]);
    expect(errors.join("\n")).toContain("collides");
  });

  it("rejects invalid names, missing prompts and bad args", () => {
    const { commands, errors } = parseProjectCommandPack({
      commands: [
        { ...validPack.commands[0], name: "Bad Name" },
        { ...validPack.commands[0], name: "no-prompt", prompt: "" },
        { ...validPack.commands[0], name: "bad-arg", args: [{ name: "BAD", description: "x" }] },
      ],
    });
    expect(commands).toHaveLength(1); // bad-arg still loads with the arg dropped
    expect(commands[0].name).toBe("bad-arg");
    expect(errors.join("\n")).toContain("name must match");
    expect(errors.join("\n")).toContain("summary, description and prompt are required");
    expect(errors.join("\n")).toContain("args[0].name is invalid");
  });

  it("rejects a non-array commands field", () => {
    expect(parseProjectCommandPack({ commands: {} })).toEqual({
      commands: [],
      errors: ["commands.json must have a commands[] array"],
    });
  });

  it("treats a missing file as an empty pack and invalid JSON as an error", async () => {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), "be-command-pack-"));
    try {
      expect(await loadProjectCommands(root)).toEqual({ commands: [], errors: [] });
      await fs.mkdir(path.join(root, ".black-eclipse"), { recursive: true });
      await fs.writeFile(path.join(root, ".black-eclipse", "commands.json"), "{nope", "utf8");
      const invalid = await loadProjectCommands(root);
      expect(invalid.commands).toEqual([]);
      expect(invalid.errors[0]).toContain("not valid JSON");
    } finally {
      await fs.rm(root, { recursive: true, force: true });
    }
  });
});
