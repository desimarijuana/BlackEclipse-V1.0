// ─── Per-command rate limits (server-only, in-memory) ─────────────────────────
// A sliding window per actor + command id. Limits are risk-based by default and
// can be overridden per command (`rateLimit`). In-memory is deliberate: this is
// abuse/runaway protection for a single local runtime, not a billing quota.

import type { CommandRisk, CommandSpec } from "./command-registry";

const WINDOW_MS = 60_000;

const DEFAULTS: Record<CommandRisk, { limit: number; windowMs: number }> = {
  critical: { limit: 4, windowMs: WINDOW_MS },
  high: { limit: 6, windowMs: WINDOW_MS },
  medium: { limit: 20, windowMs: WINDOW_MS },
  low: { limit: 60, windowMs: WINDOW_MS },
  none: { limit: 120, windowMs: WINDOW_MS },
};

const MAX_KEYS = 2_000;
const buckets = new Map<string, number[]>();

export interface RateLimitDecision {
  ok: boolean;
  limit: number;
  remaining: number;
  retryAfterSec?: number;
}

export function checkCommandRateLimit(
  spec: CommandSpec,
  actor: "user" | "agent",
  now: number,
): RateLimitDecision {
  const policy = spec.rateLimit ?? DEFAULTS[spec.risk] ?? DEFAULTS.none;
  const windowMs = Math.max(1_000, policy.windowMs);
  const limit = Math.max(1, policy.limit);
  const key = `${actor}:${spec.id}`;
  const cutoff = now - windowMs;
  const recent = (buckets.get(key) ?? []).filter((at) => at > cutoff);

  if (recent.length >= limit) {
    const oldest = recent[0] ?? now;
    buckets.set(key, recent);
    return {
      ok: false,
      limit,
      remaining: 0,
      retryAfterSec: Math.max(1, Math.ceil((oldest + windowMs - now) / 1000)),
    };
  }

  recent.push(now);
  buckets.set(key, recent);
  if (buckets.size > MAX_KEYS) {
    const oldestKey = buckets.keys().next().value;
    if (oldestKey !== undefined) buckets.delete(oldestKey);
  }
  return { ok: true, limit, remaining: limit - recent.length };
}

/** Test-only: clear the buckets. */
export function resetRateLimitsForTests(): void {
  buckets.clear();
}
