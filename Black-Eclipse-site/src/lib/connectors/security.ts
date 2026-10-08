// ── Connector outbound security ─────────────────────────────────────────────
// Hardened SSRF protection for operator-configured outbound requests.
//
// This is deliberately SEPARATE from `checkOutboundUrl` in `src/lib/api-guard.ts`.
// That helper is a hostname-regex gate for RSS feed URLs; it is not sufficient as
// a security boundary for arbitrary user APIs because it does not resolve DNS,
// does not revalidate redirects, and enforces no response-size cap.
//
// This module provides:
//   1. canonical IP classification (parsed values, not regex strings),
//   2. DNS resolution + validation BEFORE connecting,
//   3. a DNS-pinned `lookup` so validation and connection cannot be separated
//      by a DNS rebinding race,
//   4. manual redirects (never auto-followed),
//   5. a hard, streamed response-size cap,
//   6. a strict timeout.
//
// It uses only Node built-ins (node:dns, node:https, node:net) — no new
// dependency is added.

import dns from "node:dns";
import https from "node:https";
import net from "node:net";

export const DEFAULT_TIMEOUT_MS = 8_000;
export const MAX_TIMEOUT_MS = 10_000;
export const DEFAULT_MAX_BYTES = 5 * 1024 * 1024; // 5 MB

export type OutboundErrorCode =
  | "invalid_url"
  | "blocked_protocol"
  | "blocked_credentials"
  | "blocked_host"
  | "dns_failure"
  | "timeout"
  | "too_large"
  | "redirect"
  | "network";

export class OutboundError extends Error {
  readonly code: OutboundErrorCode;
  constructor(code: OutboundErrorCode, message: string) {
    super(message);
    this.name = "OutboundError";
    this.code = code;
  }
}

// ── IP classification (pure) ────────────────────────────────────────────────

/**
 * `URL.hostname` keeps the square brackets on IPv6 hosts (`"[::1]"`), which
 * `net.isIP` does not accept. Strip them before any IP classification.
 */
export function normalizeHostname(hostname: string): string {
  return hostname.startsWith("[") && hostname.endsWith("]") ? hostname.slice(1, -1) : hostname;
}

function ipv4ToInt(ip: string): number | null {
  const parts = ip.split(".");
  if (parts.length !== 4) return null;
  let n = 0;
  for (const p of parts) {
    if (!/^\d{1,3}$/.test(p)) return null;
    const v = Number(p);
    if (v > 255) return null;
    n = (n << 8) | v;
  }
  return n >>> 0;
}

// [base, prefixLength] — everything that must never be reachable outbound.
const BLOCKED_V4: Array<[string, number]> = [
  ["0.0.0.0", 8], // "this network"
  ["10.0.0.0", 8], // RFC1918
  ["100.64.0.0", 10], // CGNAT (covers 100.100.100.200 metadata)
  ["127.0.0.0", 8], // loopback
  ["169.254.0.0", 16], // link-local (covers 169.254.169.254 metadata)
  ["172.16.0.0", 12], // RFC1918
  ["192.0.0.0", 24], // IETF protocol assignments
  ["192.0.2.0", 24], // TEST-NET-1
  ["192.168.0.0", 16], // RFC1918
  ["198.18.0.0", 15], // benchmarking
  ["198.51.100.0", 24], // TEST-NET-2
  ["203.0.113.0", 24], // TEST-NET-3
  ["224.0.0.0", 4], // multicast
  ["240.0.0.0", 4], // reserved + broadcast
];

/**
 * Parse an IPv6 literal into eight 16-bit groups. Handles `::`, zone ids, and
 * embedded IPv4 tails such as `::ffff:127.0.0.1`. Returns null when malformed.
 */
export function parseIpv6(input: string): number[] | null {
  let ip = input.trim();
  if (ip.startsWith("[") && ip.endsWith("]")) ip = ip.slice(1, -1);
  const zone = ip.indexOf("%");
  if (zone !== -1) ip = ip.slice(0, zone);
  if (ip.length === 0) return null;

  // Embedded IPv4 tail (e.g. ::ffff:127.0.0.1) → two hex groups.
  const tailPart = ip.slice(ip.lastIndexOf(":") + 1);
  if (tailPart.includes(".")) {
    const v4 = ipv4ToInt(tailPart);
    if (v4 === null) return null;
    const hex = `${((v4 >>> 16) & 0xffff).toString(16)}:${(v4 & 0xffff).toString(16)}`;
    ip = ip.slice(0, ip.lastIndexOf(":") + 1) + hex;
  }

  const halves = ip.split("::");
  if (halves.length > 2) return null;

  const parseGroups = (s: string): number[] | null => {
    if (s === "") return [];
    const out: number[] = [];
    for (const piece of s.split(":")) {
      if (!/^[0-9a-fA-F]{1,4}$/.test(piece)) return null;
      out.push(parseInt(piece, 16));
    }
    return out;
  };

  const head = parseGroups(halves[0]);
  if (head === null) return null;
  let groups: number[];
  if (halves.length === 2) {
    const back = parseGroups(halves[1]);
    if (back === null) return null;
    const missing = 8 - head.length - back.length;
    if (missing < 1) return null;
    groups = [...head, ...new Array<number>(missing).fill(0), ...back];
  } else {
    groups = head;
  }
  return groups.length === 8 ? groups : null;
}

function v6Matches(groups: number[], baseCidr: string, prefix: number): boolean {
  const base = parseIpv6(baseCidr);
  if (!base) return false;
  let bits = prefix;
  for (let i = 0; i < 8 && bits > 0; i++) {
    const take = Math.min(16, bits);
    const mask = take === 16 ? 0xffff : (0xffff << (16 - take)) & 0xffff;
    if ((groups[i] & mask) !== (base[i] & mask)) return false;
    bits -= take;
  }
  return true;
}

const BLOCKED_V6: Array<[string, number]> = [
  ["::", 128], // unspecified
  ["::1", 128], // loopback
  ["fe80::", 10], // link-local
  ["fc00::", 7], // unique local
  ["ff00::", 8], // multicast
  ["2001:db8::", 32], // documentation
  ["2002::", 16], // 6to4
  ["64:ff9b::", 96], // NAT64
];

/** True when an IP literal must never be reachable by a connector. */
export function isBlockedAddress(ip: string): boolean {
  const fam = net.isIP(ip);
  if (fam === 4) {
    const n = ipv4ToInt(ip);
    if (n === null) return true;
    return BLOCKED_V4.some(([base, prefix]) => {
      const b = ipv4ToInt(base);
      if (b === null) return true;
      const shift = 32 - prefix;
      return shift === 0 ? n === b : n >>> shift === b >>> shift;
    });
  }
  if (fam === 6) {
    const groups = parseIpv6(ip);
    if (!groups) return true;
    // IPv4-mapped (::ffff:x.x.x.x) — classify the embedded address.
    if (v6Matches(groups, "::ffff:0:0", 96)) {
      const v4 = `${(groups[6] >> 8) & 0xff}.${groups[6] & 0xff}.${(groups[7] >> 8) & 0xff}.${groups[7] & 0xff}`;
      return isBlockedAddress(v4);
    }
    return BLOCKED_V6.some(([base, prefix]) => v6Matches(groups, base, prefix));
  }
  return true; // not an IP literal — caller must not use the IP path
}

// ── URL validation ──────────────────────────────────────────────────────────

export interface UrlCheck {
  safe: boolean;
  reason?: string;
  code?: OutboundErrorCode;
  hostname?: string;
}

/**
 * Canonicalize and pre-check a URL. The WHATWG `URL` parser normalizes
 * alternate IPv4 encodings (decimal / octal / hex) into dotted form, so we
 * classify the normalized hostname rather than pattern-matching raw strings.
 */
export function validateOutboundUrl(rawUrl: string): UrlCheck {
  let parsed: URL;
  try {
    parsed = new URL(rawUrl);
  } catch {
    return { safe: false, reason: "Invalid URL", code: "invalid_url" };
  }
  if (parsed.protocol !== "https:") {
    return { safe: false, reason: `Blocked protocol: ${parsed.protocol}`, code: "blocked_protocol" };
  }
  if (parsed.username || parsed.password) {
    return { safe: false, reason: "URLs with embedded credentials are not allowed", code: "blocked_credentials" };
  }
  const hostname = parsed.hostname;
  if (!hostname) return { safe: false, reason: "Missing hostname", code: "invalid_url" };
  const bare = normalizeHostname(hostname);
  if (net.isIP(bare) && isBlockedAddress(bare)) {
    return { safe: false, reason: `Blocked address: ${bare}`, code: "blocked_host", hostname: bare };
  }
  return { safe: true, hostname: bare };
}

/**
 * Redact a URL for logs and error messages. Query strings routinely carry API
 * keys, so only origin + pathname are ever surfaced.
 */
export function redactUrl(rawUrl: string): string {
  try {
    const u = new URL(rawUrl);
    return `${u.origin}${u.pathname}`;
  } catch {
    return "<invalid-url>";
  }
}

// ── DNS ─────────────────────────────────────────────────────────────────────

export type LookupCallback = (
  err: NodeJS.ErrnoException | null,
  address: string | LookupAllEntry[],
  family: number
) => void;
export type LookupFn = (hostname: string, options: dns.LookupOptions, callback: LookupCallback) => void;

export interface LookupAllEntry {
  address: string;
  family: number;
}

export type LookupAllFn = (
  hostname: string,
  options: dns.LookupAllOptions,
  callback: (err: NodeJS.ErrnoException | null, addresses: LookupAllEntry[]) => void
) => void;

const defaultLookupAll = dns.lookup as unknown as LookupAllFn;

/**
 * Resolve a hostname and reject it if ANY resolved address is private.
 * IP literals are classified directly (no DNS).
 */
export async function assertPublicHost(
  hostname: string,
  lookupAll: LookupAllFn = defaultLookupAll
): Promise<void> {
  if (net.isIP(hostname)) {
    if (isBlockedAddress(hostname)) {
      throw new OutboundError("blocked_host", `Blocked address: ${hostname}`);
    }
    return;
  }
  const all = await new Promise<LookupAllEntry[]>((resolve, reject) => {
    lookupAll(hostname, { all: true }, (err, addresses) => (err ? reject(err) : resolve(addresses)));
  }).catch((err: NodeJS.ErrnoException) => {
    throw new OutboundError("dns_failure", `DNS lookup failed for ${hostname}: ${err.code ?? err.message}`);
  });
  if (all.length === 0) {
    throw new OutboundError("dns_failure", `DNS lookup returned no addresses for ${hostname}`);
  }
  for (const entry of all) {
    if (isBlockedAddress(entry.address)) {
      throw new OutboundError("blocked_host", `Host ${hostname} resolves to blocked address`);
    }
  }
}

/**
 * Build a `lookup` function that revalidates every resolved address at connect
 * time. This closes the rebinding window: the address that passes validation is
 * the exact address the socket connects to, and TLS/SNI still uses the real
 * hostname (unlike the "replace URL with IP" approach).
 *
 * Node 20's happy-eyeballs (`autoSelectFamily`) calls `lookup` with
 * `{ all: true }` and expects an array back, so both shapes are honored.
 */
export function createPinnedLookup(lookupAll: LookupAllFn = defaultLookupAll): LookupFn {
  return (hostname, options, callback) => {
    lookupAll(hostname, { ...options, all: true }, (err, addresses) => {
      if (err) return callback(err, "", 4);
      const safe: LookupAllEntry[] = [];
      for (const entry of addresses) {
        if (isBlockedAddress(entry.address)) {
          const blocked: NodeJS.ErrnoException = new Error(`Blocked address for ${hostname}`);
          blocked.code = "EBLOCKEDHOST";
          return callback(blocked, "", entry.family);
        }
        safe.push(entry);
      }
      if (safe.length === 0) {
        const none: NodeJS.ErrnoException = new Error(`No address for ${hostname}`);
        none.code = "ENOTFOUND";
        return callback(none, "", 4);
      }
      if (options.all) {
        return callback(null, safe, safe[0].family);
      }
      return callback(null, safe[0].address, safe[0].family);
    });
  };
}

// ── Capped body reader ──────────────────────────────────────────────────────

export interface CappedBody {
  text: string;
  bytes: number;
  /**
   * The exact received bytes. Present only when the caller requested `binary`
   * — decoding binary payloads (e.g. a GDELT .zip) as UTF-8 replaces invalid
   * sequences with U+FFFD and destroys the data irreversibly.
   */
  buffer?: Buffer;
}

/**
 * Read an async-iterable body with a hard byte cap. Never use `res.text()` on
 * an untrusted response — this stops accumulating (and destroys the stream) the
 * moment the limit is exceeded.
 */
export async function readCappedBody(
  body: AsyncIterable<Uint8Array>,
  maxBytes: number = DEFAULT_MAX_BYTES,
  binary = false
): Promise<CappedBody> {
  const chunks: Buffer[] = [];
  let bytes = 0;
  for await (const chunk of body) {
    const buf = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    bytes += buf.byteLength;
    if (bytes > maxBytes) {
      const destroy = (body as { destroy?: () => void }).destroy;
      if (typeof destroy === "function") destroy.call(body);
      throw new OutboundError("too_large", `Response exceeded ${maxBytes} bytes`);
    }
    chunks.push(buf);
  }
  const concat = Buffer.concat(chunks);
  return binary
    ? { text: "", bytes, buffer: concat }
    : { text: concat.toString("utf8"), bytes };
}

// ── Safe GET ────────────────────────────────────────────────────────────────

export interface SafeGetOptions {
  url: string;
  headers?: Record<string, string>;
  timeoutMs?: number;
  maxBytes?: number;
  /** Preserve exact bytes (for binary payloads). `text` is then empty. */
  binary?: boolean;
  /**
   * Follow up to N redirects, re-validating EVERY hop through this same gate.
   * Default 0 (a 3xx is returned/rejected as-is). Only ever follows an https
   * `Location`; a redirect to a non-https scheme or a blocked address is refused.
   */
  maxRedirects?: number;
}

export interface SafeGetResult {
  status: number;
  contentType: string | null;
  text: string;
  /** Exact bytes, when the request set `binary: true`. */
  buffer?: Buffer;
  bytes: number;
  /**
   * Final URL. For `safeGet` this equals the request URL (redirects are never
   * followed); `safeGetFollowing` sets it to the last hop actually fetched.
   */
  url: string;
  /**
   * Response headers (lowercased keys). Used by the market adapters to read a
   * provider's REAL rate-limit/quota headers (`b-app-id`-style, Binance
   * `x-mbx-used-weight-1m`, `retry-after`, …) so pacing is measured against the
   * live limit. Additive; absent on older callers/tests.
   */
  headers?: Record<string, string>;
}

export interface SafeGetDeps {
  /** Injectable DNS resolver for tests. */
  lookupAll?: LookupAllFn;
  /** Injectable transport for tests. Defaults to node:https. */
  request?: typeof https.request;
}

/**
 * Perform a single, fully-guarded outbound GET.
 * - https only
 * - DNS resolved and validated, then pinned for the connection
 * - redirects NOT followed (a 3xx is returned to the caller as-is)
 * - strict timeout
 * - streamed response-size cap
 */
export async function safeGet(
  options: SafeGetOptions,
  deps: SafeGetDeps = {},
  _depth = 0
): Promise<SafeGetResult> {
  const check = validateOutboundUrl(options.url);
  if (!check.safe || !check.hostname) {
    throw new OutboundError(check.code ?? "invalid_url", check.reason ?? "Blocked URL");
  }
  const hostname = check.hostname;
  if (net.isIP(hostname)) {
    if (isBlockedAddress(hostname)) {
      throw new OutboundError("blocked_host", `Blocked address: ${hostname}`);
    }
  } else {
    await assertPublicHost(hostname, deps.lookupAll);
  }

  const timeoutMs = Math.min(options.timeoutMs ?? DEFAULT_TIMEOUT_MS, MAX_TIMEOUT_MS);
  const maxBytes = options.maxBytes ?? DEFAULT_MAX_BYTES;
  const request = deps.request ?? https.request;
  const parsed = new URL(options.url);
  const maxRedirects = Math.max(0, options.maxRedirects ?? 0);

  return new Promise<SafeGetResult>((resolve, reject) => {
    const reqOptions = {
      method: "GET",
      headers: { accept: "application/json, text/plain;q=0.9, */*;q=0.5", ...(options.headers ?? {}) },
      lookup: createPinnedLookup(deps.lookupAll) as unknown as https.RequestOptions["lookup"],
      signal: AbortSignal.timeout(timeoutMs),
    } as https.RequestOptions;

    const req = request(parsed, reqOptions, (res) => {
      const status = res.statusCode ?? 0;
      const contentType = (res.headers["content-type"] as string | undefined) ?? null;
      if (status >= 300 && status < 400) {
        res.destroy();
        const location = (res.headers["location"] as string | undefined) ?? "";
        if (maxRedirects > 0 && _depth < maxRedirects && location) {
          // Resolve the redirect target and REQUIRE https before recursing — the
          // recursive call re-runs validateOutboundUrl + the DNS-pinned lookup, so
          // a redirect to a private address / non-https scheme is rejected there.
          let next: string;
          try {
            next = new URL(location, options.url).toString();
          } catch {
            reject(new OutboundError("redirect", `Invalid redirect Location: ${location.slice(0, 80)}`));
            return;
          }
          if (!next.startsWith("https://")) {
            reject(new OutboundError("redirect", `Refusing redirect to non-https target`));
            return;
          }
          safeGet({ ...options, url: next }, deps, _depth + 1).then(resolve, reject);
          return;
        }
        reject(new OutboundError("redirect", `Redirect not followed (HTTP ${status})`));
        return;
      }
      readCappedBody(res as unknown as AsyncIterable<Uint8Array>, maxBytes, options.binary)
        .then((body) => resolve({
          status,
          contentType,
          text: body.text,
          buffer: body.buffer,
          bytes: body.bytes,
          url: options.url,
          headers: lowercasedHeaders(res.headers),
        }))
        .catch(reject);
    });
    req.on("error", (err: NodeJS.ErrnoException) => {
      if (err.name === "AbortError" || err.code === "ABORT_ERR") {
        reject(new OutboundError("timeout", `Request timed out after ${timeoutMs} ms`));
      } else if (err.code === "EBLOCKEDHOST") {
        reject(new OutboundError("blocked_host", err.message));
      } else {
        reject(new OutboundError("network", `Request failed for ${redactUrl(options.url)}: ${err.code ?? err.message}`));
      }
    });
    req.end();
  });
}

export const MAX_REDIRECTS = 5;

/** Flatten Node response headers into a lowercased string map (first value). */
function lowercasedHeaders(headers: import("node:http").IncomingHttpHeaders): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(headers)) {
    if (value === undefined) continue;
    out[key.toLowerCase()] = Array.isArray(value) ? value.join(", ") : String(value);
  }
  return out;
}
