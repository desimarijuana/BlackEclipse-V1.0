import { describe, expect, it } from "vitest";
import { BUSY_GRACE_MS, isRecentlyHealthy, shouldReplaceStaleRuntime } from "./runtime-supervision";

const ours = (over: Partial<Parameters<typeof shouldReplaceStaleRuntime>[0]> = {}) => ({
  ok: true,
  service: "harness-runtime",
  startedAtMs: 1000,
  activeRuns: 0,
  ...over,
});

describe("shouldReplaceStaleRuntime", () => {
  it("keeps a runtime whose code is newer than the source on disk", () => {
    expect(shouldReplaceStaleRuntime(ours({ startedAtMs: 2000 }), 1000)).toBe(false);
  });

  it("replaces a stale IDLE runtime so a harness edit takes effect", () => {
    expect(shouldReplaceStaleRuntime(ours({ startedAtMs: 1000, activeRuns: 0 }), 2000)).toBe(true);
  });

  it("NEVER replaces a runtime that is actively serving runs", () => {
    // A running agent (or one paused on an approval card) must survive.
    expect(shouldReplaceStaleRuntime(ours({ startedAtMs: 1000, activeRuns: 1 }), 2000)).toBe(false);
    expect(shouldReplaceStaleRuntime(ours({ startedAtMs: 1000, activeRuns: 4 }), 9999)).toBe(false);
  });

  it("ignores a service that is not ours", () => {
    expect(shouldReplaceStaleRuntime(ours({ service: "something-else", startedAtMs: 1000 }), 2000)).toBe(false);
  });

  it("is conservative when health or timestamps are missing", () => {
    expect(shouldReplaceStaleRuntime(null, 2000)).toBe(false);
    expect(shouldReplaceStaleRuntime(ours({ startedAtMs: 0 }), 2000)).toBe(false);
    expect(shouldReplaceStaleRuntime(ours({ startedAtMs: 1000 }), 0)).toBe(false);
  });
});

describe("isRecentlyHealthy", () => {
  it("treats a runtime that answered inside the grace window as busy, not hung", () => {
    const now = 1_000_000;
    expect(isRecentlyHealthy(now - 1, now)).toBe(true);
    expect(isRecentlyHealthy(now - (BUSY_GRACE_MS - 1), now)).toBe(true);
  });

  it("allows a kill only when the last success is older than the grace window", () => {
    const now = 1_000_000;
    expect(isRecentlyHealthy(now - BUSY_GRACE_MS, now)).toBe(false);
    expect(isRecentlyHealthy(now - 10 * BUSY_GRACE_MS, now)).toBe(false);
  });

  it("does not treat an unknown last-success as recent", () => {
    expect(isRecentlyHealthy(undefined, 1_000_000)).toBe(false);
  });
});
