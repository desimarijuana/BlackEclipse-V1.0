// SERVER-ONLY: the auth facade used by Node route handlers.
//
// It wires the pure session resolver to the real `AuthStore` and exposes:
//   * `getAuthContext(request)`   — the request's identity (or anonymous).
//   * `requireApiAuth(request)`   — a Response when unauthenticated, else null.
//
// There is exactly ONE store and ONE cookie story; nothing else re-reads the
// session. The Edge middleware (`src/middleware.ts`) does the *coarse* gate (a
// validly signed cookie); THIS is the authoritative check that the session row
// still exists and the user is active, and it is where a route that needs a real
// identity must go.

import { authConfig, authMisconfigured } from "./config";
import { getAuthStore } from "./store";
import { resolveAuthContext, type AuthContext } from "./session";

export type { AuthContext } from "./session";
export { AUTH_COOKIE, AUTH_SESSION_TTL_SECONDS, authConfig, authMisconfigured, authRequired } from "./config";
export {
  signSessionToken,
  verifySessionToken,
  sessionCookie,
  clearedSessionCookie,
  signingSecretConfigured,
} from "./token";
export { tokenHash, hasSignedSession } from "./session";

/** Resolve this request's identity against the process store. */
export async function getAuthContext(request: Request): Promise<AuthContext> {
  const store = getAuthStore();
  return resolveAuthContext(request, {
    lookupSession: (id) => {
      const session = store.resolveSession(id);
      return session ? { userId: session.userId } : null;
    },
    lookupUser: (id) => store.getUserById(id),
  });
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/**
 * Resolve the tenant scope a request may act on.
 *
 * When authentication is REQUIRED, the scope comes from the authenticated
 * session and a caller-supplied value is IGNORED — a signed-in user cannot widen
 * their scope by putting a different `scopeId` in a body or query. When auth is
 * OFF (the zero-config single-user local case), the caller-supplied scope is
 * returned unchanged, exactly as before, so local behavior is unchanged.
 */
export async function resolveScope(
  request: Request,
  requestedScope: string | undefined
): Promise<string | undefined> {
  if (!authConfig().required) return requestedScope;
  const ctx = await getAuthContext(request);
  return ctx.scope ?? undefined;
}

/**
 * The authoritative API guard: enforce authentication when the deployment
 * requires it and the session is still live. Returns a ready-to-return
 * `Response`, or null when the request may proceed.
 *
 * Fails CLOSED when auth is required but no signing secret is configured.
 */
export async function requireApiAuth(request: Request): Promise<Response | null> {
  if (!authConfig().required) return null;
  if (authMisconfigured()) {
    return json(503, {
      error:
        "Authentication is required for this deployment but HARNESS_AUTH_SECRET is not set. " +
        "Set a random secret (>= 16 chars) and restart, or set HARNESS_AUTH=off for a trusted local-only run.",
      code: "AUTH_MISCONFIGURED",
    });
  }
  const ctx = await getAuthContext(request);
  if (ctx.authenticated) return null;
  return json(401, { error: "Sign in required", code: "AUTH_REQUIRED" });
}

/**
 * Broker surfaces are operator-only. When auth is off (local single user) this
 * is a no-op; when auth is on, an authenticated non-operator gets a 403. This is
 * the authoritative check; the middleware only proves the cookie signature.
 */
export async function requireOperatorApiAuth(request: Request): Promise<Response | null> {
  const denied = await requireApiAuth(request);
  if (denied) return denied;
  if (!authConfig().required) return null;
  const ctx = await getAuthContext(request);
  if (ctx.user?.role === "operator") return null;
  return json(403, { error: "Operator access required", code: "OPERATOR_REQUIRED" });
}
