import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { AuthStore, setAuthStore } from "@/lib/auth/store";
import { loginHandler, logoutHandler, meHandler, setupHandler } from "@/lib/auth/handlers";
import { resolveScope } from "@/lib/auth/server";
import { resetAuthConfig } from "@/lib/auth/config";
import { AUTH_COOKIE } from "@/lib/auth/token";

// Auth endpoint behaviour + the tenancy rule (session scope is authoritative).

const SECRET = "test-signing-secret-at-least-16-chars";
let store: AuthStore | null = null;
const saved = { auth: process.env.HARNESS_AUTH, secret: process.env.HARNESS_AUTH_SECRET };

beforeEach(() => {
  resetAuthConfig();
  process.env.HARNESS_AUTH = "required";
  process.env.HARNESS_AUTH_SECRET = SECRET;
  store = new AuthStore(":memory:");
  setAuthStore(store);
});
afterEach(() => {
  setAuthStore(null);
  store?.close();
  store = null;
  resetAuthConfig();
  if (saved.auth === undefined) delete process.env.HARNESS_AUTH; else process.env.HARNESS_AUTH = saved.auth;
  if (saved.secret === undefined) delete process.env.HARNESS_AUTH_SECRET; else process.env.HARNESS_AUTH_SECRET = saved.secret;
});

function post(path: string, body: unknown): Request {
  return new Request(`http://localhost:3000${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", origin: "http://localhost:3000" },
    body: JSON.stringify(body),
  });
}

function cookieToken(res: Response): string {
  const setCookie = res.headers.get("set-cookie") || "";
  const match = setCookie.match(new RegExp(`${AUTH_COOKIE}=([^;]+)`));
  return match ? decodeURIComponent(match[1]) : "";
}

describe("setup + login + logout", () => {
  it("creates the first account, then closes setup", async () => {
    const created = await setupHandler(post("/api/auth/setup", { username: "ada", password: "password123" }));
    expect(created.status).toBe(200);
    const again = await setupHandler(post("/api/auth/setup", { username: "bob", password: "password123" }));
    expect(again.status).toBe(403);
    expect((await again.json()).code).toBe("AUTH_SETUP_CLOSED");
  });

  it("rejects a weak password on setup", async () => {
    const res = await setupHandler(post("/api/auth/setup", { username: "ada", password: "short" }));
    expect(res.status).toBe(400);
    expect((await res.json()).code).toBe("AUTH_WEAK_PASSWORD");
  });

  it("logs in with the right password and sets a session cookie", async () => {
    await setupHandler(post("/api/auth/setup", { username: "ada", password: "password123" }));
    const res = await loginHandler(post("/api/auth/login", { username: "ada", password: "password123" }));
    expect(res.status).toBe(200);
    expect(cookieToken(res)).not.toBe("");
    expect((await res.json()).user.username).toBe("ada");
  });

  it("refuses a wrong password with a generic message", async () => {
    await setupHandler(post("/api/auth/setup", { username: "ada", password: "password123" }));
    const res = await loginHandler(post("/api/auth/login", { username: "ada", password: "nope" }));
    expect(res.status).toBe(401);
    expect((await res.json()).code).toBe("AUTH_INVALID_CREDENTIALS");
  });

  it("clears the cookie on logout", async () => {
    const res = await logoutHandler(post("/api/auth/logout", {}));
    expect(res.status).toBe(200);
    expect(res.headers.get("set-cookie")).toContain("Max-Age=0");
  });

  it("reports auth state from /me and whether setup is required", async () => {
    const before = await meHandler(new Request("http://localhost/api/auth/me"));
    const bodyBefore = await before.json();
    expect(bodyBefore.authRequired).toBe(true);
    expect(bodyBefore.authenticated).toBe(false);
    expect(bodyBefore.setupRequired).toBe(true);

    await setupHandler(post("/api/auth/setup", { username: "ada", password: "password123" }));
    const after = await meHandler(new Request("http://localhost/api/auth/me"));
    expect((await after.json()).setupRequired).toBe(false);
  });

  it("does not mark the session cookie Secure for a local hostname alias", async () => {
    // Through `http://blackeclipse` (hosts-file alias to loopback, fronted by
    // scripts/local-proxy.js) the cookie is served over plain http. A Secure
    // cookie would be dropped by the browser and login would silently fail.
    await setupHandler(post("/api/auth/setup", { username: "ada", password: "password123" }));
    const local = await loginHandler(
      new Request("http://blackeclipse/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json", origin: "http://blackeclipse" },
        body: JSON.stringify({ username: "ada", password: "password123" }),
      })
    );
    expect(local.headers.get("set-cookie")).not.toContain("Secure");

    // A genuinely remote host still gets a Secure cookie.
    const remote = await loginHandler(
      new Request("https://eclipse.example.com/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json", origin: "https://eclipse.example.com" },
        body: JSON.stringify({ username: "ada", password: "password123" }),
      })
    );
    expect(remote.headers.get("set-cookie")).toContain("Secure");
  });
});

describe("tenancy: the session scope is authoritative", () => {
  it("ignores a caller-supplied scope when auth is required", async () => {
    await setupHandler(post("/api/auth/setup", { username: "ada", password: "password123" }));
    const login = await loginHandler(post("/api/auth/login", { username: "ada", password: "password123" }));
    const token = cookieToken(login);
    const request = new Request("http://localhost/api/x", {
      headers: { cookie: `${AUTH_COOKIE}=${encodeURIComponent(token)}` },
    });
    // A caller tries to widen scope via the body; the session scope wins.
    const scope = await resolveScope(request, "someone-elses-tenant");
    expect(scope).toBe("local"); // the user's real scope
  });

  it("passes the requested scope through unchanged when auth is off", async () => {
    process.env.HARNESS_AUTH = "off";
    resetAuthConfig();
    const scope = await resolveScope(new Request("http://localhost/api/x"), "caller-label");
    expect(scope).toBe("caller-label");
  });
});
