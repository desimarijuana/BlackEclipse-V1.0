import { describe, expect, it } from "vitest";
import {
  codeInfo,
  decisionNeedsAttention,
  decisionTone,
  explainDecision,
  formatDecisionLine,
  isLearnableFailure,
  isNoTrade,
} from "./decision";
import type { DecisionRecord } from "./types";

function decision(patch: Partial<DecisionRecord> = {}): DecisionRecord {
  return {
    botId: "aut_1",
    botVersion: 1,
    strategyId: "ema_trend",
    strategyVersion: "1.0.0",
    mode: "demo",
    tier: "l1",
    barTs: "2026-11-17T09:00:00Z",
    symbol: "EURUSD",
    signal: "long_entry",
    action: "buy",
    reason: "EMA(12) crossed above EMA(50)",
    indicators: { ema_fast: 1.0841, ema_slow: 1.0837 },
    risk: { allowed: true, quantity: 0.1, reasons: [] },
    outcome: "filled",
    code: null,
    orderId: "ord_1",
    orderStatus: "filled",
    warnings: [],
    ...patch,
  };
}

describe("refusal codes", () => {
  it("knows the catalogued codes", () => {
    const info = codeInfo("RISK_REFUSED");
    expect(info.severity).toBe("warning");
    expect(info.remedy).toMatch(/reduce size/i);
    expect(info.learnable).toBe(true);
  });

  it("shows an unknown code as an error instead of pretending it succeeded", () => {
    const info = codeInfo("SOMETHING_NEW");
    expect(info.severity).toBe("error");
    expect(info.label).toContain("SOMETHING_NEW");
    expect(info.learnable).toBe(false);
  });

  it("does not treat a missing code as fine", () => {
    expect(codeInfo(null).label).toMatch(/No code/);
  });

  it("marks normal no-trades as non-learnable", () => {
    expect(codeInfo("SESSION_CLOSED").learnable).toBe(true);
    expect(codeInfo("BAR_ALREADY_PROCESSED").learnable).toBe(false);
    expect(codeInfo("SHADOW").learnable).toBe(false);
  });
});

describe("decision rendering", () => {
  it("renders a filled entry with size", () => {
    expect(formatDecisionLine(decision())).toBe("EURUSD · BUY 0.1 · filled");
  });

  it("renders a refusal with its code", () => {
    expect(
      formatDecisionLine(
        decision({ outcome: "refused", action: "none", code: "RISK_REFUSED" }),
      ),
    ).toBe("EURUSD · — · refused · (RISK_REFUSED)");
  });

  it("explains a no-signal bar without pretending it traded", () => {
    const text = explainDecision(
      decision({
        outcome: "none",
        action: "none",
        signal: "none",
        reason: "no signal on the last closed bar",
      }),
    );
    expect(text).toContain("EURUSD");
    expect(text).toContain("no signal on the last closed bar");
    expect(text).not.toContain("BUY");
  });

  it("appends the remedy for a refusal", () => {
    const text = explainDecision(
      decision({ outcome: "refused", action: "none", code: "BROKER_UNAVAILABLE" }),
    );
    expect(text).toContain("broker");
    expect(text).toMatch(/terminal/i);
  });

  it("flags failed/refused/error decisions for attention", () => {
    expect(decisionNeedsAttention(decision())).toBe(false);
    expect(decisionNeedsAttention(decision({ outcome: "failed" }))).toBe(true);
    expect(
      decisionNeedsAttention(decision({ outcome: "skipped", code: "STRATEGY_UNAVAILABLE" })),
    ).toBe(true);
    expect(decisionNeedsAttention(decision({ outcome: "skipped", code: "SESSION_CLOSED" }))).toBe(
      false,
    );
  });

  it("paints a restrained tone per outcome", () => {
    expect(decisionTone(decision())).toBe("positive");
    expect(decisionTone(decision({ outcome: "placed" }))).toBe("positive");
    expect(decisionTone(decision({ outcome: "failed" }))).toBe("danger");
    expect(decisionTone(decision({ outcome: "refused", code: "RISK_REFUSED" }))).toBe(
      "warning",
    );
    expect(
      decisionTone(decision({ outcome: "refused", code: "STRATEGY_UNAVAILABLE" })),
    ).toBe("danger");
    expect(decisionTone(decision({ outcome: "skipped", code: "SESSION_CLOSED" }))).toBe(
      "info",
    );
    expect(decisionTone(decision({ outcome: "none", action: "none" }))).toBe("muted");
  });
});

describe("what counts as a failure", () => {
  it("counts a learnable skip but not a filled trade", () => {
    expect(isLearnableFailure({ outcome: "skipped", code: "STALE_MARKET_DATA" })).toBe(true);
    expect(isLearnableFailure({ outcome: "filled", code: null })).toBe(false);
    expect(isLearnableFailure({ outcome: "none", code: "SHADOW" })).toBe(false);
    expect(isLearnableFailure({ outcome: "refused", code: "APPROVAL_REQUIRED" })).toBe(false);
  });

  it("recognises an honest no-op", () => {
    expect(isNoTrade({ outcome: "none", action: "none" })).toBe(true);
    expect(isNoTrade({ outcome: "filled", action: "buy" })).toBe(false);
  });
});
