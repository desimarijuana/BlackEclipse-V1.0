// ── Investor Eye — per-source circuit breaker ────────────────────────────────
// Ingestion already isolates one source's failure from the others, but a source
// that is DETERMINISTICALLY down (a host that always times out, a provider that
// keeps returning 5xx) still costs its full timeout on EVERY cycle — the shared
// transport caps timeouts at 10s, and with several sources that is minutes of
// wall-clock per assembly spent waiting on something known to be broken.
//
// The breaker bounds that: after `FAILURE_THRESHOLD` consecutive failures a
// source is short-circuited (skipped without a network call) until a cooldown
// elapses, then allowed a single probe. A success closes it immediately. This is
// the standard three-state breaker (closed → open → half-open) reduced to the
// two facts the ingestion loop needs: "may I try?" and "did it work?".
//
// State is anchored on `globalThis` so every route bundle / dev HMR instance
// shares one breaker per source — the same discipline as `sources/registry.ts`
// and `cache.ts`.
//
// Honesty: an open breaker does NOT invent a source result. The skipped run is
// reported with the real reason and failure count, so a short-circuit is never
// displayed as a healthy-but-quiet source.

export interface BreakerConfig {
  /** Consecutive failures that open the circuit. */
  failureThreshold: number;
  /** How long the circuit stays open before one probe is allowed, in ms. */
  cooldownMs: number;
}

export const DEFAULT_BREAKER_CONFIG: BreakerConfig = {
  failureThreshold: 3,
  cooldownMs: 5 * 60 * 1000,
};

interface BreakerEntry {
  failures: number;
  /** Epoch ms when the open circuit may next be probed (0 = closed). */
  openUntil: number;
}

interface BreakerState {
  entries: Map<string, BreakerEntry>;
  config: BreakerConfig;
}

const globalForBreaker = globalThis as unknown as {
  investorEyeBreaker: BreakerState | undefined;
};

function state(): BreakerState {
  if (!globalForBreaker.investorEyeBreaker) {
    globalForBreaker.investorEyeBreaker = {
      entries: new Map(),
      config: { ...DEFAULT_BREAKER_CONFIG },
    };
  }
  return globalForBreaker.investorEyeBreaker;
}

/** Override the thresholds (used by tests; also a future settings seam). */
export function configureBreaker(config: Partial<BreakerConfig>): void {
  state().config = { ...state().config, ...config };
}

export interface BreakerSnapshot {
  id: string;
  open: boolean;
  failures: number;
  /** Ms until the next probe is allowed (0 when closed). */
  retryAfterMs: number;
}

/** Whether a source may be fetched right now. */
export function breakerCanAttempt(id: string, now = Date.now()): boolean {
  const entry = state().entries.get(id);
  if (!entry) return true;
  if (entry.openUntil === 0) return true;
  if (now >= entry.openUntil) {
    // Half-open: allow exactly one probe. `openUntil` stays set so a failure
    // re-opens immediately; a success clears it via `breakerRecordSuccess`.
    return true;
  }
  return false;
}

/** Record a successful run (including an honest empty result) and close it. */
export function breakerRecordSuccess(id: string): void {
  state().entries.delete(id);
}

/** Record a failed run and open the circuit after enough consecutive failures. */
export function breakerRecordFailure(id: string, now = Date.now()): void {
  const s = state();
  const entry = s.entries.get(id) ?? { failures: 0, openUntil: 0 };
  entry.failures += 1;
  if (entry.failures >= s.config.failureThreshold) {
    entry.openUntil = now + s.config.cooldownMs;
  }
  s.entries.set(id, entry);
}

/** Read-only view of a source's breaker, for observability and reporting. */
export function breakerSnapshot(id: string, now = Date.now()): BreakerSnapshot {
  const entry = state().entries.get(id);
  if (!entry) return { id, open: false, failures: 0, retryAfterMs: 0 };
  const open = entry.openUntil > now;
  return {
    id,
    open,
    failures: entry.failures,
    retryAfterMs: open ? entry.openUntil - now : 0,
  };
}

/** All sources currently short-circuited. */
export function openBreakers(now = Date.now()): BreakerSnapshot[] {
  const out: BreakerSnapshot[] = [];
  for (const id of state().entries.keys()) {
    const snap = breakerSnapshot(id, now);
    if (snap.open) out.push(snap);
  }
  return out;
}

/** Test seam: forget all breaker state. */
export function resetBreakers(): void {
  const s = state();
  s.entries.clear();
  s.config = { ...DEFAULT_BREAKER_CONFIG };
}
