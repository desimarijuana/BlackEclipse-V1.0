// ── Inbound webhook proof ────────────────────────────────────────────────────
// Pure helpers shared by the public webhook route and its tests. The signature
// scheme matches the outbound `integration.webhook_send` node:
//
//   X-Eclipse-Signature: sha256=<hex HMAC-SHA256(secret, "<timestamp>.<rawBody>")>
//   X-Eclipse-Timestamp: <unix seconds>
//
// A token header (`X-Eclipse-Token`) is supported as an alternative for
// providers that cannot sign. The secret never appears in the URL by default.

import crypto from 'node:crypto';

export const SIGNATURE_HEADER = 'x-eclipse-signature';
export const TIMESTAMP_HEADER = 'x-eclipse-timestamp';
export const TOKEN_HEADER = 'x-eclipse-token';
export const DELIVERY_HEADER = 'x-eclipse-delivery';
export const DEFAULT_TOLERANCE_SEC = 300;

/** 32 random bytes, URL-safe. Shown once; only the encrypted cipher is stored. */
export function generateWebhookSecret(): string {
  return crypto.randomBytes(32).toString('base64url');
}

/** Random, non-secret URL path segment. */
export function generateWebhookSlug(): string {
  return crypto.randomBytes(18).toString('base64url');
}

/** Last 4 characters, for the UI only. */
export function secretHint(secret: string): string {
  return secret.slice(-4);
}

/** `sha256=<hex>` over `"<timestamp>.<body>"`. */
export function signWebhook(secret: string, timestamp: string, body: Buffer | string): string {
  const bytes = Buffer.isBuffer(body) ? body : Buffer.from(body, 'utf8');
  const mac = crypto.createHmac('sha256', secret);
  mac.update(timestamp, 'utf8');
  mac.update('.', 'utf8');
  mac.update(bytes);
  return `sha256=${mac.digest('hex')}`;
}

function safeEqual(a: string, b: string): boolean {
  const left = Buffer.from(a, 'utf8');
  const right = Buffer.from(b, 'utf8');
  if (left.length !== right.length) return false;
  return crypto.timingSafeEqual(left, right);
}

/** Null when the signature is valid; otherwise a short, non-leaky reason. */
export function verifyWebhookSignature(input: {
  secret: string;
  signature: string | null;
  timestamp: string | null;
  body: Buffer | string;
  nowMs?: number;
  toleranceSec?: number;
}): string | null {
  const signature = (input.signature ?? '').trim();
  const timestamp = (input.timestamp ?? '').trim();
  if (!signature || !timestamp) return 'missing signature or timestamp';
  if (!/^\d{1,12}$/.test(timestamp)) return 'invalid timestamp';
  const now = input.nowMs ?? Date.now();
  const tolerance = input.toleranceSec ?? DEFAULT_TOLERANCE_SEC;
  const age = Math.abs(now / 1000 - Number(timestamp));
  if (age > tolerance) return 'timestamp outside the replay window';
  if (!/^sha256=[0-9a-f]{64}$/.test(signature)) return 'invalid signature format';
  const expected = signWebhook(input.secret, timestamp, input.body);
  return safeEqual(signature, expected) ? null : 'signature mismatch';
}

/** Null when the token matches; otherwise a short reason. */
export function verifyWebhookToken(secret: string, token: string | null): string | null {
  if (!token) return 'missing token';
  return safeEqual(secret, token.trim()) ? null : 'token mismatch';
}

/** The caller's delivery id, or a stable body+timestamp digest as a fallback. */
export function deliveryIdOf(input: {
  headerValue: string | null;
  timestamp: string | null;
  body: Buffer | string;
}): string {
  const header = (input.headerValue ?? '').trim();
  if (header) return header.slice(0, 200);
  const bytes = Buffer.isBuffer(input.body) ? input.body : Buffer.from(input.body, 'utf8');
  return `body:${crypto.createHash('sha256').update(bytes).digest('hex').slice(0, 32)}:${(input.timestamp ?? '').slice(0, 12)}`;
}
