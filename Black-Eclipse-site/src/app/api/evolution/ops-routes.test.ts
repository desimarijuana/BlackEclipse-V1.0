// The operator proxies for corpus/autonomy: typed runtime calls, no policy
// re-implementation in the front door, and an honest 503 when the runtime is
// unavailable.

import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  class Unavailable extends Error {}
  return {
    Unavailable,
    corpus: vi.fn(async () => ({ success: true, manifest: { taskCount: 338 } })),
    rotation: vi.fn(async (input: unknown) => ({
      success: true, quarter: "2026Q4", plan: { moves: [] }, applied: false, input,
    })),
    autonomy: vi.fn(async () => ({ success: true, level: "supervised" })),
    pause: vi.fn(async (reason: string) => ({
      success: true, killSwitch: { paused: true, reason },
    })),
    resume: vi.fn(async () => ({
      success: true, killSwitch: { paused: false },
    })),
    decide: vi.fn(async (input: unknown) => ({
      success: true, decision: { allowed: true }, activates: false, input,
    })),
    apply: vi.fn(async (id: string) => ({
      success: true, applied: true, stateId: id,
    })),
  };
});

const { corpus, rotation, autonomy, pause, resume, decide, apply, Unavailable } = mocks;

vi.mock("@/lib/harness/evolution-client", () => ({
  getEvolutionCorpusStatus: () => mocks.corpus(),
  getEvolutionRotationPreview: (input: unknown) => mocks.rotation(input),
  getEvolutionAutonomyStatus: () => mocks.autonomy(),
  pauseEvolutionAutonomy: (reason: string) => mocks.pause(reason),
  resumeEvolutionAutonomy: () => mocks.resume(),
  decideEvolutionAutonomy: (input: unknown) => mocks.decide(input),
  applyEvolutionAutonomy: (id: string) => mocks.apply(id),
}));

vi.mock("@/lib/harness", () => ({ HarnessRuntimeUnavailable: mocks.Unavailable }));

import { GET as corpusGET } from "@/app/api/evolution/corpus/route";
import { GET as rotationGET } from "@/app/api/evolution/corpus/rotation/route";
import { GET as autonomyGET } from "@/app/api/evolution/rsl/autonomy/route";
import { POST as pausePOST } from "@/app/api/evolution/rsl/autonomy/pause/route";
import { POST as resumePOST } from "@/app/api/evolution/rsl/autonomy/resume/route";
import { POST as decidePOST } from "@/app/api/evolution/rsl/autonomy/decide/route";
import { POST as applyPOST } from "@/app/api/evolution/states/[id]/autonomy-apply/route";

function req(path: string, body?: unknown): Request {
  return new Request(`http://localhost:3000${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

describe("corpus/autonomy operator proxies", () => {
  it("returns the corpus status and passes the rotation query through", async () => {
    const corpusRes = await corpusGET();
    expect(corpusRes.status).toBe(200);
    expect((await corpusRes.json()).manifest.taskCount).toBe(338);

    const rotationRes = await rotationGET(
      req("/api/evolution/corpus/rotation?quarter=2026Q4&count=4"),
    );
    expect(rotationRes.status).toBe(200);
    expect(rotation).toHaveBeenCalledWith({ quarter: "2026Q4", count: 4 });
  });

  it("reads the autonomy status and toggles the kill switch", async () => {
    const statusRes = await autonomyGET();
    expect((await statusRes.json()).level).toBe("supervised");

    const pauseRes = await pausePOST(req("/pause", { reason: "operator stop" }));
    expect(pause).toHaveBeenCalledWith("operator stop");
    expect((await pauseRes.json()).killSwitch.paused).toBe(true);

    const resumeRes = await resumePOST();
    expect((await resumeRes.json()).killSwitch.paused).toBe(false);
  });

  it("requires a risk preview field and never claims to activate", async () => {
    const missing = await decidePOST(req("/decide", {}));
    expect(missing.status).toBe(400);
    expect(decide).not.toHaveBeenCalled();

    const ok = await decidePOST(req("/decide", { risk: "L1", changed: true }));
    expect(ok.status).toBe(200);
    expect(decide).toHaveBeenCalledWith({ risk: "L1", changed: true });
    expect((await ok.json()).activates).toBe(false);
  });

  it("applies one state through the explicit operator route", async () => {
    const res = await applyPOST(
      req("/apply", {}),
      { params: Promise.resolve({ id: "state_1" }) },
    );
    expect(apply).toHaveBeenCalledWith("state_1");
    expect(res.status).toBe(200);
  });

  it("maps a missing runtime to 503", async () => {
    corpus.mockRejectedValueOnce(new Unavailable("runtime down"));
    const res = await corpusGET();
    expect(res.status).toBe(503);
    expect((await res.json()).error).toContain("runtime down");
  });
});
