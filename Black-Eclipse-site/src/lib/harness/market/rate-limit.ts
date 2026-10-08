// Live rate-limit extraction from provider response headers.
//
// The Python router paces on a DECLARED limit; these headers are the provider's
// REAL quota, which the gateway observes so pacing reflects the live limit.
// Parsing is provider-aware for the fields that matter, with a generic
// `x-ratelimit-*` / `retry-after` fallback.

export interface RateLimitInfo {
  limit?: number;
  used?: number;
  remaining?: number;
  windowSeconds?: number;
  retryAfterS?: number;
}

function num(value: string | undefined): number | undefined {
  if (value === undefined) return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

/** Binance public weight headers (spot 1200/min, USD-M futures 2400/min). */
function binance(headers: Record<string, string>, futures: boolean): RateLimitInfo | undefined {
  const used = num(headers["x-mbx-used-weight-1m"]);
  const retry = num(headers["retry-after"]);
  if (used === undefined && retry === undefined) return undefined;
  return {
    limit: futures ? 2400 : 1200,
    used,
    remaining: used !== undefined ? Math.max(0, (futures ? 2400 : 1200) - used) : undefined,
    windowSeconds: 60,
    retryAfterS: retry,
  };
}

export function rateLimitFromHeaders(
  providerId: string,
  headers: Record<string, string> | undefined,
  opts: { futures?: boolean } = {},
): RateLimitInfo | undefined {
  if (!headers) return undefined;
  if (providerId === "binance") return binance(headers, opts.futures === true);

  // Generic: RFC-style rate-limit headers + Retry-After.
  const limit = num(headers["x-ratelimit-limit"]);
  const remaining = num(headers["x-ratelimit-remaining"]);
  const reset = num(headers["x-ratelimit-reset"]);
  const retry = num(headers["retry-after"]);
  if (limit === undefined && remaining === undefined && retry === undefined) return undefined;
  // `x-ratelimit-reset` is often epoch seconds; convert to a window when sane.
  let windowSeconds: number | undefined;
  if (reset !== undefined && reset > 1_000_000_000) {
    const delta = reset - Math.floor(Date.now() / 1000);
    if (delta > 0 && delta <= 3600) windowSeconds = delta;
  }
  return { limit, remaining, used: limit !== undefined && remaining !== undefined ? limit - remaining : undefined, windowSeconds, retryAfterS: retry };
}
