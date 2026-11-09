import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  prefs: {} as Record<string, boolean>,
  calls: 0,
}));

vi.mock("@/lib/setup/state", () => ({
  effectiveSourcePreferences: async () => {
    state.calls++;
    return state.prefs;
  },
}));

import {
  getSourcePreferenceMap,
  invalidateSourcePreferenceCache,
  isDataSourceEnabled,
} from "./data-source-preferences";

describe("data-source preference enforcement", () => {
  beforeEach(() => {
    invalidateSourcePreferenceCache();
    state.prefs = {};
    state.calls = 0;
  });

  it("keeps legacy behavior when a source has no explicit preference", async () => {
    await expect(isDataSourceEnabled("tradingview")).resolves.toBe(true);
  });

  it("honors an explicit off", async () => {
    state.prefs = { tradingview: false };
    await expect(isDataSourceEnabled("tradingview")).resolves.toBe(false);
  });

  it("caches for the TTL and invalidates on demand", async () => {
    state.prefs = { gdelt: false };
    await expect(isDataSourceEnabled("gdelt")).resolves.toBe(false);
    state.prefs = { gdelt: true };
    // Cached value wins until invalidation.
    await expect(isDataSourceEnabled("gdelt")).resolves.toBe(false);
    invalidateSourcePreferenceCache();
    await expect(isDataSourceEnabled("gdelt")).resolves.toBe(true);
  });

  it("returns the whole map without inventing keys", async () => {
    state.prefs = { sec: true, binance: false };
    await expect(getSourcePreferenceMap()).resolves.toEqual({ sec: true, binance: false });
  });
});
