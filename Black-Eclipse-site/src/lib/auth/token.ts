// EDGE-SAFE: session token signing/verification and cookie helpers.
//
// This module is imported by BOTH the Edge middleware and Node route handlers,
// so it uses only `jose` (Web-Crypto backed) and the Web `Request`/`Response`
// APIs — never `node:crypto` and never the SQLite store. That is what lets the
// middleware gate the whole app with a signed cookie while the authoritative,
// DB-backed session check runs later in a Node route handler.

import { SignJWT, jwtVerify } from "jose";

export const AUTH_COOKIE = "eclipse_session";
export const AUTH_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7; // 7 days

function secretKey(): Uint8Array | null {
  const secret = process.env.HARNESS_AUTH_SECRET;
  if (!secret || secret === "change-me-to-a-random-secret" || secret.length < 16) return null;
  return new TextEncoder().encode(secret);
}

/** Whether a usable signing secret is configured. */
export function signingSecretConfigured(): boolean {
  return secretKey() !== null;
}

/** Sign a server-side session id into a compact JWT. */
export async function signSessionToken(sessionId: string): Promise<string> {
  const key = secretKey();
  if (!key) throw new Error("no signing secret");
  return await new SignJWT({ sid: sessionId })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(`${AUTH_SESSION_TTL_SECONDS}s`)
    .sign(key);
}

/** Verify a token and return its session id, or null (expired/forged/absent). */
export async function verifySessionToken(token: string): Promise<string | null> {
  const key = secretKey();
  if (!key) return null;
  try {
    const { payload } = await jwtVerify(token, key, { algorithms: ["HS256"] });
    return typeof payload.sid === "string" ? payload.sid : null;
  } catch {
    return null;
  }
}

/** Parse one cookie value out of a Cookie header. */
export function readCookie(cookieHeader: string | null, name: string = AUTH_COOKIE): string | null {
  if (!cookieHeader) return null;
  for (const part of cookieHeader.split(";")) {
    const idx = part.indexOf("=");
    if (idx === -1) continue;
    if (part.slice(0, idx).trim() === name) return decodeURIComponent(part.slice(idx + 1).trim());
  }
  return null;
}

/** The `Set-Cookie` value that starts a session. */
export function sessionCookie(token: string, opts: { secure: boolean }): string {
  const attrs = [
    `${AUTH_COOKIE}=${encodeURIComponent(token)}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
    `Max-Age=${AUTH_SESSION_TTL_SECONDS}`,
  ];
  if (opts.secure) attrs.push("Secure");
  return attrs.join("; ");
}

/** The `Set-Cookie` value that clears a session. */
export function clearedSessionCookie(): string {
  return `${AUTH_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`;
}
