import { beforeEach, describe, it, expect } from "vitest";

import {
  clearCommandHistory,
  getCommandFavorites,
  getCommandHistory,
  recentCommandNames,
  recordCommandRun,
  resetCommandMemoryForTests,
  toggleCommandFavorite,
} from "./command-history";

describe("command history store", () => {
  beforeEach(() => {
    resetCommandMemoryForTests();
  });

  it("records commands newest-first and de-duplicates", () => {
    recordCommandRun("quote");
    recordCommandRun("/status");
    recordCommandRun("QUOTE");

    expect(getCommandHistory().map((entry) => entry.name)).toEqual(["quote", "status"]);
    expect(recentCommandNames(1)).toEqual(["quote"]);
  });

  it("caps the history at 50 unique commands", () => {
    for (let i = 0; i < 60; i += 1) recordCommandRun(`cmd-${i}`);
    expect(getCommandHistory()).toHaveLength(50);
    expect(getCommandHistory()[0].name).toBe("cmd-59");
  });

  it("pins and unpins a command", () => {
    toggleCommandFavorite("skills");
    toggleCommandFavorite("/help");
    expect(getCommandFavorites()).toEqual(["skills", "help"]);

    toggleCommandFavorite("skills");
    expect(getCommandFavorites()).toEqual(["help"]);
  });

  it("clears recent commands but keeps pins", () => {
    recordCommandRun("quote");
    toggleCommandFavorite("quote");
    clearCommandHistory();
    expect(getCommandHistory()).toEqual([]);
    expect(getCommandFavorites()).toEqual(["quote"]);
  });

  it("ignores empty names", () => {
    recordCommandRun("   ");
    recordCommandRun("/");
    expect(getCommandHistory()).toEqual([]);
  });
});
