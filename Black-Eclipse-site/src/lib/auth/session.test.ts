import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  signSessionToken,
  verifySessionToken,
  readCookie,
  sessionCookie,
  clearedSessionCookie,
  AUTH_COOKIE,
} from "@/lib/auth/token";
import { resolveAuthContext, hasSignedSession, tokenHash } from "@/lib/auth/session";
import type { AuthUser } from "@/lib/auth/store";

// Token signing/verification and the request→identity resolver.

const SECRET = "test-signing-secret-at-least-16-chars";
const saved = process.env.HARNESS_AUTH_SECRET;
beforeEach(() => {
  process.env.HARNESS_AUTH_SECRET = SECRET;
});
afterEach(() => {
  if (saved === undefined) delete process.env.HARNESS_AUTH_SECRET;
  else process.env.HARNESS_AUTH_SECRET = saved;
});

describe("session token", () => {
  it("round-trips a session id", async () => {
    const token = await signSessionToken("sess_123");
    expect(await verifySessionToken(token)).toBe("sess_123");
  });

  it("rejects a forged token", async () => {
    expect(await verifySessionToken("not.a.jwt")).toBeNull();
    // Signed with a different secret:
    process.env.HARNESS_AUTH_SECRET = "a-completely-different-secret-x";
    const other = await signSessionToken("sess_456");
    process.env.HARNESS_AUTH_SECRET = SECRET;
    expect(await verifySessionToken(other)).toBeNull();
  });

  it("refuses to sign without a secret", async () => {
    delete process.env.HARNESS_AUTH_SECRET;
    await expect(signSessionToken("x")).rejects.toThrow();
  });
});

describe("cookies", () => {
  it("reads a cookie value out of a header", () => {
    expect(readCookie(`foo=1; ${AUTH_COOKIE}=abc.def; bar=2`, AUTH_COOKIE)).toBe("abc.def");
    expect(readCookie(null, AUTH_COOKIE)).toBeNull();
    expect(readCookie("foo=1", AUTH_COOKIE)).toBeNull();
  });

  it("sets HttpOnly, SameSite, and Secure for non-loopback", () => {
    const c = sessionCookie("tok", { secure: true });
    expect(c).toContain("HttpOnly");
    expect(c).toContain("SameSite=Lax");
    expect(c).toContain("Secure");
    expect(sessionCookie("tok", { secure: false })).not.toContain("Secure");
  });

  it("clears the cookie", () => {
    expect(clearedSessionCookie()).toContain("Max-Age=0");
  });

  it("hashes a token deterministically", () => {
    expect(tokenHash("abc")).toBe(tokenHash("abc"));
    expect(tokenHash("abc")).not.toBe(tokenHash("abd"));
  });
});

describe("resolveAuthContext", () => {
  function reqWithCookie(token: string): Request {
    return new Request("http://localhost/api/x", { headers: { cookie: `${AUTH_COOKIE}=${encodeURIComponent(token)}` } });
  }
  const user: AuthUser = { id: "u1", username: "ada", scope: "tenant-a", createdAt: "x", disabled: false };

  it("returns anonymous without a cookie", async () => {
    const ctx = await resolveAuthContext(new Request("http://localhost/api/x"), {
      lookupSession: () => ({ userId: "u1" }),
      lookupUser: () => user,
    });
    expect(ctx.authenticated).toBe(false);
  });

  it("resolves an authenticated user from a valid session", async () => {
    const token = await signSessionToken("sess_1");
    const ctx = await resolveAuthContext(reqWithCookie(token), {
      lookupSession: (id) => (id === "sess_1" ? { userId: "u1" } : null),
      lookupUser: () => user,
    });
    expect(ctx.authenticated).toBe(true);
    expect(ctx.user?.username).toBe("ada");
    expect(ctx.scope).toBe("tenant-a");
  });

  it("treats a revoked (missing) session as anonymous", async () => {
    const token = await signSessionToken("sess_gone");
    const ctx = await resolveAuthContext(reqWithCookie(token), {
      lookupSession: () => null,
      lookupUser: () => user,
    });
    expect(ctx.authenticated).toBe(false);
  });

  it("treats a disabled user as anonymous", async () => {
    const token = await signSessionToken("sess_1");
    const ctx = await resolveAuthContext(reqWithCookie(token), {
      lookupSession: () => ({ userId: "u1" }),
      lookupUser: () => ({ ...user, disabled: true }),
    });
    expect(ctx.authenticated).toBe(false);
  });

  it("hasSignedSession checks only the signature", async () => {
    const token = await signSessionToken("sess_1");
    expect(await hasSignedSession(reqWithCookie(token))).toBe(true);
    expect(await hasSignedSession(new Request("http://localhost/api/x"))).toBe(false);
  });
});
