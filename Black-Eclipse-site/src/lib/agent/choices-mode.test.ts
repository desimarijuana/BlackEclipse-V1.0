import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  choicesModeLabel,
  choicesModeTitle,
  getChoicesMode,
  nextChoicesMode,
  setChoicesMode,
  subscribeChoicesMode,
} from "./choices-mode";

// The store is deliberately window-only (it is read by the client chat path), so
// the test provides the smallest real EventTarget-shaped window it uses.
let store: Map<string, string>;
let listeners: Map<string, Set<(event: { type: string; detail?: unknown }) => void>>;

beforeEach(() => {
  store = new Map();
  listeners = new Map();
  vi.stubGlobal("window", {
    localStorage: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => store.set(key, value),
      removeItem: (key: string) => store.delete(key),
    },
    addEventListener: (type: string, fn: (event: { type: string; detail?: unknown }) => void) => {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type)!.add(fn);
    },
    removeEventListener: (type: string, fn: (event: { type: string; detail?: unknown }) => void) => {
      listeners.get(type)?.delete(fn);
    },
    dispatchEvent: (event: { type: string; detail?: unknown }) => {
      listeners.get(event.type)?.forEach((fn) => fn(event));
      return true;
    },
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("choices mode preference", () => {
  it("defaults to auto", () => {
    expect(getChoicesMode()).toBe("auto");
  });

  it("persists and notifies subscribers", () => {
    const seen: string[] = [];
    const unsubscribe = subscribeChoicesMode((mode) => seen.push(mode));
    setChoicesMode("on");
    expect(getChoicesMode()).toBe("on");
    expect(seen).toEqual(["on"]);
    unsubscribe();
  });

  it("cycles auto -> on -> off -> auto", () => {
    expect(nextChoicesMode("auto")).toBe("on");
    expect(nextChoicesMode("on")).toBe("off");
    expect(nextChoicesMode("off")).toBe("auto");
  });

  it("has a readable label for each state", () => {
    expect(choicesModeLabel("auto")).toBe("Choices auto");
    expect(choicesModeLabel("on")).toBe("Choices");
    expect(choicesModeLabel("off")).toBe("Choices off");
  });

  it("explains each state", () => {
    expect(choicesModeTitle("on")).toContain("clickable options");
    expect(choicesModeTitle("off")).toContain("best interpretation");
    expect(choicesModeTitle("auto")).toContain("genuinely");
  });
});
