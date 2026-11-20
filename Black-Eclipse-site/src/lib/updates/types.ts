// Shared, dependency-free types for the update surface. Kept separate from the
// server-only verifier so client components can import them without dragging
// `node:crypto` into the browser bundle.

export const UPDATE_CHANNELS = ["stable", "beta"] as const;

export type UpdateChannel = (typeof UPDATE_CHANNELS)[number];

export function isUpdateChannel(value: unknown): value is UpdateChannel {
  return typeof value === "string" && (UPDATE_CHANNELS as readonly string[]).includes(value);
}

/** The server's answer to "is there a newer signed release than mine?". */
export interface UpdateStatus {
  /** false = the check itself failed; `error` says why (never guess "up to date"). */
  ok: boolean;
  currentVersion: string;
  channel: UpdateChannel;
  repository: string;
  /** ISO time of the successful check, or null when nothing was checked. */
  checkedAt: string | null;
  latestVersion: string | null;
  available: boolean;
  /**
   * True only for a git checkout, where the in-app updater can check out the
   * signed tag. A packaged install has no repository, so it updates by
   * downloading the release and running its installer.
   */
  canSelfUpdate: boolean;
  /** The installed version is below the release's `minSupported`. */
  mandatory: boolean;
  notesUrl: string | null;
  downloadUrl: string | null;
  publishedAt: string | null;
  /** Human-readable, safe to show. No stack traces or raw upstream bodies. */
  error: string | null;
}

/**
 * An in-app update that has been staged on this machine.
 *
 * The flow is deliberately two steps — stage, then restart — because promoting a
 * new build restarts the window and (on Windows) kills the server that spawned
 * it. Staging only checks out the signed tag, installs and builds; nothing the
 * running app depends on is touched. The restart is then owned by the shell.
 */
export type UpdateJobPhase =
  | "starting"
  | "verifying"
  | "backing-up"
  | "checkout"
  | "installing"
  | "building"
  | "promoting"
  /** Downloading a signed installer (packaged installs, which have no git tree). */
  | "downloading"
  /** The runner closed the app so it could replace its native dependencies. */
  | "stopping"
  | "ready"
  | "failed";

export type UpdateJobStatus = "running" | "ready" | "failed";

/** A signed installer asset for one platform (`<platform>-<arch>` key). */
export interface UpdateInstallerAsset {
  url: string;
  /** Hex SHA-256 of the exact bytes the URL serves. */
  sha256: string;
  size?: number;
}

export interface UpdateArtifact {
  path: string;
  name: string;
  sha256: string;
  bytes: number;
}

export interface UpdateJob {
  /** Random id per run, so a stale poll cannot be mistaken for the new run. */
  id: string;
  status: UpdateJobStatus;
  phase: UpdateJobPhase;
  /** One short, user-facing line for the current phase. */
  message: string;
  /** Version before the update (from the running build). */
  fromVersion: string;
  /** Version that was checked out and built, once known. */
  toVersion: string | null;
  /**
   * How the release was applied. `git` = checkout + build (source installs);
   * `installer` = verified signed installer (packaged installs).
   */
  mode?: "git" | "installer";
  /** The verified installer this run downloaded, when `mode` is `installer`. */
  artifact?: UpdateArtifact | null;
  startedAt: string;
  /** Heartbeat, written with every phase change. Used to spot a dead job. */
  updatedAt: string;
  finishedAt: string | null;
  /** The runner's pid, when the job file came from it. */
  pid: number | null;
  /** Last lines of updater output, oldest first. Bounded by the runner. */
  log: string[];
  error: string | null;
}

/** What a signed manifest payload contains after verification. */
export interface UpdateManifestPayload {
  schema: number;
  channel: string;
  version: string;
  publishedAt?: string;
  commit: string;
  notesUrl?: string;
  downloadUrl?: string;
  minSupported?: string;
  /**
   * Signed per-platform installers. The runner verifies the downloaded bytes
   * against `sha256` before it will start the installer.
   */
  installers?: Record<string, UpdateInstallerAsset>;
}
