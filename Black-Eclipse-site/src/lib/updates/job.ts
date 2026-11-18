// Server-only reader for the staged-update job file.
//
// The runner (`scripts/update-apply.js`) is spawned detached by
// /api/updates/apply and writes this file; the UI polls it. The file is the only
// channel between the two, because the runner outlives the server process it was
// started from (a rebuild replaces node_modules under the running app).

import fs from "node:fs";
import path from "node:path";

import type { UpdateJob, UpdateJobPhase, UpdateJobStatus } from "./types";

const JOB_STATUSES: readonly string[] = ["running", "ready", "failed"];
const JOB_PHASES: readonly string[] = [
  "starting",
  "verifying",
  "backing-up",
  "checkout",
  "installing",
  "building",
  "promoting",
  "stopping",
  "ready",
  "failed",
];

/** A job with no heartbeat for this long is presumed dead (the app may have quit). */
const STALE_AFTER_MS = 5 * 60 * 1000;

export function updateJobFile(): string {
  return (
    process.env.BE_UPDATE_JOB_FILE ||
    path.join(process.cwd(), ".runtime", "update-job.json")
  );
}

export function isUpdateJob(value: unknown): value is UpdateJob {
  if (!value || typeof value !== "object") return false;
  const job = value as Record<string, unknown>;
  return (
    typeof job.id === "string" &&
    typeof job.status === "string" &&
    JOB_STATUSES.includes(job.status) &&
    typeof job.phase === "string" &&
    JOB_PHASES.includes(job.phase)
  );
}

export interface UpdateJobReadOptions {
  /**
   * The version this install is actually running. A finished job recorded
   * against a different version is a spent receipt (the update it describes
   * already happened, or the CLI replaced the build) and must not be shown.
   */
  installedVersion?: string;
  now?: number;
}

/**
 * The job as the UI should see it. Anything unreadable returns null, and a
 * "running" job whose heartbeat stopped is downgraded to failed — the honest
 * answer, instead of a progress spinner that never finishes.
 */
export function readUpdateJob(options: UpdateJobReadOptions = {}): UpdateJob | null {
  const now = options.now ?? Date.now();
  let raw: string;
  try {
    raw = fs.readFileSync(updateJobFile(), "utf8");
  } catch {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isUpdateJob(parsed)) return null;

  const job: UpdateJob = {
    ...parsed,
    fromVersion: typeof parsed.fromVersion === "string" ? parsed.fromVersion : "",
    log: Array.isArray(parsed.log) ? parsed.log.slice(-80) : [],
    toVersion: typeof parsed.toVersion === "string" ? parsed.toVersion : null,
    pid: typeof parsed.pid === "number" ? parsed.pid : null,
    finishedAt: typeof parsed.finishedAt === "string" ? parsed.finishedAt : null,
    error: typeof parsed.error === "string" ? parsed.error : null,
  };

  if (job.status === "running") {
    const beat = Date.parse(job.updatedAt || job.startedAt);
    if (Number.isFinite(beat) && now - beat > STALE_AFTER_MS) {
      return {
        ...job,
        status: "failed" as UpdateJobStatus,
        phase: "failed" as UpdateJobPhase,
        error:
          job.error ||
          "The updater stopped responding — it may have been interrupted. Run `black update` to finish.",
        finishedAt: job.updatedAt,
      };
    }
    // A live run is always shown, even while it reports the version it left.
    return job;
  }

  // A finished run belongs to the build it started from. After a CLI update (or
  // this job's own restart) the installed version moves on, so re-showing the
  // old receipt would claim "Update did not finish" forever. A job with no
  // recorded version is kept: an unknown origin is not proof it is spent.
  if (
    options.installedVersion &&
    job.fromVersion &&
    job.fromVersion !== options.installedVersion
  ) {
    return null;
  }
  return job;
}
