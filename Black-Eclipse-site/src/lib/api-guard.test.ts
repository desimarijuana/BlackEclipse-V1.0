import { describe, it, expect, beforeEach, vi } from "vitest";

// Use a stable window so rate-limit buckets behave predictably in tests.
const FIXED_NOW = 1_700_000_000_000;
vi.useFakeTimers();
vi.setSystemTime(FIXED_NOW);

import {
  checkMutationAllowed,
  checkOutboundUrl,
  deploymentExposure,
  rateLimit,
} from "./api-guard";

const req = (over: Partial<{ url: string; origin: string | null; auth: string }> = {}): Request =>
  new Request(over.url ?? "http://localhost:3000/api/refresh", {
    method: "POST",
    headers: over.origin === null ? {} : { origin: over.origin ?? "http://localhost:3000" },
  });

describe("checkMutationAllowed", () => {
  beforeEach(() => {
    vi.stubEnv("CRON_SECRET", "");
  });

  it("allows same-origin browser requests", () => {
    expect(checkMutationAllowed(req()).allowed).toBe(true);
  });

  it("rejects cross-origin requests", () => {
    const r = req({ origin: "https://evil.example" });
    expect(checkMutationAllowed(r).allowed).toBe(false);
  });

  it("rejects non-browser (no Origin) requests on a public host", () => {
    const r = req({ url: "https://terminal.example.com/api/refresh", origin: null });
    expect(checkMutationAllowed(r).allowed).toBe(false);
  });

  it("allows non-browser local requests", () => {
    const r = req({ origin: null });
    expect(checkMutationAllowed(r).allowed).toBe(true);
  });

  it("accepts the CRON_SECRET bearer token from anywhere", () => {
    vi.stubEnv("CRON_SECRET", "s3cret");
    const r = new Request("https://terminal.example.com/api/cron/run", {
      method: "POST",
      headers: { authorization: "Bearer s3cret" },
    });
    expect(checkMutationAllowed(r).allowed).toBe(true);
  });

  it("ignores the placeholder CRON_SECRET default", () => {
    vi.stubEnv("CRON_SECRET", "change-me-to-a-random-secret");
    const r = new Request("https://terminal.example.com/api/cron/run", {
      method: "POST",
      headers: {},
    });
    expect(checkMutationAllowed(r).allowed).toBe(false);
  });

  it("does NOT treat the 0.0.0.0 wildcard as a trusted local host", () => {
    const r = new Request("http://0.0.0.0:3000/api/refresh", { method: "POST", headers: {} });
    expect(checkMutationAllowed(r).allowed).toBe(false);
  });
});

describe("deploymentExposure", () => {
  it("never claims multi-user safety", () => {
    expect(deploymentExposure({ CRON_SECRET: "" }).multiUserSafe).toBe(false);
    expect(deploymentExposure({ CRON_SECRET: "real-secret" }).multiUserSafe).toBe(false);
  });

  it("flags production without a real secret", () => {
    const exposure = deploymentExposure({ NODE_ENV: "production", CRON_SECRET: "" });
    expect(exposure.exposed).toBe(true);
    expect(exposure.warning).toBeTruthy();
  });

  it("does not flag a configured secret", () => {
    const exposure = deploymentExposure({ NODE_ENV: "production", CRON_SECRET: "s3cret" });
    expect(exposure.exposed).toBe(false);
    expect(exposure.operatorSecretConfigured).toBe(true);
  });

  it("ignores the placeholder secret", () => {
    const exposure = deploymentExposure({
      NODE_ENV: "production",
      CRON_SECRET: "change-me-to-a-random-secret",
    });
    expect(exposure.operatorSecretConfigured).toBe(false);
    expect(exposure.exposed).toBe(true);
  });
});

describe("rateLimit", () => {
  it("allows up to the limit then blocks with retry-after", () => {
    const key = "test:a";
    for (let i = 0; i < 3; i++) {
      expect(rateLimit(key, { limit: 3, windowMs: 60_000 }).ok).toBe(true);
    }
    const blocked = rateLimit(key, { limit: 3, windowMs: 60_000 });
    expect(blocked.ok).toBe(false);
    expect(blocked.retryAfterSec).toBeGreaterThan(0);
  });

  it("resets after the window passes", () => {
    const key = "test:b";
    for (let i = 0; i < 2; i++) rateLimit(key, { limit: 2, windowMs: 60_000 });
    expect(rateLimit(key, { limit: 2, windowMs: 60_000 }).ok).toBe(false);
    vi.advanceTimersByTime(61_000);
    expect(rateLimit(key, { limit: 2, windowMs: 60_000 }).ok).toBe(true);
  });

  it("tracks keys independently", () => {
    expect(rateLimit("test:c1", { limit: 1, windowMs: 60_000 }).ok).toBe(true);
    expect(rateLimit("test:c1", { limit: 1, windowMs: 60_000 }).ok).toBe(false);
    expect(rateLimit("test:c2", { limit: 1, windowMs: 60_000 }).ok).toBe(true);
  });
});

describe("checkOutboundUrl", () => {
  it("allows public https URLs", () => {
    expect(checkOutboundUrl("https://www.cnbc.com/id/100003114/device/rss/rss.html").safe).toBe(true);
  });

  it("blocks non-http protocols", () => {
    expect(checkOutboundUrl("file:///etc/passwd").safe).toBe(false);
    expect(checkOutboundUrl("ftp://example.com/feed").safe).toBe(false);
  });

  it("blocks localhost and private ranges", () => {
    expect(checkOutboundUrl("http://localhost:11434/v1").safe).toBe(false);
    expect(checkOutboundUrl("http://127.0.0.1/x").safe).toBe(false);
    expect(checkOutboundUrl("http://10.0.0.5/x").safe).toBe(false);
    expect(checkOutboundUrl("http://192.168.1.10/x").safe).toBe(false);
    expect(checkOutboundUrl("http://169.254.169.254/latest/meta-data").safe).toBe(false);
    expect(checkOutboundUrl("http://myserver.internal/feed").safe).toBe(false);
  });

  it("blocks bare IP literals even when public", () => {
    expect(checkOutboundUrl("http://93.184.216.34/feed").safe).toBe(false);
  });

  it("blocks URLs with embedded credentials", () => {
    expect(checkOutboundUrl("https://user:pass@example.com/feed").safe).toBe(false);
  });

  it("blocks garbage", () => {
    expect(checkOutboundUrl("not a url").safe).toBe(false);
  });
});
