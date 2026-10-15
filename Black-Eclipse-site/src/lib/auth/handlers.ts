// SERVER-ONLY: auth request handlers, shared by the thin route files under
// `src/app/api/auth/*`. Keeping the logic here means the four routes are one
// line each and the behavior is unit-testable without Next.

import { NextResponse } from "next/server";
import crypto from "node:crypto";
import { authConfig, AUTH_SESSION_TTL_SECONDS } from "./config";
import { getAuthStore } from "./store";
import { getAuthContext } from "./server";
import { signSessionToken, sessionCookie, clearedSessionCookie } from "./token";
import { tokenHash } from "./session";
import { guardMutation, isLocalRequest } from "@/lib/api-guard";

function bad(status: number, error: string, code: string) {
  return NextResponse.json({ error, code }, { status });
}

function secureFor(request: Request): boolean {
  // A Secure cookie is dropped by the browser over plain http. Any local host
  // (loopback aliases — and the `blackeclipse` hosts-file alias, which also
  // resolves to loopback) is served over http, so it must NOT be marked
  // Secure. Everything else is treated as remote and cookie-protected. The host
  // is read Host-aware (x-forwarded-host / host), not from `request.url`, so
  // this is correct behind the local reverse proxy too.
  return !isLocalRequest(request);
}

async function readCredentials(request: Request): Promise<{ username: string; password: string } | null> {
  try {
    const body = (await request.json()) as { username?: unknown; password?: unknown };
    const username = typeof body.username === "string" ? body.username : "";
    const password = typeof body.password === "string" ? body.password : "";
    if (!username || !password) return null;
    return { username, password };
  } catch {
    return null;
  }
}

export async function loginHandler(request: Request): Promise<Response> {
  const forbidden = guardMutation(request, "auth-login");
  if (forbidden) return NextResponse.json(forbidden.body, { status: forbidden.status });

  const creds = await readCredentials(request);
  if (!creds) return bad(400, "A username and password are required.", "AUTH_BAD_REQUEST");

  const store = getAuthStore();
  const user = store.authenticate(creds.username, creds.password);
  if (!user) {
    // Deliberately generic: never reveal whether the username exists.
    return bad(401, "Incorrect username or password.", "AUTH_INVALID_CREDENTIALS");
  }

  // Mint the session id first, sign a token bound to it, then persist the session
  // with a hash of that token. One row, one id — the token and the stored session
  // can never disagree.
  const sessionId = `sess_${crypto.randomUUID().replace(/-/g, "")}`;
  const token = await signSessionToken(sessionId);
  store.createSession(user.id, tokenHash(token), AUTH_SESSION_TTL_SECONDS, sessionId);

  const response = NextResponse.json({
    success: true,
    user: { id: user.id, username: user.username, scope: user.scope },
  });
  response.headers.append("Set-Cookie", sessionCookie(token, { secure: secureFor(request) }));
  return response;
}

export async function logoutHandler(request: Request): Promise<Response> {
  const forbidden = guardMutation(request, "auth-logout");
  if (forbidden) return NextResponse.json(forbidden.body, { status: forbidden.status });
  const ctx = await getAuthContext(request);
  if (ctx.sessionId) {
    try {
      getAuthStore().deleteSession(ctx.sessionId);
    } catch {
      /* best-effort */
    }
  }
  const response = NextResponse.json({ success: true });
  response.headers.append("Set-Cookie", clearedSessionCookie());
  return response;
}

export async function meHandler(request: Request): Promise<Response> {
  const cfg = authConfig();
  const ctx = await getAuthContext(request);
  let setupRequired = false;
  try {
    setupRequired = getAuthStore().userCount() === 0;
  } catch {
    setupRequired = false;
  }
  return NextResponse.json({
    authRequired: cfg.required,
    authenticated: ctx.authenticated,
    configured: cfg.secretConfigured || !cfg.required,
    setupRequired,
    user: ctx.user ? { id: ctx.user.id, username: ctx.user.username, scope: ctx.user.scope } : null,
  });
}

export async function setupHandler(request: Request): Promise<Response> {
  const forbidden = guardMutation(request, "auth-setup");
  if (forbidden) return NextResponse.json(forbidden.body, { status: forbidden.status });

  const store = getAuthStore();
  // First-run only: never let this endpoint add a second user on a live app.
  if (store.userCount() > 0) {
    return bad(403, "An account already exists. Sign in instead.", "AUTH_SETUP_CLOSED");
  }
  const creds = await readCredentials(request);
  if (!creds) return bad(400, "A username and password are required.", "AUTH_BAD_REQUEST");
  const username = creds.username.trim();
  if (username.length < 3 || username.length > 64) {
    return bad(400, "The username must be 3–64 characters.", "AUTH_BAD_USERNAME");
  }
  if (creds.password.length < 8) {
    return bad(400, "The password must be at least 8 characters.", "AUTH_WEAK_PASSWORD");
  }
  const user = store.createUser(username, creds.password, "local");
  return NextResponse.json({ success: true, user: { id: user.id, username: user.username, scope: user.scope } });
}
