import { describe, it, expect, vi, beforeEach } from "vitest";

const ensurePythonRuntime = vi.fn();
const guardMutation = vi.fn();
const resolveRunModelSettings = vi.fn();

vi.mock("@/lib/harness/python-runtime", () => ({
  HARNESS_PY_URL: "http://127.0.0.1:8765",
  ensurePythonRuntime: (...a: unknown[]) => ensurePythonRuntime(...a),
}));
vi.mock("@/lib/harness/runtime-auth", () => ({
  runtimeCallbackToken: () => "test-token",
}));
vi.mock("@/lib/api-guard", () => ({
  guardMutation: (...a: unknown[]) => guardMutation(...a),
}));
vi.mock("@/lib/harness/run-service", () => ({
  resolveRunModelSettings: (...a: unknown[]) => resolveRunModelSettings(...a),
}));

import { GET, POST, PUT } from "@/app/api/canvas/[[...path]]/route";

function ctx(path: string[]) {
  return { params: Promise.resolve({ path }) };
}

function req(method: string, body?: unknown, origin = "http://localhost:3000") {
  return new Request("http://localhost:3000/api/canvas", {
    method,
    headers: { "content-type": "application/json", ...(origin ? { origin } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

describe("/api/canvas proxy", () => {
  beforeEach(() => {
    ensurePythonRuntime.mockReset();
    guardMutation.mockReset();
    resolveRunModelSettings.mockReset();
    vi.unstubAllGlobals();
  });

  it("refuses a cross-origin mutation before reaching the runtime", async () => {
    guardMutation.mockReturnValue({ status: 403, body: { error: "cross-origin" } });
    const res = await PUT(req("PUT", { baseVersion: 1, content: "x" }, "http://evil.example"), ctx(["artifacts", "a1"]));
    expect(res.status).toBe(403);
    expect(ensurePythonRuntime).not.toHaveBeenCalled();
  });

  it("returns 503 honestly when the runtime is unavailable", async () => {
    guardMutation.mockReturnValue(null);
    ensurePythonRuntime.mockResolvedValue(false);
    const res = await GET(req("GET"), ctx(["artifacts"]));
    expect(res.status).toBe(503);
  });

  it("injects modelSettings resolved from the vault for edit proposals", async () => {
    guardMutation.mockReturnValue(null);
    ensurePythonRuntime.mockResolvedValue(true);
    resolveRunModelSettings.mockResolvedValue({ provider: "openai", model: "gpt-4o", apiKey: "k" });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ operations: [], baseVersion: 1, currentVersion: 1, mode: "edit" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const res = await POST(req("POST", { baseVersion: 1, instruction: "improve", mode: "edit" }), ctx(["artifacts", "a1", "edits"]));
    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/canvas/artifacts/a1/edits");
    const sent = JSON.parse(init.body as string);
    expect(sent.modelSettings).toEqual({ provider: "openai", model: "gpt-4o", apiKey: "k" });
    expect(sent.model).toBeUndefined();
  });

  it("forwards a GET and passes JSON back", async () => {
    ensurePythonRuntime.mockResolvedValue(true);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ artifacts: [] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    const res = await GET(req("GET"), ctx(["artifacts"]));
    expect(res.status).toBe(200);
    expect((await res.json()).artifacts).toEqual([]);
    const url = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(url).toContain("/canvas/artifacts");
  });
});
