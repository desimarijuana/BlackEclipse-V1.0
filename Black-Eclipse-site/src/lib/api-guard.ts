// Mutation guard + rate limiter for API routes.
//
// BlackEclipse is an open-source, zero-config app: cloning the repo and
// running `npm run dev` must work with no environment setup. So protection
// is layered by deployment mode instead of requiring accounts:
//
//   1. Browser UI (same-origin POSTs)          -> always allowed.
//   2. Server-to-server with CRON_SECRET set   -> allowed via
//      `Authorization: Bearer <CRON_SECRET>` or `x-api-key`.
//   3. Non-browser requests without a secret    -> only allowed when the
//      server itself is local (localhost / 127.0.0.1). On a public host,
//      setting CRON_SECRET is required for programmatic access.
//
// This keeps the out-of-the-box dev experience frictionless while making a
// public deployment safe with a single env var.

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]", "::1", "0.0.0.0"]);

function requestHost(request: Request): string {
  try {
    return new URL(request.url).host;
  } catch {
    return "";
  }
}

function originHost(request: Request): string | null {
  const origin = request.headers.get("origin");
  if (!origin || origin === "null") return null;
  try {
    return new URL(origin).host;
  } catch {
    return null;
  }
}

function isLocalHost(host: string): boolean {
  if (!host) return false;
  const hostname = host.split(":")[0].toLowerCase();
  return LOCAL_HOSTS.has(hostname);
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export interface GuardResult {
  allowed: boolean;
  reason?: string;
}

/**
 * Decide whether a mutating (POST/PUT/PATCH/DELETE) request may proceed.
 * Returns { allowed: true } or { allowed: false, reason }.
 */
export function checkMutationAllowed(request: Request): GuardResult {
  const host = requestHost(request);
  const origin = originHost(request);

  // 1) Explicit secret wins (cron jobs, scripts, reverse-proxied calls).
  const secret = process.env.CRON_SECRET;
  if (secret && secret !== "change-me-to-a-random-secret") {
    const auth = request.headers.get("authorization") || "";
    const bearer = auth.startsWith("Bearer ") ? auth.slice(7) : "";
    const apiKey = request.headers.get("x-api-key") || "";
    if (timingSafeEqual(bearer, secret) || timingSafeEqual(apiKey, secret)) {
      return { allowed: true };
    }
  }

  // 2) Same-origin browser requests are trusted (the app's own UI).
  //    Browsers always attach Origin to cross-site POSTs; a matching Origin
  //    means the call came from a page served by this app.
  if (origin !== null) {
    if (origin === host) return { allowed: true };
    // Origin present but mismatched -> cross-site request forgery attempt.
    return { allowed: false, reason: "Cross-origin requests are not allowed" };
  }

  // 3) No Origin header (curl, cron, another service). Allowed only when the
  //    server is local, or when the request targets a local loopback host.
  if (isLocalHost(host)) return { allowed: true };

  return {
    allowed: false,
    reason: "Set CRON_SECRET and send it as 'Authorization: Bearer <secret>' for programmatic access",
  };
}

/**
 * Convenience wrapper for route handlers: returns a 403 NextResponse when the
 * request is rejected, otherwise null (continue).
 */
export function guardMutation(
  request: Request,
  label: string
): { status: number; body: { error: string } } | null {
  const result = checkMutationAllowed(request);
  if (result.allowed) return null;
  console.warn(`[guard] blocked ${label}: ${result.reason}`);
  return { status: 403, body: { error: result.reason || "Forbidden" } };
}

// ─── Rate limiting ──────────────────────────────────────────────────────
// Simple in-memory fixed-window limiter. Adequate for the single-node,
// self-hosted deployments this app targets; swap for a shared store when
// running multiple instances.

interface Bucket {
  count: number;
  windowStart: number;
  windowMs: number;
}

const buckets = new Map<string, Bucket>();

// Periodically drop stale buckets so the map cannot grow unbounded.
const SWEEP_INTERVAL_MS = 60_000;
let lastSweep = Date.now();

function sweep(now: number) {
  if (now - lastSweep < SWEEP_INTERVAL_MS) return;
  lastSweep = now;
  for (const [key, bucket] of buckets) {
    if (now - bucket.windowStart > bucket.windowMs) buckets.delete(key);
  }
}

export interface RateLimitOptions {
  /** Max requests allowed per window. */
  limit: number;
  /** Window length in milliseconds. */
  windowMs: number;
}

export interface RateLimitResult {
  ok: boolean;
  remaining: number;
  retryAfterSec: number;
}

export function rateLimit(key: string, options: RateLimitOptions): RateLimitResult {
  const now = Date.now();
  sweep(now);
  const bucket = buckets.get(key);
  if (!bucket || now - bucket.windowStart >= options.windowMs) {
    buckets.set(key, { count: 1, windowStart: now, windowMs: options.windowMs });
    return { ok: true, remaining: options.limit - 1, retryAfterSec: 0 };
  }
  bucket.count++;
  if (bucket.count > options.limit) {
    return {
      ok: false,
      remaining: 0,
      retryAfterSec: Math.max(1, Math.ceil((bucket.windowStart + options.windowMs - now) / 1000)),
    };
  }
  return { ok: true, remaining: options.limit - bucket.count, retryAfterSec: 0 };
}

/** Best-effort client identity for rate limiting (proxy-aware). */
export function clientKey(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0].trim();
  const realIp = request.headers.get("x-real-ip");
  if (realIp) return realIp.trim();
  return requestHost(request) || "unknown";
}

// ─── Outbound fetch safety (SSRF) ───────────────────────────────────────
// User-configurable URLs (news feeds) are fetched server-side. Restrict them
// to public http(s) endpoints so a malicious feed config cannot probe
// localhost services or internal network hosts.

const PRIVATE_HOST_PATTERNS = [
  /^localhost$/i,
  /^127\./,
  /^0\./,
  /^10\./,
  /^169\.254\./,
  /^172\.(1[6-9]|2\d|3[01])\./,
  /^192\.168\./,
  /^\[?::1\]?$/,
  /^\[?fe80:/i,
  /^\[?fc00:/i,
  /^\[?fd[0-9a-f]{2}:/i,
  /\.local$/i,
  /\.internal$/i,
];

export interface UrlSafetyResult {
  safe: boolean;
  reason?: string;
}

export function checkOutboundUrl(rawUrl: string): UrlSafetyResult {
  let parsed: URL;
  try {
    parsed = new URL(rawUrl);
  } catch {
    return { safe: false, reason: "Invalid URL" };
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return { safe: false, reason: `Blocked protocol: ${parsed.protocol}` };
  }
  if (parsed.username || parsed.password) {
    return { safe: false, reason: "URLs with embedded credentials are not allowed" };
  }
  const hostname = parsed.hostname;
  if (PRIVATE_HOST_PATTERNS.some((re) => re.test(hostname))) {
    return { safe: false, reason: `Blocked host: ${hostname}` };
  }
  // Pure-IPv4/IPv6 literals are risky even when they don't match the common
  // private ranges above — require a real hostname.
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(hostname)) {
    return { safe: false, reason: "IP-literal URLs are not allowed" };
  }
  return { safe: true };
}

/** Filter a list of feed URLs down to the ones safe to fetch server-side. */
export function filterSafeUrls<T extends { url: string }>(items: T[]): T[] {
  return items.filter((item) => checkOutboundUrl(item.url).safe);
}

/**
 * Combined guard for expensive mutation endpoints: mutation policy + per-IP
 * rate limit in one call. Returns a NextResponse-ready rejection or null.
 */
export function guardExpensiveMutation(
  request: Request,
  label: string,
  limits: RateLimitOptions
): { status: number; body: { error: string }; headers?: Record<string, string> } | null {
  const forbidden = guardMutation(request, label);
  if (forbidden) return forbidden;
  const rl = rateLimit(`${label}:${clientKey(request)}`, limits);
  if (!rl.ok) {
    return {
      status: 429,
      body: { error: "Too many requests — slow down" },
      headers: { "Retry-After": String(rl.retryAfterSec) },
    };
  }
  return null;
}
