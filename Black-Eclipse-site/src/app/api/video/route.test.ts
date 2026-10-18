import { describe, it, expect, vi, beforeEach } from "vitest";

const ensurePythonRuntime = vi.fn();
const guardMutation = vi.fn();
const runtimeIdentityHeaders = vi.fn(async (_request?: Request) => ({ "X-Harness-Identity": "jwt" }));

vi.mock("@/lib/harness/python-runtime", () => ({
  HARNESS_PY_URL: "http://127.0.0.1:8765",
  ensurePythonRuntime: (...a: unknown[]) => ensurePythonRuntime(...a),
}));
vi.mock("@/lib/harness/runtime-auth", () => ({
  runtimeCallbackToken: () => "test-token",
}));
vi.mock("@/lib/harness/runtime-identity", () => ({
  runtimeIdentityHeaders: async (request: Request) => runtimeIdentityHeaders(request),
}));
vi.mock("@/lib/api-guard", () => ({
  guardMutation: (...a: unknown[]) => guardMutation(...a),
}));

import { GET, POST } from "@/app/api/video/[[...path]]/route";

function ctx(path: string[]) {
  return { params: Promise.resolve({ path }) };
}

function req(method: string, body?: unknown) {
  return new Request("http://localhost:3000/api/video", {
    method,
    headers: { "content-type": "application/json", origin: "http://localhost:3000" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  ensurePythonRuntime.mockReset();
  guardMutation.mockReset();
  runtimeIdentityHeaders.mockClear();
  vi.unstubAllGlobals();
});

describe("video api proxy", () => {
  it("runs the mutation guard before touching the runtime", async () => {
    guardMutation.mockReturnValue({ status: 403, body: { error: "blocked" } });
    const res = await POST(req("POST", { name: "x" }), ctx(["projects"]));
    expect(res.status).toBe(403);
    expect(ensurePythonRuntime).not.toHaveBeenCalled();
  });

  it("reports an unavailable runtime honestly", async () => {
    guardMutation.mockReturnValue(null);
    ensurePythonRuntime.mockResolvedValue(false);
    const res = await POST(req("POST", { name: "x" }), ctx(["projects"]));
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(String(body.error)).toContain("Python agent runtime");
  });

  it("maps an empty path to /video/capabilities", async () => {
    ensurePythonRuntime.mockResolvedValue(true);
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ success: true, ready: true }));
    vi.stubGlobal("fetch", fetchMock);
    const res = await GET(req("GET"), ctx([]));
    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8765/video/capabilities");
    const headers = init.headers as Record<string, string>;
    expect(headers["X-Harness-Operator"]).toBe("test-token");
    expect(headers["X-Harness-Identity"]).toBe("jwt");
  });

  it("encodes segments and forwards the method + body", async () => {
    ensurePythonRuntime.mockResolvedValue(true);
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ success: true, job: { jobId: "j1" } }, 202));
    vi.stubGlobal("fetch", fetchMock);
    const res = await POST(
      req("POST", { mode: "final", conversationId: "chat_1" }),
      ctx(["projects", "vprj_abc", "render"]),
    );
    expect(res.status).toBe(202);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8765/video/projects/vprj_abc/render");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ mode: "final", conversationId: "chat_1" }));
  });

  it("passes upstream refusal status + detail through untouched", async () => {
    ensurePythonRuntime.mockResolvedValue(true);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { detail: { code: "REPAIR_LIMIT_REACHED", message: "already used its 2 repairs" } },
          409,
        ),
      ),
    );
    const res = await POST(req("POST", { ofJobId: "j1" }), ctx(["projects", "p", "repair"]));
    expect(res.status).toBe(409);
    const body = await res.json();
    expect(body.detail.code).toBe("REPAIR_LIMIT_REACHED");
  });
});
