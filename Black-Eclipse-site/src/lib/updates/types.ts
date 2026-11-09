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
  /** The installed version is below the release's `minSupported`. */
  mandatory: boolean;
  notesUrl: string | null;
  downloadUrl: string | null;
  publishedAt: string | null;
  /** Human-readable, safe to show. No stack traces or raw upstream bodies. */
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
}
