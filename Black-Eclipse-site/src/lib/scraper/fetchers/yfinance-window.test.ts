import { describe, it, expect, vi, beforeEach } from "vitest";

const runPythonBridge = vi.fn();

vi.mock("./python", () => ({
  findPython: () => ({ pythonPath: "python", ok: true }),
  runPythonBridge: (...a: unknown[]) => runPythonBridge(...a),
}));

import { fetchYahooBatchRaw } from "./yfinance";

describe("fetchYahooBatchRaw — the window travels with the request", () => {
  beforeEach(() => {
    runPythonBridge.mockReset();
    runPythonBridge.mockResolvedValue({
      stdout: JSON.stringify({
        history: { AAPL: [{ date: "2026-01-02", close: 1 }] },
        quotes: {},
      }),
      stderr: "",
      code: 0,
    });
  });

  it("passes an explicit start/end window to the bridge", async () => {
    await fetchYahooBatchRaw(["AAPL"], "us", "1d", "1y", {
      start: "2025-10-20",
      end: "2026-10-20",
    });
    const args = runPythonBridge.mock.calls[0][1] as string[];
    // [market, symbols, interval, period, start, end]
    expect(args.slice(0, 4)).toEqual(["us", "AAPL", "1d", "1y"]);
    expect(args[4]).toBe("2025-10-20");
    expect(args[5]).toBe("2026-10-20");
  });

  it("keeps the legacy period call when no window is given", async () => {
    await fetchYahooBatchRaw(["AAPL"], "us", "1d", "1y");
    const args = runPythonBridge.mock.calls[0][1] as string[];
    expect(args).toEqual(["us", "AAPL", "1d", "1y"]);
  });

  it("keeps the quote path when no interval/period is given", async () => {
    await fetchYahooBatchRaw(["AAPL"], "us");
    const args = runPythonBridge.mock.calls[0][1] as string[];
    expect(args).toEqual(["us", "AAPL"]);
  });
});
