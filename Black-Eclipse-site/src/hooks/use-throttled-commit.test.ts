import { describe, expect, it, vi } from "vitest";
import { createThrottledCommit } from "./use-throttled-commit";

/** Controllable clock + scheduler so the throttle is deterministic in tests. */
function harness<T>(commit: (value: T) => void, intervalMs = 100) {
  let time = 0;
  const scheduled: { fn: () => void; at: number; cancelled: boolean }[] = [];
  const now = () => time;
  const schedule = (fn: () => void, ms: number) => {
    const entry = { fn, at: time + ms, cancelled: false };
    scheduled.push(entry);
    return entry as unknown as ReturnType<typeof setTimeout>;
  };
  const cancel = (handle: ReturnType<typeof setTimeout>) => {
    (handle as unknown as { cancelled: boolean }).cancelled = true;
  };
  const advance = (ms: number) => {
    time += ms;
    for (const entry of scheduled) {
      if (!entry.cancelled && entry.at <= time) {
        entry.cancelled = true;
        entry.fn();
      }
    }
  };
  const api = createThrottledCommit<T>(commit, intervalMs, now, schedule, cancel);
  return { ...api, advance, get time() { return time; } };
}

describe("createThrottledCommit", () => {
  it("applies the first value immediately (leading edge)", () => {
    const commit = vi.fn();
    const t = harness<string>(commit, 100);
    t.emit("a");
    expect(commit).toHaveBeenCalledTimes(1);
    expect(commit).toHaveBeenCalledWith("a");
  });

  it("coalesces rapid calls to the latest value after the interval", () => {
    const commit = vi.fn();
    const t = harness<string>(commit, 100);
    t.emit("a");
    t.emit("b");
    t.emit("c");
    expect(commit).toHaveBeenCalledTimes(1);
    t.advance(100);
    expect(commit).toHaveBeenCalledTimes(2);
    expect(commit).toHaveBeenLastCalledWith("c");
  });

  it("applies immediately again once the interval has elapsed", () => {
    const commit = vi.fn();
    const t = harness<string>(commit, 100);
    t.emit("a");
    t.advance(100);
    t.emit("b");
    expect(commit).toHaveBeenCalledTimes(2);
    expect(commit).toHaveBeenLastCalledWith("b");
  });

  it("flush applies the pending value immediately", () => {
    const commit = vi.fn();
    const t = harness<string>(commit, 100);
    t.emit("a");
    t.emit("b");
    t.flush();
    expect(commit).toHaveBeenCalledTimes(2);
    expect(commit).toHaveBeenLastCalledWith("b");
    // A later scheduled tick must not double-apply.
    t.advance(200);
    expect(commit).toHaveBeenCalledTimes(2);
  });

  it("dispose flushes a pending value and clears the timer", () => {
    const commit = vi.fn();
    const t = harness<string>(commit, 100);
    t.emit("a");
    t.emit("b");
    t.dispose();
    expect(commit).toHaveBeenLastCalledWith("b");
    t.advance(200);
    expect(commit).toHaveBeenCalledTimes(2);
  });

  it("never runs the commit reentrantly more than once per interval window", () => {
    const commit = vi.fn();
    const t = harness<string>(commit, 100);
    for (let i = 0; i < 50; i++) t.emit(String(i));
    expect(commit).toHaveBeenCalledTimes(1);
    t.advance(100);
    expect(commit).toHaveBeenCalledTimes(2);
    expect(commit).toHaveBeenLastCalledWith("49");
  });
});
