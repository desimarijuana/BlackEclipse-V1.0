import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  getPlanMode,
  nextPlanMode,
  planModeLabel,
  planModeTitle,
  setPlanMode,
  subscribePlanMode,
} from "./plan-mode";

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

describe("plan mode preference", () => {
  it("defaults to auto", () => {
    expect(getPlanMode()).toBe("auto");
  });

  it("persists and notifies subscribers", () => {
    const seen: string[] = [];
    const unsubscribe = subscribePlanMode((mode) => seen.push(mode));
    setPlanMode("on");
    expect(getPlanMode()).toBe("on");
    expect(seen).toEqual(["on"]);
    unsubscribe();
  });

  it("cycles auto -> on -> off -> auto", () => {
    expect(nextPlanMode("auto")).toBe("on");
    expect(nextPlanMode("on")).toBe("off");
    expect(nextPlanMode("off")).toBe("auto");
  });

  it("has a readable label for each state", () => {
    expect(planModeLabel("auto")).toBe("Plan auto");
    expect(planModeLabel("on")).toBe("Plan");
    expect(planModeLabel("off")).toBe("Plan off");
  });

  it("explains each state", () => {
    expect(planModeTitle("on")).toContain("waits for your approval");
    expect(planModeTitle("off")).toContain("without presenting a plan");
    expect(planModeTitle("auto")).toContain("complex enough");
  });
});
