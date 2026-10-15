import { describe, it, expect } from "vitest";

import {
  CHAT_COMMANDS,
  COMMAND_EMPTY_INSTRUCTION,
  ECLIPSESDK_COMMAND,
  findChatCommand,
  parseChatCommand,
} from "./commands";

describe("parseChatCommand", () => {
  it("parses /eclipsesdk with an instruction (case-insensitive)", () => {
    const parsed = parseChatCommand("/ECLIPSESDK create a page for my watchlist");
    expect(parsed?.command.name).toBe("eclipsesdk");
    expect(parsed?.instruction).toBe("create a page for my watchlist");
    expect(parsed?.query).toBe("create a page for my watchlist");
  });

  it("accepts the /esdk alias", () => {
    expect(parseChatCommand("/esdk add a tool")?.command.name).toBe("eclipsesdk");
  });

  it("defaults the query when the command carries no instruction", () => {
    const parsed = parseChatCommand("/eclipsesdk");
    expect(parsed?.command.name).toBe("eclipsesdk");
    expect(parsed?.instruction).toBe("");
    expect(parsed?.query).toBe(COMMAND_EMPTY_INSTRUCTION);
  });

  it("tolerates leading whitespace and collapses the boundary", () => {
    const parsed = parseChatCommand("   /eclipsesdk    fix the bug  ");
    expect(parsed?.instruction).toBe("fix the bug");
  });

  it("returns null for ordinary text", () => {
    expect(parseChatCommand("build me a page")).toBeNull();
  });

  it("returns null for an unknown command", () => {
    expect(parseChatCommand("/foo do something")).toBeNull();
  });

  it("does not treat an absolute path as a command", () => {
    expect(parseChatCommand("/usr/bin/python")).toBeNull();
  });

  it("returns null for null/undefined/empty", () => {
    expect(parseChatCommand(null)).toBeNull();
    expect(parseChatCommand(undefined)).toBeNull();
    expect(parseChatCommand("")).toBeNull();
  });
});

describe("command registry", () => {
  it("exposes /eclipsesdk first with a write profile", () => {
    expect(CHAT_COMMANDS[0]).toBe(ECLIPSESDK_COMMAND);
    expect(ECLIPSESDK_COMMAND.profile.autonomy).toBe("edit_verify");
    expect(ECLIPSESDK_COMMAND.profile.analysisEnabled).toBe(true);
  });

  it("finds a command by name or alias (with or without a slash)", () => {
    expect(findChatCommand("eclipsesdk")?.name).toBe("eclipsesdk");
    expect(findChatCommand("/ECLIPSESDK")?.name).toBe("eclipsesdk");
    expect(findChatCommand("esdk")?.name).toBe("eclipsesdk");
    expect(findChatCommand("nope")).toBeUndefined();
  });
});
