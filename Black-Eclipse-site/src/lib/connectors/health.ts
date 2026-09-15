// ── Connector health ────────────────────────────────────────────────────────
// Lightweight, application-level health state. No Prisma enum, no monitor loop
// — the custom connector rows persist the fields directly (mirroring the
// existing `SourceHealth` pattern), and this module derives the state string.

import type { HealthSnapshot, HealthState, TestResult } from "./types";

/** Derive a health state from an HTTP status code. */
export function stateFromStatus(status: number | undefined): HealthState {
  if (status === undefined) return "ERROR";
  if (status === 401 || status === 403) return "AUTH_FAILED";
  if (status === 429) return "RATE_LIMITED";
  if (status >= 200 && status < 300) return "CONNECTED";
  if (status === 0) return "UNAVAILABLE";
  return "ERROR";
}

/** Build a snapshot from a test result, without ever including the secret. */
export function snapshotFromTest(result: TestResult, now: Date = new Date()): HealthSnapshot {
  const iso = now.toISOString();
  const snapshot: HealthSnapshot = {
    state: result.state,
    lastTested: iso,
    httpStatus: result.httpStatus,
    latencyMs: result.latencyMs,
  };
  if (result.ok) {
    snapshot.lastSuccess = iso;
  } else {
    snapshot.lastError = result.message.slice(0, 300);
  }
  return snapshot;
}

/** One-line, human-readable health label for the Data Sources UI. */
export function describeHealth(snapshot: HealthSnapshot): string {
  switch (snapshot.state) {
    case "CONNECTED":
      return "Connected";
    case "AUTH_FAILED":
      return "Authentication failed";
    case "RATE_LIMITED":
      return "Rate limited";
    case "UNAVAILABLE":
      return "Unavailable";
    default:
      return "Error";
  }
}
