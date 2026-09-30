import { describe, it, expect, vi, beforeEach } from "vitest";

// Front-door contract for /api/skill-executions/[runId]. It reaches the Python
// runtime (status mapping) and DELETE cancels a run (operator-gated).

const getSkillExecution = vi.fn();
const cancelSkillExecution = vi.fn();

vi.mock("@/lib/harness/skills-client", () => ({
  getSkillExecution: (...a: unknown[]) => getSkillExecution(...a),
  cancelSkillExecution: (...a: unknown[]) => cancelSkillExecution(...a),
}));

import { GET, DELETE } from "@/app/api/skill-executions/[runId]/route";
import { HarnessRuntimeUnavailable } from "@/lib/harness/python-client";

const params = Promise.resolve({ runId: "run_1" });

function del(origin = "http://localhost:3000"): Request {
  return new Request("http://localhost:3000/api/skill-executions/run_1", {
    method: "DELETE",
    headers: origin ? { origin } : {},
  });
}

describe("GET /api/skill-executions/[runId]", () => {
  beforeEach(() => getSkillExecution.mockReset());

  it("returns 404 when the execution is not found", async () => {
    getSkillExecution.mockResolvedValueOnce(null);
    const res = await GET(new Request("http://localhost:3000/api/skill-executions/run_1"), { params });
    expect(res.status).toBe(404);
  });

  it("returns 503 when the Python runtime is unavailable", async () => {
    getSkillExecution.mockRejectedValueOnce(new HarnessRuntimeUnavailable("runtime down"));
    const res = await GET(new Request("http://localhost:3000/api/skill-executions/run_1"), { params });
    expect(res.status).toBe(503);
  });

  it("returns the execution on success", async () => {
    getSkillExecution.mockResolvedValueOnce({ id: "run_1", status: "ok" });
    const res = await GET(new Request("http://localhost:3000/api/skill-executions/run_1"), { params });
    expect(res.status).toBe(200);
    expect((await res.json()).execution.id).toBe("run_1");
  });
});

describe("DELETE /api/skill-executions/[runId]", () => {
  beforeEach(() => cancelSkillExecution.mockReset());

  it("refuses a cross-origin cancel", async () => {
    const res = await DELETE(del("http://evil.example"), { params });
    expect(res.status).toBe(403);
    expect(cancelSkillExecution).not.toHaveBeenCalled();
  });

  it("cancels the run for an operator", async () => {
    cancelSkillExecution.mockResolvedValueOnce(true);
    const res = await DELETE(del(), { params });
    expect(res.status).toBe(200);
    expect((await res.json()).cancelled).toBe(true);
  });
});
