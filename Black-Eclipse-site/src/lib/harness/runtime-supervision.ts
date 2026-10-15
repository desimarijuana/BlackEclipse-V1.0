// ─── Runtime supervision policy (pure, no I/O) ───────────────────────────────
// The front door's decision to REPLACE a Python runtime is dangerous: a restart
// orphans every run in flight — including one paused on an operator-approval
// card, whose change is then lost. The policy therefore lives here, separated
// from the spawn/netstat plumbing, so it is exhaustively unit-testable.

/** The subset of the runtime's `/health` payload the supervisor reasons about. */
export interface RuntimeHealth {
  ok?: boolean;
  service?: string;
  startedAtMs?: number;
  /** OS pid of the runtime process (advisory; distinguishes two processes). */
  pid?: number;
  /** Agent runs in flight in that process. 0/absent = idle. */
  activeRuns?: number;
}

/**
 * How long after a confirmed-healthy probe we still treat a runtime as "busy,
 * not hung". Killing a runtime that answered moments ago orphans its in-flight
 * runs, so a transient probe miss inside this window never triggers a kill.
 */
export const BUSY_GRACE_MS = 30_000;

/**
 * Whether a healthy-looking runtime should be REPLACED because it serves code
 * older than the source on disk (a restart is how a `python/harness/**` edit
 * takes effect).
 *
 * It refuses to replace a runtime that is actively serving runs
 * (`activeRuns > 0`): a restart would orphan those runs — including one paused
 * on an operator-approval card — and their changes would be lost. The restart
 * is deferred to a later probe, when the runtime is idle.
 */
export function shouldReplaceStaleRuntime(
  health: RuntimeHealth | null,
  sourceMtimeMs: number,
): boolean {
  if (!health || health.service !== "harness-runtime") return false;
  const startedAt = health.startedAtMs ?? 0;
  if (!(sourceMtimeMs > 0) || !(startedAt > 0) || !(startedAt < sourceMtimeMs)) return false;
  if ((health.activeRuns ?? 0) > 0) return false;
  return true;
}

/**
 * A runtime that answered within the busy-grace window is treated as BUSY, not
 * hung. Used before clearing a silent-but-listening port: a transient probe miss
 * must not cost the runtime its in-flight runs.
 */
export function isRecentlyHealthy(lastHealthyAt: number | undefined, now: number): boolean {
  return lastHealthyAt !== undefined && now - lastHealthyAt < BUSY_GRACE_MS;
}
