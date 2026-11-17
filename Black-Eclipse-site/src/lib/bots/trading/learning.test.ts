import { describe, expect, it } from "vitest";
import {
  acceptProposal,
  analyzeFailures,
  applyProposal,
  autoApplicable,
  buildProposal,
  learningDigest,
  learningSummary,
  markProposed,
  proposeImprovements,
} from "./learning";
import type {
  DecisionRecord,
  ImprovementProposal,
  LearningPolicy,
  TradingAuthority,
  TradingConfig,
} from "./types";

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
    action: "none",
    reason: "order refused",
    indicators: {},
    risk: null,
    outcome: "refused",
    code: "RISK_REFUSED",
    orderId: null,
    orderStatus: null,
    warnings: [],
    ...patch,
  };
}

function config(patch: Partial<TradingConfig> = {}): TradingConfig {
  return {
    strategyId: "ema_trend",
    strategyVersion: "1.0.0",
    mode: "demo",
    connectionId: "brk_1",
    symbols: ["EURUSD"],
    excludedSymbols: [],
    dynamicSymbols: false,
    maxSymbols: 4,
    timeframe: "H1",
    volume: 0.1,
    stopLossPoints: 150,
    takeProfitPoints: 300,
    maxOrdersPerDay: 4,
    session: null,
    trialId: "live_1",
    dryRun: false,
    consent: null,
    visuals: [],
    learning: policy(),
    ...patch,
  };
}

function authority(patch: Partial<TradingAuthority> = {}): TradingAuthority {
  return {
    tier: "l1",
    appetite: "conservative",
    sizingMode: "risk_based",
    requireStop: true,
    maxOpenPositions: 1,
    maxMarginPerOrder: 500,
    cooldownS: 900,
    maxDailyLossPct: 3,
    autoMode: true,
    autoRenew: true,
    learningEnabled: true,
    improveAfterFailures: 3,
    ...patch,
  };
}

function policy(patch: Partial<LearningPolicy> = {}): LearningPolicy {
  return {
    enabled: true,
    threshold: 3,
    tightenOnly: true,
    requireConsent: true,
    lastAcceptedAt: null,
    lastProposedAt: null,
    proposed: [],
    ...patch,
  };
}

function repeats(code: string, count: number, patch: Partial<DecisionRecord> = {}) {
  return Array.from({ length: count }, (_, i) =>
    decision({
      code,
      barTs: new Date(Date.parse("2026-11-17T09:00:00Z") + i * 3_600_000).toISOString(),
      ...patch,
    }),
  );
}

describe("finding patterns", () => {
  it("needs the threshold before it reports anything", () => {
    expect(analyzeFailures(repeats("RISK_REFUSED", 2))).toEqual([]);
    const patterns = analyzeFailures(repeats("RISK_REFUSED", 3));
    expect(patterns).toHaveLength(1);
    expect(patterns[0]).toMatchObject({ code: "RISK_REFUSED", count: 3 });
    expect(patterns[0].samples).toHaveLength(3);
  });

  it("ignores filled trades and non-learnable outcomes", () => {
    const rows = [
      ...repeats("RISK_REFUSED", 3),
      decision({ outcome: "filled", code: null, action: "buy" }),
      ...repeats("APPROVAL_REQUIRED", 5),
    ];
    const patterns = analyzeFailures(rows);
    expect(patterns.map((item) => item.code)).toEqual(["RISK_REFUSED"]);
  });

  it("only looks inside the window", () => {
    const old = repeats("RISK_REFUSED", 5).map((row, i) => ({
      ...row,
      barTs: new Date(Date.parse("2026-01-01T00:00:00Z") + i * 60_000).toISOString(),
    }));
    const recent = repeats("STALE_MARKET_DATA", 3, { outcome: "skipped" });
    const patterns = analyzeFailures([...old, ...recent], { window: 5 });
    expect(patterns.map((item) => item.code)).toEqual(["STALE_MARKET_DATA"]);
  });

  it("sorts the loudest pattern first", () => {
    const patterns = analyzeFailures([
      ...repeats("STALE_MARKET_DATA", 3, { outcome: "skipped" }),
      ...repeats("RISK_REFUSED", 5),
    ]);
    expect(patterns[0].code).toBe("RISK_REFUSED");
  });
});

describe("proposals", () => {
  it("halves size for a risk refusal and speaks in the first person", () => {
    const pattern = analyzeFailures(repeats("RISK_REFUSED", 3))[0];
    const proposal = buildProposal(pattern, { config: config(), authority: authority() });
    expect(proposal.kind).toBe("tighten");
    expect(proposal.changes.volume).toBe(0.05);
    expect(proposal.riskDelta).toBe("lower");
    expect(proposal.autoApplicable).toBe(true);
    expect(proposal.message).toMatch(/want me to apply|shall/i);
    expect(proposal.id).toContain("RISK_REFUSED");
  });

  it("never asks to raise the position cap without flagging the risk", () => {
    const pattern = analyzeFailures(repeats("POSITION_ALREADY_OPEN", 3))[0];
    const proposal = buildProposal(pattern, {
      config: config(),
      authority: authority({ appetite: "normal", maxOpenPositions: 1 }),
    });
    expect(proposal.riskDelta).toBe("higher");
    expect(proposal.autoApplicable).toBe(false);
    expect(proposal.authorityChanges.maxOpenPositions).toBe(2);
  });

  it("suggests a cooldown instead when the band is already at its cap", () => {
    const pattern = analyzeFailures(repeats("POSITION_CAP_REACHED", 3))[0];
    const proposal = buildProposal(pattern, {
      config: config(),
      authority: authority({ appetite: "conservative", maxOpenPositions: 1 }),
    });
    expect(proposal.riskDelta).toBe("lower");
    expect(proposal.autoApplicable).toBe(true);
    expect(proposal.authorityChanges.cooldownS).toBe(1800);
  });

  it("drops an untradable symbol and is safe to apply", () => {
    const pattern = analyzeFailures(
      repeats("SYMBOL_NOT_TRADABLE", 3, { outcome: "skipped" }),
    )[0];
    const proposal = buildProposal(pattern, { config: config(), authority: authority() });
    expect(proposal.changes.excludedSymbols).toContain("EURUSD");
    expect(proposal.autoApplicable).toBe(true);
  });

  it("steps the appetite down after repeated daily-loss brakes", () => {
    const pattern = analyzeFailures(
      repeats("DAILY_LOSS_LIMIT", 4, { outcome: "skipped" }),
    )[0];
    const proposal = buildProposal(pattern, { config: config(), authority: authority() });
    expect(proposal.authorityChanges.appetite).toBe("conservative");
    expect(proposal.authorityChanges.maxDailyLossPct).toBeLessThan(3);
    expect(proposal.autoApplicable).toBe(true);
  });

  it("proposes a slower timeframe for a stale feed", () => {
    const pattern = analyzeFailures(
      repeats("STALE_MARKET_DATA", 3, { outcome: "skipped" }),
    )[0];
    const proposal = buildProposal(pattern, { config: config(), authority: authority() });
    expect(proposal.changes.timeframe).toBe("H4");
    expect(proposal.riskDelta).toBe("lower");
  });

  it("switches to preview-only when the broker is unreachable", () => {
    const pattern = analyzeFailures(
      repeats("BROKER_UNAVAILABLE", 3, { outcome: "failed" }),
    )[0];
    const proposal = buildProposal(pattern, { config: config(), authority: authority() });
    expect(proposal.kind).toBe("pause");
    expect(proposal.changes.dryRun).toBe(true);
    expect(proposal.authorityChanges.autoRenew).toBe(false);
  });

  it("offers a conversation, not a change, for an unknown code", () => {
    const pattern = analyzeFailures(
      repeats("WEIRD_NEW_CODE", 3, { outcome: "skipped" }),
    )[0];
    const proposal = buildProposal(pattern, { config: config(), authority: authority() });
    expect(proposal.changes).toEqual({});
    expect(proposal.autoApplicable).toBe(false);
    expect(proposal.message).toMatch(/together/i);
  });
});

describe("applying a proposal", () => {
  it("applies a tightening proposal", () => {
    const pattern = analyzeFailures(repeats("RISK_REFUSED", 3))[0];
    const proposal = buildProposal(pattern, { config: config(), authority: authority() });
    const result = applyProposal(config(), authority(), proposal);
    expect(result.config.volume).toBe(0.05);
    expect(result.applied).toContain("volume");
  });

  it("refuses to widen risk without the operator's approval", () => {
    const pattern = analyzeFailures(repeats("POSITION_ALREADY_OPEN", 3))[0];
    const proposal = buildProposal(pattern, {
      config: config(),
      authority: authority({ appetite: "normal", maxOpenPositions: 1 }),
    });
    const refused = applyProposal(config(), authority({ appetite: "normal", maxOpenPositions: 1 }), proposal);
    expect(refused.applied).toEqual([]);
    expect(refused.authority.maxOpenPositions).toBe(1);

    const approved = applyProposal(
      config(),
      authority({ appetite: "normal", maxOpenPositions: 1 }),
      proposal,
      true,
    );
    expect(approved.authority.maxOpenPositions).toBe(2);
  });

  it("clamps even a hand-edited proposal to the band", () => {
    const rogue: ImprovementProposal = {
      id: "x",
      code: "RISK_REFUSED",
      kind: "tighten",
      title: "rogue",
      rationale: "",
      message: "",
      changes: { volume: 99_999, maxOrdersPerDay: 99 },
      authorityChanges: { maxOpenPositions: 50, cooldownS: 999_999 },
      riskDelta: "lower",
      autoApplicable: true,
    };
    const result = applyProposal(config(), authority(), rogue);
    expect(result.config.volume).toBe(1000);
    expect(result.config.maxOrdersPerDay).toBe(2); // conservative band
    expect(result.authority.maxOpenPositions).toBe(1);
    expect(result.authority.cooldownS).toBe(86_400);
  });
});

describe("learning bookkeeping", () => {
  it("only auto-applies strictly risk-reducing proposals", () => {
    const patterns = analyzeFailures([
      ...repeats("RISK_REFUSED", 3),
      ...repeats("POSITION_ALREADY_OPEN", 3),
    ]);
    const proposals = proposeImprovements(patterns, {
      config: config(),
      authority: authority({ appetite: "normal", maxOpenPositions: 1 }),
    });
    expect(autoApplicable(proposals).map((item) => item.code)).toEqual(["RISK_REFUSED"]);
  });

  it("remembers proposals so the bot does not nag", () => {
    const patterns = analyzeFailures(repeats("RISK_REFUSED", 3));
    const proposals = proposeImprovements(patterns, {
      config: config(),
      authority: authority(),
    });
    const marked = markProposed(policy(), proposals, Date.parse("2026-11-17T10:00:00Z"));
    expect(marked.proposed).toEqual([proposals[0].id]);
    expect(marked.lastProposedAt).toBe("2026-11-17T10:00:00.000Z");
    const again = markProposed(marked, proposals, Date.parse("2026-11-17T11:00:00Z"));
    expect(again.proposed).toHaveLength(1);
  });

  it("records acceptance with a timestamp", () => {
    const patterns = analyzeFailures(repeats("RISK_REFUSED", 3));
    const proposal = proposeImprovements(patterns, {
      config: config(),
      authority: authority(),
    })[0];
    const accepted = acceptProposal(policy(), proposal, Date.parse("2026-11-17T10:00:00Z"));
    expect(accepted.lastAcceptedAt).toBe("2026-11-17T10:00:00.000Z");
    expect(accepted.proposed).toContain(proposal.id);
  });

  it("writes a digest that asks before changing anything", () => {
    const patterns = analyzeFailures(repeats("RISK_REFUSED", 3));
    const proposals = proposeImprovements(patterns, {
      config: config(),
      authority: authority(),
    });
    const digest = learningDigest(patterns, proposals)!;
    expect(digest).toContain("Nothing changes until you say yes.");
    expect(digest).toMatch(/RISK_REFUSED|risk/i);
    expect(learningDigest([], [])).toBeNull();
  });

  it("summarises health honestly", () => {
    expect(learningSummary([], policy())).toMatch(/nothing to learn/i);
    expect(learningSummary([], policy({ enabled: false }))).toMatch(/off/i);
    expect(
      learningSummary(analyzeFailures(repeats("RISK_REFUSED", 3)), policy()),
    ).toContain("RISK_REFUSED×3");
  });
});
