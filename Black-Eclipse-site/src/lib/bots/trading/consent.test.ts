import { describe, expect, it } from "vitest";
import {
  CONSENT_TTL_MS,
  consentCovers,
  consentSignature,
  consentStatus,
  grantConsent,
  limitsFromEnvelope,
  needsPhrase,
  renewConsent,
  revokeConsent,
  tightenConsent,
} from "./consent";
import type { ConsentLimits, TradingConsent } from "./types";

const NOW = Date.parse("2026-11-17T10:00:00Z");

const limits: ConsentLimits = {
  symbols: ["EURUSD", "GBPUSD"],
  maxOrdersPerDay: 4,
  maxMarginPerOrder: 500,
  maxOpenPositions: 2,
};

function granted(patch: Partial<TradingConsent> = {}): TradingConsent {
  const result = grantConsent({
    modes: ["demo"],
    limits,
    phrase: "MANDATE DEMO MT5 demo",
    expectedPhrase: "MANDATE DEMO MT5 demo",
    now: NOW,
    autoRenew: true,
  });
  expect(result.error).toBeNull();
  return { ...result.consent!, ...patch };
}

describe("granting consent", () => {
  it("stores the scope, the proof phrase and an expiry", () => {
    const consent = granted();
    expect(consent.kind).toBe("standing");
    expect(consent.modes).toEqual(["demo"]);
    expect(consent.limits.symbols).toEqual(["EURUSD", "GBPUSD"]);
    expect(consent.expiresAt).toBe(
      new Date(NOW + CONSENT_TTL_MS.demo).toISOString(),
    );
    expect(consentStatus(consent, NOW)).toBe("active");
  });

  it("refuses a phrase that does not match exactly", () => {
    const result = grantConsent({
      modes: ["demo"],
      limits,
      phrase: "mandate demo mt5 demo",
      expectedPhrase: "MANDATE DEMO MT5 demo",
      now: NOW,
    });
    expect(result.consent).toBeNull();
    expect(result.error).toContain("MANDATE DEMO MT5 demo");
  });

  it("refuses a consent that covers no execution mode", () => {
    const result = grantConsent({
      modes: ["shadow"],
      limits,
      phrase: "x",
      expectedPhrase: "x",
      now: NOW,
    });
    expect(result.consent).toBeNull();
    expect(result.error).toMatch(/demo or live/i);
  });

  it("normalises an empty symbol list to a wildcard", () => {
    const result = grantConsent({
      modes: ["demo"],
      limits: { ...limits, symbols: [] },
      phrase: "MANDATE DEMO MT5 demo",
      expectedPhrase: "MANDATE DEMO MT5 demo",
      now: NOW,
    });
    expect(result.consent!.limits.symbols).toEqual(["*"]);
  });
});

describe("consent coverage", () => {
  const request = {
    mode: "demo" as const,
    symbols: ["EURUSD"],
    maxOrdersPerDay: 2,
    maxMarginPerOrder: 200,
    maxOpenPositions: 1,
  };

  it("covers a request inside every limit", () => {
    expect(consentCovers(granted(), request, NOW)).toEqual({
      covered: true,
      status: "active",
      reason: null,
      field: null,
    });
  });

  it("does not cover a mode the operator never authorized", () => {
    const check = consentCovers(granted(), { ...request, mode: "live" }, NOW);
    expect(check.covered).toBe(false);
    expect(check.reason).toMatch(/live/);
    expect(needsPhrase(granted(), { ...request, mode: "live" }, NOW)).toBe(true);
  });

  it("does not cover a symbol outside the grant", () => {
    const check = consentCovers(granted(), { ...request, symbols: ["USDJPY"] }, NOW);
    expect(check.covered).toBe(false);
    expect(check.field).toBe("symbols");
  });

  it("does not cover more orders than agreed", () => {
    const check = consentCovers(granted(), { ...request, maxOrdersPerDay: 9 }, NOW);
    expect(check.covered).toBe(false);
    expect(check.field).toBe("maxOrdersPerDay");
  });

  it("does not cover more margin or positions than agreed", () => {
    expect(
      consentCovers(granted(), { ...request, maxMarginPerOrder: 900 }, NOW).covered,
    ).toBe(false);
    expect(
      consentCovers(granted(), { ...request, maxOpenPositions: 3 }, NOW).covered,
    ).toBe(false);
  });

  it("a wildcard symbol grant covers anything", () => {
    const consent = granted({ limits: { ...limits, symbols: ["*"] } });
    expect(consentCovers(consent, { ...request, symbols: ["XAUUSD"] }, NOW).covered).toBe(
      true,
    );
  });

  it("shadow never needs a phrase", () => {
    expect(needsPhrase(null, { ...request, mode: "shadow" }, NOW)).toBe(false);
  });
});

describe("consent lifecycle", () => {
  it("expires exactly at its timestamp", () => {
    const consent = granted();
    const expires = Date.parse(consent.expiresAt!);
    expect(consentStatus(consent, expires - 1)).toBe("active");
    expect(consentStatus(consent, expires)).toBe("expired");
    expect(consentCovers(consent, {
      mode: "demo",
      symbols: ["EURUSD"],
      maxOrdersPerDay: 1,
      maxMarginPerOrder: 0,
      maxOpenPositions: 1,
    }, expires).covered).toBe(false);
  });

  it("a revoked consent is never covered and can never be renewed", () => {
    const revoked = revokeConsent(granted(), NOW)!;
    expect(consentStatus(revoked, NOW)).toBe("revoked");
    expect(renewConsent(revoked, NOW)).toBeNull();
  });

  it("renews only when auto-renew is on", () => {
    const consent = granted();
    const renewed = renewConsent(consent, NOW + 10 * 86_400_000)!;
    expect(Date.parse(renewed.expiresAt!)).toBeGreaterThan(
      Date.parse(consent.expiresAt!),
    );
    expect(renewConsent({ ...consent, autoRenew: false }, NOW)).toBeNull();
  });

  it("tightening can only shrink, never widen", () => {
    const consent = granted();
    const tighter = tightenConsent(consent, {
      maxOrdersPerDay: 1,
      maxMarginPerOrder: 100,
      maxOpenPositions: 1,
    });
    expect(tighter.limits.maxOrdersPerDay).toBe(1);
    expect(tighter.limits.maxOpenPositions).toBe(1);
    expect(tighter.limits.maxMarginPerOrder).toBe(100);

    const attemptedWiden = tightenConsent(consent, {
      maxOrdersPerDay: 20,
      maxMarginPerOrder: 5000,
      maxOpenPositions: 9,
    });
    expect(attemptedWiden.limits.maxOrdersPerDay).toBe(4);
    expect(attemptedWiden.limits.maxMarginPerOrder).toBe(500);
    expect(attemptedWiden.limits.maxOpenPositions).toBe(2);
  });

  it("the signature changes when the grant changes", () => {
    const a = consentSignature(granted());
    const b = consentSignature(granted({ grantedAt: new Date(NOW + 1).toISOString() }));
    expect(a).not.toBe(b);
    expect(consentSignature(null)).toBe("none");
  });

  it("builds limits from an envelope without inventing a wildcard", () => {
    expect(
      limitsFromEnvelope({
        symbols: ["eurusd", "EURUSD", "gbpusd"],
        maxOrdersPerDay: 99,
        maxMarginPerOrder: -5,
        maxOpenPositions: 0,
      }),
    ).toEqual({
      symbols: ["EURUSD", "GBPUSD"],
      maxOrdersPerDay: 20,
      maxMarginPerOrder: 0,
      maxOpenPositions: 1,
    });
  });
});
