import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { NextRequest } from "next/server";
import { middleware } from "@/middleware";
import { resetAuthConfig } from "@/lib/auth/config";
import { signSessionToken } from "@/lib/auth/token";

// The app-wide auth gate. With auth OFF it must never block anything (zero-config
// preserved). With auth ON it must 401 APIs, redirect pages, and let the login
// surface through.

const SECRET = "test-signing-secret-at-least-16-chars";
// `process.env` is typed immutable; the test needs to restore prior values, so it
// mutates an indexable view of the same object.
const env = process.env as Record<string, string | undefined>;
const saved = { auth: env.HARNESS_AUTH, secret: env.HARNESS_AUTH_SECRET };

beforeEach(() => {
  resetAuthConfig();
  env.HARNESS_AUTH = "required";
  env.HARNESS_AUTH_SECRET = SECRET;
});
afterEach(() => {
  resetAuthConfig();
  if (saved.auth === undefined) delete env.HARNESS_AUTH; else env.HARNESS_AUTH = saved.auth;
  if (saved.secret === undefined) delete env.HARNESS_AUTH_SECRET; else env.HARNESS_AUTH_SECRET = saved.secret;
});

function req(path: string, cookie?: string): NextRequest {
  return new NextRequest(`http://localhost:3000${path}`, {
    headers: cookie ? { cookie } : {},
  });
}

describe("middleware with auth OFF", () => {
  it("never blocks (zero-config local preserved)", async () => {
    env.HARNESS_AUTH = "off";
    resetAuthConfig();
    const res = await middleware(req("/api/settings"));
    // NextResponse.next() has no redirect; assert it is not a 401/redirect.
    expect(res.status).not.toBe(401);
    expect(res.headers.get("location")).toBeNull();
  });
});

describe("middleware with auth ON", () => {
  it("401s an API request with no session", async () => {
    const res = await middleware(req("/api/settings"));
    expect(res.status).toBe(401);
    expect((await res.json()).code).toBe("AUTH_REQUIRED");
  });

  it("redirects a page request to /login with the return path", async () => {
    const res = await middleware(req("/"));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/login");
  });

  it("lets the login page and auth endpoints through", async () => {
    for (const path of ["/login", "/api/auth/login", "/api/auth/me"]) {
      const res = await middleware(req(path));
      expect(res.status).not.toBe(401);
      expect(res.headers.get("location")).toBeNull();
    }
  });

  it("allows a request with a validly signed session cookie", async () => {
    const token = await signSessionToken("sess_1");
    const res = await middleware(req("/api/settings", `eclipse_session=${encodeURIComponent(token)}`));
    expect(res.status).not.toBe(401);
    expect(res.headers.get("location")).toBeNull();
  });

  it("rejects a forged cookie", async () => {
    const res = await middleware(req("/api/settings", "eclipse_session=forged.token.here"));
    expect(res.status).toBe(401);
  });

  it("fails closed with 503 when required but no secret is configured", async () => {
    delete env.HARNESS_AUTH_SECRET;
    resetAuthConfig();
    const res = await middleware(req("/api/settings"));
    expect(res.status).toBe(503);
    expect((await res.json()).code).toBe("AUTH_MISCONFIGURED");
  });
});

describe("canonical origin redirect", () => {
  const savedCanonical = env.BE_CANONICAL_HOST;
  afterEach(() => {
    if (savedCanonical === undefined) delete env.BE_CANONICAL_HOST; else env.BE_CANONICAL_HOST = savedCanonical;
  });

  it("redirects a non-canonical host, preserving path + query", async () => {
    env.BE_CANONICAL_HOST = "blackeclipse";
    const res = await middleware(req("/terminal?tab=1"));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://blackeclipse/terminal?tab=1");
  });

  it("does not redirect the canonical host", async () => {
    env.BE_CANONICAL_HOST = "blackeclipse";
    env.HARNESS_AUTH = "off";
    resetAuthConfig();
    const res = await middleware(new NextRequest("http://blackeclipse/terminal"));
    expect(res.headers.get("location")).toBeNull();
  });

  it("does not redirect when the forwarded host is canonical", async () => {
    env.BE_CANONICAL_HOST = "blackeclipse";
    env.HARNESS_AUTH = "off";
    resetAuthConfig();
    const res = await middleware(
      new NextRequest("http://127.0.0.1:3000/terminal", {
        headers: {
          host: "blackeclipse",
          "x-forwarded-host": "blackeclipse",
          "x-forwarded-proto": "https",
        },
      }),
    );
    expect(res.headers.get("location")).toBeNull();
  });

  it("redirects based on the Host header when nextUrl has the internal host", async () => {
    env.BE_CANONICAL_HOST = "blackeclipse";
    const res = await middleware(
      new NextRequest("http://127.0.0.1:3000/terminal", { headers: { host: "127.0.0.1:3000" } }),
    );
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://blackeclipse/terminal");
  });

  it("never redirects /api/* (loopback callers must keep working)", async () => {
    env.BE_CANONICAL_HOST = "blackeclipse";
    env.HARNESS_AUTH = "off";
    resetAuthConfig();
    const res = await middleware(req("/api/settings"));
    expect(res.headers.get("location")).toBeNull();
  });

  it("does nothing when BE_CANONICAL_HOST is unset", async () => {
    env.HARNESS_AUTH = "off";
    resetAuthConfig();
    const res = await middleware(req("/terminal"));
    expect(res.headers.get("location")).toBeNull();
  });
});
