import { describe, it, expect, vi, afterEach } from "vitest";

import {
  VideoApiError,
  cancelVideoJob,
  createVideoRecap,
  getVideoJob,
  renderVideoProject,
  repairVideoProject,
} from "./video-client";

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  vi.restoreAllMocks();
});

function mockFetch(payload: unknown, ok = true, status = 200) {
  const calls: { url: string; init?: RequestInit }[] = [];
  global.fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    return new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }) as unknown as typeof fetch;
  return calls;
}

describe("video-client", () => {
  it("queues a final render through the front door with the conversation id", async () => {
    const calls = mockFetch({ success: true, job: { jobId: "job_1", status: "QUEUED" } });
    const job = await renderVideoProject("vprj_abc", "final", { conversationId: "chat_9" });
    expect(job.jobId).toBe("job_1");
    expect(calls[0].url).toBe("/api/video/projects/vprj_abc/render");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({
      mode: "final",
      conversationId: "chat_9",
    });
  });

  it("encodes ids in job paths", async () => {
    const calls = mockFetch({ success: true, job: { jobId: "job_1" } });
    await getVideoJob("job/with slash");
    expect(calls[0].url).toBe("/api/video/jobs/job%2Fwith%20slash");
  });

  it("posts a repair with the failed job id", async () => {
    const calls = mockFetch({ success: true, job: { jobId: "job_2" } });
    await repairVideoProject("vprj_abc", "job_1", { spec: { schemaVersion: 2 } });
    expect(calls[0].url).toBe("/api/video/projects/vprj_abc/repair");
    expect(JSON.parse(String(calls[0].init?.body))).toMatchObject({ ofJobId: "job_1" });
  });

  it("creates a market recap project from symbols", async () => {
    const calls = mockFetch({ success: true, project: { id: "vprj_recap", name: "Recap", kind: "storyboard" } });
    const project = await createVideoRecap({ symbols: ["BTC-USD", "ETH-USD"], title: "Recap" });
    expect(project.id).toBe("vprj_recap");
    expect(calls[0].url).toBe("/api/video/recaps");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({
      symbols: ["BTC-USD", "ETH-USD"],
      title: "Recap",
    });
  });

  it("surfaces the runtime refusal code as a typed error", async () => {
    mockFetch(
      { detail: { code: "REPAIR_LIMIT_REACHED", message: "this failure line already used its 2 repair attempts" } },
      false,
      409,
    );
    await expect(cancelVideoJob("job_1")).rejects.toMatchObject({
      name: "VideoApiError",
      status: 409,
      code: "REPAIR_LIMIT_REACHED",
    });
    try {
      await cancelVideoJob("job_1");
    } catch (err) {
      expect(err).toBeInstanceOf(VideoApiError);
    }
  });
});
