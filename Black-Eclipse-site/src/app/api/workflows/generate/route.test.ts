import { describe, it, expect, vi, beforeEach } from "vitest";

// Front-door contract for POST /api/workflows/generate — the one call that turns
// a sentence into a SAVED Graph Studio workflow. It must plan through the Python
// runtime, refuse a plan that does not validate, and write only through the
// canonical workflow store.

const runtimeFetch = vi.fn(async (_url: string, _init?: RequestInit): Promise<unknown> => ({}));

const createWorkflow = vi.fn();

vi.mock("@/lib/harness/python-runtime", () => ({
  HARNESS_PY_URL: "http://127.0.0.1:8765",
  ensurePythonRuntime: async () => true,
}));

vi.mock("@/lib/harness/runtime-auth", () => ({
  runtimeCallbackToken: () => "token",
}));

vi.mock("@/lib/harness/runtime-identity", () => ({
  runtimeIdentityHeaders: async () => ({ "X-Harness-Identity": "test" }),
}));

vi.mock("@/lib/settings", () => ({
  getLLMConfig: async () => ({
    provider: "ollama",
    baseUrl: "http://127.0.0.1:11434/v1",
    apiKey: null,
    model: "llama3.1",
    contextWindow: 8192,
  }),
}));

vi.mock("@/lib/graph-studio/server-store", () => ({
  createWorkflow: (...args: unknown[]) => createWorkflow(...args),
}));

import { createWorkflowIR } from "@/lib/graph-studio/ir";
import { POST } from "@/app/api/workflows/generate/route";

function req(body: unknown): Request {
  return new Request("http://localhost:3000/api/workflows/generate", {
    method: "POST",
    headers: { "content-type": "application/json", host: "localhost:3000" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

function planResponse(body: unknown, status = 200): unknown {
  return {
    ok: status < 400,
    status,
    json: async () => body,
  } as unknown as Response;
}

const ir = createWorkflowIR({ name: "Planned workflow", description: "From the planner" });

beforeEach(() => {
  runtimeFetch.mockReset();
  createWorkflow.mockReset();
  createWorkflow.mockImplementation(async (input: { name: string; description: string; ir: unknown }) => ({
    id: "wf_saved",
    name: input.name,
    description: input.description,
    currentVersion: 1,
  }));
  vi.stubGlobal("fetch", runtimeFetch);
});

describe("POST /api/workflows/generate", () => {
  it("refuses a description that is too short without calling the runtime", async () => {
    const res = await POST(req({ objective: "hi" }));
    expect(res.status).toBe(400);
    expect(runtimeFetch).not.toHaveBeenCalled();
  });

  it("forwards the objective to the planner and saves the validated IR", async () => {
    runtimeFetch.mockResolvedValue(
      planResponse({ ok: true, ir, nodeCount: 2, edgeCount: 1, executionMode: "research", warnings: [] }),
    );
    const res = await POST(req({ objective: "Fetch AAPL bars and report the SMA." }));
    expect(res.status).toBe(201);
    const body = (await res.json()) as {
      workflow: { id: string; name: string };
      plan: { nodeCount: number };
    };
    expect(body.workflow.id).toBe("wf_saved");
    expect(body.workflow.name).toBe("Planned workflow");
    expect(body.plan.nodeCount).toBe(2);
    expect(createWorkflow).toHaveBeenCalledTimes(1);
    const saved = createWorkflow.mock.calls[0][0] as { tags: string[]; ir: { name: string } };
    expect(saved.tags).toEqual(["generated"]);
    expect(saved.ir.name).toBe("Planned workflow");
  });

  it("returns the planner diagnostics and saves nothing when the plan is invalid", async () => {
    runtimeFetch.mockResolvedValue(
      planResponse({ ok: false, errors: [{ message: "unknown node type 'foo'" }], warnings: [] }),
    );
    const res = await POST(req({ objective: "Build something the planner cannot build." }));
    expect(res.status).toBe(422);
    expect((await res.json()).error).toContain("unknown node type");
    expect(createWorkflow).not.toHaveBeenCalled();
  });

  it("surfaces a planner transport error honestly", async () => {
    runtimeFetch.mockRejectedValue(new Error("connect ECONNREFUSED"));
    const res = await POST(req({ objective: "Fetch AAPL bars and report the SMA." }));
    expect(res.status).toBe(502);
    expect((await res.json()).error).toContain("ECONNREFUSED");
    expect(createWorkflow).not.toHaveBeenCalled();
  });
});
