import { describe, it, expect } from "vitest";
import { isAutoSyncDue } from "./scheduler";

const NOW = Date.UTC(2026, 10, 2, 12, 0, 0);
const INTERVAL = 5 * 60_000;

function link(overrides: Partial<{ autoSync: boolean; enabled: boolean; lastSyncedAt: string | null }> = {}) {
  return {
    autoSync: true,
    enabled: true,
    lastSyncedAt: null,
    ...overrides,
  };
}

describe("isAutoSyncDue", () => {
  it("is due when never synced", () => {
    expect(isAutoSyncDue(link(), NOW, INTERVAL)).toBe(true);
  });

  it("is not due before the interval", () => {
    expect(
      isAutoSyncDue(link({ lastSyncedAt: new Date(NOW - 60_000).toISOString() }), NOW, INTERVAL),
    ).toBe(false);
  });

  it("is due at or after the interval", () => {
    expect(
      isAutoSyncDue(link({ lastSyncedAt: new Date(NOW - INTERVAL).toISOString() }), NOW, INTERVAL),
    ).toBe(true);
  });

  it("respects the per-link toggle", () => {
    expect(isAutoSyncDue(link({ autoSync: false }), NOW, INTERVAL)).toBe(false);
    expect(isAutoSyncDue(link({ enabled: false }), NOW, INTERVAL)).toBe(false);
  });

  it("treats a malformed timestamp as never synced", () => {
    expect(isAutoSyncDue(link({ lastSyncedAt: "not-a-date" }), NOW, INTERVAL)).toBe(true);
  });
});
