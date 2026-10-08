import { describe, it, expect, beforeEach } from "vitest";
import {
  resolveAuthConfig,
  authConfig,
  authMisconfigured,
  resetAuthConfig,
} from "@/lib/auth/config";

// The auth MODE resolver. This is the crux of "zero-config must keep working":
// local dev must stay accountless, and the moment the app is reachable by another
// machine (or is a production build) it must require auth instead of silently
// being open.

beforeEach(() => resetAuthConfig());

describe("resolveAuthConfig", () => {
  it("is OFF by default on a local dev bind (zero-config preserved)", () => {
    const cfg = resolveAuthConfig({ NODE_ENV: "development" });
    expect(cfg.required).toBe(false);
    expect(cfg.source).toBe("auto-local");
  });

  it("is REQUIRED automatically on a non-loopback bind", () => {
    const cfg = resolveAuthConfig({ NODE_ENV: "development", HOST: "0.0.0.0" });
    expect(cfg.required).toBe(true);
    expect(cfg.source).toBe("auto-public");
  });

  it("does NOT treat localhost/127.0.0.1/::1 as public", () => {
    for (const host of ["localhost", "127.0.0.1", "::1", "[::1]"]) {
      expect(resolveAuthConfig({ NODE_ENV: "development", HOST: host }).required).toBe(false);
    }
  });

  it("is REQUIRED for a production build unless explicitly off", () => {
    expect(resolveAuthConfig({ NODE_ENV: "production" }).required).toBe(true);
    expect(resolveAuthConfig({ NODE_ENV: "production", HARNESS_AUTH: "off" }).required).toBe(false);
  });

  it("honours an explicit HARNESS_AUTH=required even on localhost", () => {
    const cfg = resolveAuthConfig({ NODE_ENV: "development", HARNESS_AUTH: "required" });
    expect(cfg.required).toBe(true);
    expect(cfg.source).toBe("explicit-on");
  });

  it("honours an explicit HARNESS_AUTH=off even on a public bind", () => {
    const cfg = resolveAuthConfig({ NODE_ENV: "production", HOST: "0.0.0.0", HARNESS_AUTH: "off" });
    expect(cfg.required).toBe(false);
    expect(cfg.source).toBe("explicit-off");
  });

  it("reports misconfiguration when required but no secret is set", () => {
    expect(authMisconfigured({ HARNESS_AUTH: "required" })).toBe(true);
    expect(authMisconfigured({ HARNESS_AUTH: "required", HARNESS_AUTH_SECRET: "short" })).toBe(true);
    expect(authMisconfigured({ HARNESS_AUTH: "required", HARNESS_AUTH_SECRET: "a-sufficiently-long-secret" })).toBe(false);
    // Not required => never "misconfigured".
    expect(authMisconfigured({ NODE_ENV: "development" })).toBe(false);
  });

  it("memoizes authConfig per process", () => {
    const a = authConfig({ NODE_ENV: "development" });
    expect(authConfig({ HARNESS_AUTH: "required" })).toBe(a); // memoized, ignores the 2nd arg
  });
});
