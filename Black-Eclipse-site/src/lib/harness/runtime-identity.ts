// SERVER-ONLY: mint the short-lived identity token the Python runtime verifies.
//
// The Python runtime must never trust a caller-supplied `userId`/`tenantId`. The
// front door is the authenticator: it verifies the signed session, resolves the
// DB-backed user + tenant scope, and signs a 5-minute HS256 JWT with the SAME
// secret (`HARNESS_AUTH_SECRET`). Proxies forward it as `X-Harness-Identity`, and
// `python/harness/security/identity.py` verifies it. Do not import this module
// from a client component (it pulls the server-only auth store).

import { SignJWT } from "jose";
import { getAuthContext } from "@/lib/auth/server";

const IDENTITY_TTL = "5m";

function signingKey(): Uint8Array | null {
  const secret = process.env.HARNESS_AUTH_SECRET;
  if (!secret || secret === "change-me-to-a-random-secret" || secret.length < 16) return null;
  return new TextEncoder().encode(secret);
}

/**
 * The identity JWT for this request, or undefined when the caller is anonymous
 * (or auth is not configured). Never throws.
 */
export async function runtimeIdentityToken(request: Request): Promise<string | undefined> {
  const key = signingKey();
  if (!key) return undefined;
  try {
    const ctx = await getAuthContext(request);
    if (!ctx.authenticated || !ctx.user) return undefined;
    const payload: Record<string, unknown> = {
      sub: ctx.user.id,
      sid: ctx.sessionId,
      roles: ["user"],
    };
    // The tenant scope comes from the authenticated session, never the body.
    if (ctx.scope) payload.tenant = ctx.scope;
    return await new SignJWT(payload)
      .setProtectedHeader({ alg: "HS256" })
      .setIssuedAt()
      .setExpirationTime(IDENTITY_TTL)
      .sign(key);
  } catch {
    return undefined;
  }
}

/** The proxy header set for this request (empty when anonymous). */
export async function runtimeIdentityHeaders(request: Request): Promise<Record<string, string>> {
  const token = await runtimeIdentityToken(request);
  return token ? { "X-Harness-Identity": token } : {};
}
