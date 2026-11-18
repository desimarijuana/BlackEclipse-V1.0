import { describe, expect, it } from "vitest";

import {
  ensurePythonRuntime,
  isBindConflict,
  isHarnessHealth,
  parseListenerPids,
} from "@/lib/harness/python-runtime";

// Measured 2026-11-06: a second `npm run start` found a live runtime on the
// harness port, and the supervisor STILL spawned a rival uvicorn. It died with
// `WinError 10048` and the front door reported "runtime unavailable" for the
// rest of the session. These tests lock the three pure decisions that prevent
// that: which PIDs own the port, whether a health answer is OUR service, and
// whether a child died because the port was taken.

const NETSTAT = `
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    127.0.0.1:8766         0.0.0.0:0              LISTENING       4242
  TCP    127.0.0.1:18766        0.0.0.0:0              LISTENING       1111
  TCP    0.0.0.0:3100           0.0.0.0:0              LISTENING       2222
  TCP    [::]:8766              [::]:0                 LISTENING       4242
  TCP    127.0.0.1:50000        127.0.0.1:8766         ESTABLISHED     3333
`;

describe("parseListenerPids", () => {
  it("finds the listener on the exact port", () => {
    expect(parseListenerPids(NETSTAT, 8766)).toEqual(["4242"]);
  });

  it("does not match a longer port (18766) or a foreign address", () => {
    const pids = parseListenerPids(NETSTAT, 8766);
    expect(pids).not.toContain("1111");
    expect(pids).not.toContain("3333"); // established client, not a listener
  });

  it("returns nothing for a free port", () => {
    expect(parseListenerPids(NETSTAT, 9999)).toEqual([]);
  });

  it("ignores header lines and malformed rows", () => {
    expect(parseListenerPids("Proto  Local Address  State  PID\nLISTENING\n", 8766)).toEqual([]);
  });
});

describe("isHarnessHealth", () => {
  it("accepts our own runtime", () => {
    expect(isHarnessHealth({ ok: true, service: "eclipse-harness" })).toBe(true);
    // The runtime reports `harness-runtime`; the old allowlist only named the
    // legacy spelling and would reject the live service.
    expect(isHarnessHealth({ ok: true, service: "harness-runtime" })).toBe(true);
  });

  it("accepts an older runtime that reported only ok", () => {
    expect(isHarnessHealth({ ok: true })).toBe(true);
  });

  it("refuses a different HTTP service squatting on the port", () => {
    expect(isHarnessHealth({ ok: true, service: "something-else" })).toBe(false);
  });

  it("refuses no answer at all", () => {
    expect(isHarnessHealth(null)).toBe(false);
  });
});

describe("isBindConflict", () => {
  it("recognises the Windows bind error", () => {
    expect(
      isBindConflict(
        "ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8766)",
      ),
    ).toBe(true);
  });

  it("recognises the POSIX message", () => {
    expect(isBindConflict("error while attempting to bind on address: address already in use")).toBe(
      true,
    );
  });

  it("does not fire on ordinary logs", () => {
    expect(isBindConflict("Uvicorn running on http://127.0.0.1:8766")).toBe(false);
  });
});

// A page must never inherit the runtime's five-minute cold-start budget: on a
// stuck runtime that made every agent-backed page spin silently with no reason.
// These drive ensurePythonRuntime() through the coalesced-start path it uses for
// concurrent page routes.
describe("ensurePythonRuntime request budget", () => {
  const glob = globalThis as unknown as Record<string, unknown>;
  const KEY = "__harnessPyEnsure";

  async function withPendingStart<T>(work: Promise<boolean>, fn: () => Promise<T>): Promise<T> {
    const saved = glob[KEY];
    glob[KEY] = work;
    process.env.HARNESS_PY_REQUEST_WAIT_MS = "40";
    try {
      return await fn();
    } finally {
      glob[KEY] = saved;
      delete process.env.HARNESS_PY_REQUEST_WAIT_MS;
    }
  }

  it("answers 'unavailable' quickly when the start is stalled", async () => {
    // A start that never settles = a runtime that is hung.
    const started = Date.now();
    const ok = await withPendingStart(new Promise<boolean>(() => {}), () => ensurePythonRuntime());
    const elapsed = Date.now() - started;
    expect(ok).toBe(false);
    // It must actually wait out the request budget (40 ms here) rather than
    // failing instantly for an unrelated reason, and it must return far below
    // the 300 s cold-start budget.
    expect(elapsed).toBeGreaterThanOrEqual(30);
    expect(elapsed).toBeLessThan(5_000);
  });

  it("still reports true when the in-flight start succeeds", async () => {
    const ok = await withPendingStart(Promise.resolve(true), () => ensurePythonRuntime());
    expect(ok).toBe(true);
  });
});
