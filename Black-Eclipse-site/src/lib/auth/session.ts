// SERVER-ONLY: request → AuthContext resolution.
//
// The token signing/verification lives in the Edge-safe `./token`; this module
// adds the DATABASE check (does the session still exist, is the user active?) and
// the injected-lookup resolver so it is unit-testable without a real database.
//
// `resolveAuthContext` is the ONE place a caller's identity is derived. A
// caller-supplied `userId` in a body is NEVER an identity — that is the tenancy
// boundary this feature closes.

import crypto from "node:crypto";
import { readCookie, verifySessionToken, AUTH_COOKIE } from "./token";
import type { AuthUser } from "./store";

export interface AuthContext {
  authenticated: boolean;
  user: AuthUser | null;
  /** The tenant scope this request may read/write. Caller-supplied labels are ignored. */
  scope: string | null;
  sessionId: string | null;
}

const ANONYMOUS: AuthContext = { authenticated: false, user: null, scope: null, sessionId: null };

type SessionLookup = (id: string) => { userId: string } | null;
type UserLookup = (id: string) => AuthUser | null;

/**
 * Resolve the request's identity. `lookupSession`/`lookupUser` are injected so
 * this pure function is testable without a database; the route layer passes the
 * real store.
 */
export async function resolveAuthContext(
  request: Request,
  deps: { lookupSession: SessionLookup; lookupUser: UserLookup }
): Promise<AuthContext> {
  const token = readCookie(request.headers.get("cookie"), AUTH_COOKIE);
  if (!token) return ANONYMOUS;
  const sessionId = await verifySessionToken(token);
  if (!sessionId) return ANONYMOUS;
  const session = deps.lookupSession(sessionId);
  if (!session) return ANONYMOUS;
  const user = deps.lookupUser(session.userId);
  if (!user || user.disabled) return ANONYMOUS;
  return { authenticated: true, user, scope: user.scope, sessionId };
}

/** A stable hash of the signed token, stored server-side for audit/rotation. */
export function tokenHash(token: string): string {
  return crypto.createHash("sha256").update(token).digest("hex");
}

/** Whether the request presents a token with a valid signature (no DB check). */
export async function hasSignedSession(request: Request): Promise<boolean> {
  const token = readCookie(request.headers.get("cookie"), AUTH_COOKIE);
  if (!token) return false;
  return (await verifySessionToken(token)) !== null;
}
