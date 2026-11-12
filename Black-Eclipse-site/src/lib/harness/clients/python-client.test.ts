import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// The Python runtime answers "not found" as 404 with a human `detail`
// (e.g. "Run not found"). The client used to drop the status, so the callers
// that map 404 -> null fell through and the front door answered 500. These
// tests pin the status-aware behaviour.

const ensurePythonRuntime = vi.fn();
vi.mock("../python-runtime", () => ({
  HARNESS_PY_URL: "http://127.0.0.1:8765",
  ensurePythonRuntime: (...a: unknown[]) => ensurePythonRuntime(...a),
}));

import { getRunFromRuntime, getRunExplanationFromRuntime } from "./python-client";
import { HarnessHttpError, isNotFoundError } from "../errors";

function respond(status: number, body: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch
  );
}

beforeEach(() => {
  ensurePythonRuntime.mockReset();
  ensurePythonRuntime.mockResolvedValue(true);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("python-client 404 handling", () => {
  it("returns null for a missing run instead of throwing", async () => {
    respond(404, { detail: "Run not found" });
    await expect(getRunFromRuntime("run_missing")).resolves.toBeNull();
  });

  it("returns null for a missing run explanation", async () => {
    respond(404, { detail: "Run not found" });
    await expect(getRunExplanationFromRuntime("run_missing")).resolves.toBeNull();
  });

  it("keeps a non-404 failure as a failure", async () => {
    respond(500, { detail: "boom" });
    await expect(getRunFromRuntime("run_1")).rejects.toThrow("boom");
  });

  it("carries the HTTP status on the thrown error", async () => {
    respond(503, { detail: "runtime down" });
    const err = await getRunFromRuntime("run_1").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(HarnessHttpError);
    expect((err as HarnessHttpError).status).toBe(503);
    expect(isNotFoundError(err)).toBe(false);
  });

  it("recognises a 404 regardless of the detail text", () => {
    expect(isNotFoundError(new HarnessHttpError(404, "Run not found"))).toBe(true);
    expect(isNotFoundError(new HarnessHttpError(500, "Run not found"))).toBe(false);
  });
});
