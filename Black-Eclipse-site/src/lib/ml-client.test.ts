import { afterEach, describe, expect, it, vi } from "vitest";
import { mlClient } from "./ml-client";

// The client is a thin shaper over /api/ml. These tests pin the request shape
// (URL, method, body) and the honest error path so a broken proxy contract is
// caught without a running runtime.

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  vi.restoreAllMocks();
});

function mockFetch(payload: unknown, ok = true, status = 200) {
  const calls: { url: string; init?: RequestInit }[] = [];
  global.fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
  }) as unknown as typeof fetch;
  return calls;
}

describe("mlClient", () => {
  it("lists datasets from /api/ml/datasets", async () => {
    const calls = mockFetch({ datasets: [] });
    const result = await mlClient.listDatasets();
    expect(result.datasets).toEqual([]);
    expect(calls[0].url).toBe("/api/ml/datasets");
  });

  it("posts an experiment with the JSON body and method", async () => {
    const calls = mockFetch({ experimentId: "e1", runId: "r1", artifactId: "a", status: "completed", result: {}, registered: null });
    await mlClient.runExperiment({ datasetId: "d", datasetVersion: "1.0.0", modelFamily: "logistic" });
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toMatchObject({ datasetId: "d", modelFamily: "logistic" });
  });

  it("URL-encodes ids in path segments", async () => {
    const calls = mockFetch({ run: { id: "x" } });
    await mlClient.getRun("run/with space");
    expect(calls[0].url).toBe("/api/ml/runs/run%2Fwith%20space");
  });

  it("surfaces the server error message", async () => {
    mockFetch({ detail: { message: "dataset not found" } }, false, 404);
    await expect(mlClient.getRun("missing")).rejects.toThrow("dataset not found");
  });

  it("submits a background experiment and polls jobs", async () => {
    const calls = mockFetch({ background: true, job: { jobId: "j1", status: "QUEUED", mode: "BACKGROUND" } });
    const res = await mlClient.runExperimentBackground({ datasetId: "d", datasetVersion: "1.0.0", modelFamily: "lightgbm" });
    expect(res.background).toBe(true);
    expect(calls[0].url).toBe("/api/ml/experiments");
    expect(JSON.parse(String(calls[0].init?.body)).background).toBe(true);

    const jobCalls = mockFetch({ job: { jobId: "j1", status: "SUCCEEDED", progress: 1 } });
    const job = await mlClient.getJob("j1");
    expect(job.job.status).toBe("SUCCEEDED");
    expect(jobCalls[0].url).toBe("/api/ml/jobs/j1");
  });
});
