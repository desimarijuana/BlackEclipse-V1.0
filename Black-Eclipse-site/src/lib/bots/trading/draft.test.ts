import { describe, expect, it } from "vitest";
import {
  buildLearningPolicy,
  buildTradingAction,
  buildTradingAuthority,
  buildTradingConfig,
  consentLimitsFor,
  consentRequestFor,
  describeTradingDraft,
  draftFromTradingAction,
  emptyTradingDraft,
  expectedConsentPhrase,
  recommendedStartTier,
  validateTradingDraft,
  type TradingDraft,
} from "./draft";
import { grantConsent } from "./consent";
import { effectiveEnvelope } from "./validate";
import type { TradingConsent } from "./types";

const NOW = Date.parse("2026-11-17T10:00:00Z");

function draft(patch: Partial<TradingDraft> = {}): TradingDraft {
  return {
    ...emptyTradingDraft(),
    enabled: true,
    strategyId: "ema_trend",
    strategyVersion: "1.0.0",
    symbolsText: "EURUSD, GBPUSD",
    ...patch,
  };
}

function consentFor(patch: Partial<TradingDraft> = {}): TradingConsent {
  const source = draft(patch);
  const result = grantConsent({
    modes: ["demo"],
    limits: consentLimitsFor(source),
    phrase: "MANDATE DEMO MT5 demo",
    expectedPhrase: "MANDATE DEMO MT5 demo",
    now: NOW,
  });
  return result.consent!;
}

const context = {
  strategies: [
    { id: "ema_trend", version: "1.0.0", hasBacktest: true, approved: true },
  ],
  connections: [
    { id: "brk_demo", label: "MT5 demo", mode: "demo", symbols: ["EURUSD", "GBPUSD"] },
    {
      id: "brk_live",
      label: "MT5 live",
      mode: "live",
      armedUntil: "2026-11-17T12:00:00Z",
      symbols: ["EURUSD", "GBPUSD"],
    },
    { id: "brk_unarmed", label: "MT5 live 2", mode: "live", armedUntil: null },
  ],
  venueSymbols: ["EURUSD", "GBPUSD"],
  now: NOW,
};

describe("the default draft", () => {
  it("starts safe: disabled, shadow, L0, preview only, learning on", () => {
    const empty = emptyTradingDraft();
    expect(empty.enabled).toBe(false);
    expect(empty.mode).toBe("shadow");
    expect(empty.tier).toBe("l0");
    expect(empty.dryRun).toBe(true);
    expect(empty.learningEnabled).toBe(true);
    expect(empty.consent).toBeNull();
    expect(empty.visuals).toEqual([]);
  });

  it("builds a complete action payload", () => {
    const action = buildTradingAction(draft(), "trade the trend");
    expect(action.type).toBe("run_strategy");
    expect(action.objective).toBe("trade the trend");
    expect(action.config.strategyId).toBe("ema_trend");
    expect(action.config.symbols).toEqual(["EURUSD", "GBPUSD"]);
    expect(action.config.learning.enabled).toBe(true);
  });

  it("clamps unsafe numbers instead of trusting the form", () => {
    const config = buildTradingConfig(
      draft({ volume: -4, maxOrdersPerDay: 99, maxSymbols: 50, improveAfterFailures: 0 }),
    );
    expect(config.volume).toBe(0.01);
    expect(config.maxOrdersPerDay).toBe(20);
    expect(config.maxSymbols).toBe(8);
    expect(config.learning.threshold).toBe(2);

    const authority = buildTradingAuthority(
      draft({ maxOpenPositions: 0, cooldownS: -1, maxDailyLossPct: 99 }),
    );
    expect(authority.maxOpenPositions).toBe(1);
    expect(authority.cooldownS).toBe(0);
    expect(authority.maxDailyLossPct).toBe(50);
  });

  it("builds the learning policy from the draft", () => {
    const policy = buildLearningPolicy(draft({ improveAfterFailures: 5 }));
    expect(policy).toMatchObject({
      enabled: true,
      threshold: 5,
      tightenOnly: true,
      requireConsent: true,
    });
  });
});

describe("consent phrasing", () => {
  it("asks for the phrase the server computes", () => {
    expect(expectedConsentPhrase(draft({ mode: "demo" }), "MT5 demo")).toBe(
      "MANDATE DEMO MT5 demo",
    );
    expect(expectedConsentPhrase(draft({ mode: "live" }), "MT5 live")).toBe(
      "LIVE TRIAL ema_trend 1.0.0",
    );
    // An agent bot has no strategy trial; its grant is the mandate itself.
    expect(
      expectedConsentPhrase(draft({ mode: "live" }), "MT5 live", "agent"),
    ).toBe("MANDATE LIVE MT5 live");
    expect(
      expectedConsentPhrase(draft({ mode: "demo" }), "MT5 demo", "agent"),
    ).toBe("MANDATE DEMO MT5 demo");
  });

  it("derives the consent request from the envelope", () => {
    expect(consentRequestFor(draft({ maxOrdersPerDay: 3 }))).toEqual({
      mode: "shadow",
      symbols: ["EURUSD", "GBPUSD"],
      maxOrdersPerDay: 3,
      maxMarginPerOrder: 0,
      maxOpenPositions: 1,
    });
  });

  it("recommends L0 for shadow and never live on day one", () => {
    expect(recommendedStartTier(draft({ mode: "shadow" }))).toBe("l0");
    // A demo bot is already on the demo rung; its leash still starts at L1.
    expect(recommendedStartTier(draft({ mode: "demo" }), 0)).toBe("l1");
    expect(recommendedStartTier(draft({ mode: "live" }), 100)).toBe("l1");
  });
});

describe("validation", () => {
  it("accepts a complete shadow setup", () => {
    const { issues, blocked } = validateTradingDraft(draft(), context, null);
    expect(issues.filter((i) => i.severity === "error")).toEqual([]);
    expect(blocked).toBe(false);
  });

  it("requires a strategy, a version and a symbol", () => {
    const { issues } = validateTradingDraft(
      draft({ strategyId: "", strategyVersion: "", symbolsText: "" }),
      context,
      null,
    );
    const codes = issues.map((i) => i.code);
    expect(codes).toContain("STRATEGY_ID_REQUIRED");
    expect(codes).toContain("STRATEGY_VERSION_REQUIRED");
    expect(codes).toContain("SYMBOLS_REQUIRED");
  });

  it("refuses a strategy that is not on the machine", () => {
    const { issues } = validateTradingDraft(
      draft({ strategyId: "missing" }),
      context,
      null,
    );
    expect(issues.map((i) => i.code)).toContain("STRATEGY_UNAVAILABLE");
  });

  it("needs consent before a demo bot may fill", () => {
    const { issues } = validateTradingDraft(
      draft({ mode: "demo", connectionId: "brk_demo", dryRun: false, tier: "l1" }),
      context,
      null,
    );
    expect(issues.map((i) => i.code)).toContain("CONSENT_REQUIRED");
  });

  it("accepts a demo bot with a covering standing consent", () => {
    const demo = draft({
      mode: "demo",
      connectionId: "brk_demo",
      dryRun: false,
      tier: "l1",
    });
    const consent = consentFor(demo);
    const { issues } = validateTradingDraft(demo, context, consent);
    expect(issues.filter((i) => i.severity === "error")).toEqual([]);
  });

  it("refuses a mode that disagrees with the connection", () => {
    const { issues } = validateTradingDraft(
      draft({ mode: "demo", connectionId: "brk_live", dryRun: true, tier: "l1" }),
      context,
      null,
    );
    expect(issues.map((i) => i.code)).toContain("MODE_MISMATCH");
  });

  it("refuses live without an arm or L2", () => {
    const base = draft({ mode: "live", connectionId: "brk_unarmed", tier: "l1", dryRun: false });
    const { issues } = validateTradingDraft(base, context, consentFor(base));
    const codes = issues.map((i) => i.code);
    expect(codes).toContain("LIVE_NOT_ARMED");
    expect(codes).toContain("BOT_TIER_REQUIRED");
  });

  it("refuses a symbol the venue does not offer", () => {
    const { issues } = validateTradingDraft(
      draft({
        mode: "demo",
        connectionId: "brk_demo",
        symbolsText: "EURUSD, USDJPY",
        tier: "l1",
        dryRun: true,
      }),
      context,
      null,
    );
    const issue = issues.find((i) => i.code === "SYMBOL_NOT_TRADABLE");
    expect(issue?.message).toContain("USDJPY");
  });

  it("enforces the appetite band and the stop requirement", () => {
    const { issues } = validateTradingDraft(
      draft({ maxOrdersPerDay: 9, appetite: "conservative", stopLossPoints: 0 }),
      context,
      null,
    );
    const codes = issues.map((i) => i.code);
    expect(codes).toContain("ORDERS_ABOVE_BAND");
    expect(codes).toContain("STOP_REQUIRED");
  });

  it("warns (not blocks) on a missing backtest", () => {
    const { issues, blocked } = validateTradingDraft(draft(), {
      ...context,
      strategies: [{ id: "ema_trend", version: "1.0.0", hasBacktest: false }],
    }, null);
    expect(issues.find((i) => i.code === "STRATEGY_NO_BACKTEST")?.severity).toBe("warning");
    expect(blocked).toBe(false);
  });

  it("reports the effective envelope as the strictest of the layers", () => {
    const config = buildTradingConfig(draft({ maxOrdersPerDay: 8 }), consentFor());
    const authority = buildTradingAuthority(draft({ maxOpenPositions: 2 }));
    const envelope = effectiveEnvelope(config, authority);
    expect(envelope.maxOrdersPerDay).toBe(2); // conservative band
    expect(envelope.maxPositions).toBe(1); // band caps at 1
    expect(envelope.riskPerTradePct).toBe(0.25);
    expect(envelope.requireStop).toBe(true);
  });
});

describe("reading a stored bot back", () => {
  it("round-trips a saved trading action", () => {
    const original = draft({
      mode: "demo",
      connectionId: "brk_demo",
      tier: "l1",
      dryRun: false,
      maxOpenPositions: 2,
      appetite: "normal",
      excludedText: "USDJPY",
      sessionEnabled: true,
      sessionStart: "07:00",
      sessionEnd: "19:00",
    });
    const config = buildTradingConfig(original, consentFor(original));
    const authority = buildTradingAuthority(original);
    const reopened = draftFromTradingAction(config, authority);

    expect(reopened.enabled).toBe(true);
    expect(reopened.mode).toBe("demo");
    expect(reopened.connectionId).toBe("brk_demo");
    expect(reopened.tier).toBe("l1");
    expect(reopened.appetite).toBe("normal");
    expect(reopened.maxOpenPositions).toBe(2);
    expect(reopened.excludedText).toBe("USDJPY");
    expect(reopened.sessionEnabled).toBe(true);
    expect(reopened.sessionStart).toBe("07:00");
    expect(reopened.consent?.kind).toBe("standing");
  });

  it("survives a malformed stored action", () => {
    const reopened = draftFromTradingAction({ symbols: "oops" }, "oops");
    expect(reopened.mode).toBe("shadow");
    expect(reopened.tier).toBe("l0");
    expect(reopened.symbolsText).toBe("");
  });

  it("describes the bot in one line", () => {
    expect(describeTradingDraft(draft())).toEqual({
      mode: "shadow",
      tier: "l0",
      universe: "EURUSD, GBPUSD",
      risk: "conservative",
      orders: "2/day",
    });
  });
});
