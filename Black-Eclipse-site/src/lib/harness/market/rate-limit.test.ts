import { describe, expect, it } from "vitest";
import { rateLimitFromHeaders } from "@/lib/harness/market/rate-limit";

describe("rateLimitFromHeaders", () => {
  it("reads Binance spot weight headers", () => {
    const rl = rateLimitFromHeaders("binance", { "x-mbx-used-weight-1m": "42" });
    expect(rl).toEqual({ limit: 1200, used: 42, remaining: 1158, windowSeconds: 60, retryAfterS: undefined });
  });

  it("reads Binance futures weight headers (higher limit)", () => {
    const rl = rateLimitFromHeaders("binance", { "x-mbx-used-weight-1m": "100" }, { futures: true });
    expect(rl?.limit).toBe(2400);
    expect(rl?.remaining).toBe(2300);
  });

  it("reads a Retry-After on a 429", () => {
    const rl = rateLimitFromHeaders("binance", { "retry-after": "12" });
    expect(rl?.retryAfterS).toBe(12);
  });

  it("reads generic x-ratelimit headers", () => {
    const rl = rateLimitFromHeaders("coingecko", { "x-ratelimit-limit": "30", "x-ratelimit-remaining": "7" });
    expect(rl).toEqual({ limit: 30, remaining: 7, used: 23, windowSeconds: undefined, retryAfterS: undefined });
  });

  it("returns undefined when no rate-limit headers exist", () => {
    expect(rateLimitFromHeaders("yahoo", { "content-type": "application/json" })).toBeUndefined();
    expect(rateLimitFromHeaders("yahoo", undefined)).toBeUndefined();
  });
});
