import { afterEach, beforeEach, describe, expect, it } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { readUpdateJob, updateJobFile } from "./job";

let dir: string;

function writeJob(job: Record<string, unknown>) {
  fs.writeFileSync(updateJobFile(), JSON.stringify(job), "utf8");
}

const base = {
  id: "abc123",
  status: "running",
  phase: "building",
  message: "Building the new version (slow)…",
  fromVersion: "0.4.0",
  toVersion: null,
  startedAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  finishedAt: null,
  pid: 4242,
  log: [],
  error: null,
};

describe("readUpdateJob", () => {
  const previous = process.env.BE_UPDATE_JOB_FILE;

  beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), "be-update-job-"));
    process.env.BE_UPDATE_JOB_FILE = path.join(dir, "update-job.json");
  });

  afterEach(() => {
    if (previous === undefined) delete process.env.BE_UPDATE_JOB_FILE;
    else process.env.BE_UPDATE_JOB_FILE = previous;
    fs.rmSync(dir, { recursive: true, force: true });
  });

  it("returns null when nothing has been staged", () => {
    expect(readUpdateJob()).toBeNull();
  });

  it("ignores a corrupt job file rather than showing a fake run", () => {
    fs.writeFileSync(updateJobFile(), "{not json", "utf8");
    expect(readUpdateJob()).toBeNull();
  });

  it("returns a fresh running job unchanged", () => {
    writeJob(base);
    const job = readUpdateJob();
    expect(job?.status).toBe("running");
    expect(job?.phase).toBe("building");
  });

  it("downgrades a running job with no heartbeat to failed", () => {
    const stale = new Date(Date.now() - 10 * 60 * 1000).toISOString();
    writeJob({ ...base, updatedAt: stale });
    const job = readUpdateJob();
    expect(job?.status).toBe("failed");
    expect(job?.error).toContain("stopped responding");
  });

  it("keeps a ready job readable and bounds the log tail", () => {
    writeJob({
      ...base,
      status: "ready",
      phase: "ready",
      toVersion: "0.4.1",
      finishedAt: new Date().toISOString(),
      log: Array.from({ length: 200 }, (_, i) => `line ${i}`),
    });
    const job = readUpdateJob();
    expect(job?.status).toBe("ready");
    expect(job?.toVersion).toBe("0.4.1");
    expect(job?.log).toHaveLength(80);
  });

  it("reads a packaged installer job's download phase and verified artifact", () => {
    writeJob({
      ...base,
      phase: "downloading",
      mode: "installer",
      artifact: { path: "C:\\data\\.runtime\\updates\\setup.exe", name: "setup.exe", sha256: "c".repeat(64), bytes: 42 },
    });
    const job = readUpdateJob();
    expect(job?.phase).toBe("downloading");
    expect(job?.mode).toBe("installer");
    expect(job?.artifact?.sha256).toBe("c".repeat(64));
  });

  // Regression: after a CLI update, the app kept serving the previous run's
  // failure and the title-bar panel claimed "Update did not finish" forever.
  it("drops a finished job recorded against a version we already left", () => {
    writeJob({
      ...base,
      status: "failed",
      phase: "failed",
      finishedAt: new Date().toISOString(),
      error: "the working tree has uncommitted changes",
    });
    expect(readUpdateJob({ installedVersion: "0.4.1" })).toBeNull();
  });

  it("keeps a finished job for the version that is actually running", () => {
    writeJob({
      ...base,
      status: "failed",
      phase: "failed",
      finishedAt: new Date().toISOString(),
      error: "the working tree has uncommitted changes",
    });
    const job = readUpdateJob({ installedVersion: "0.4.0" });
    expect(job?.status).toBe("failed");
    expect(job?.error).toContain("uncommitted");
  });

  it("never hides a live run just because it reports another version", () => {
    writeJob(base);
    const job = readUpdateJob({ installedVersion: "0.4.1" });
    expect(job?.status).toBe("running");
  });

  it("keeps a finished job whose origin version is unknown", () => {
    writeJob({ ...base, status: "failed", phase: "failed", fromVersion: "" });
    expect(readUpdateJob({ installedVersion: "0.4.1" })?.status).toBe("failed");
  });
});
