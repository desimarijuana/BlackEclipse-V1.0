// ── Failure-driven improvement ─────────────────────────────────────────────
// A bot that keeps failing the same way is not "working"; it has a lesson to
// learn. This module turns repeated decision failures into ONE concrete change,
// explains it to the operator in chat, and applies it only with consent.
//
// Two rules keep it safe:
//   * a proposal may never widen risk without the operator explicitly agreeing;
//   * strictly risk-reducing proposals are marked `autoApplicable`, but are still
//     surfaced in the conversation — the bot reports what it intends to do.
//
// The output is plain data, so the same proposal object drives the chat card,
// the detail panel and the config patch.

import { explainDecision, isLearnableFailure, codeInfo } from "./decision";
import {
  APPETITE_BANDS,
  MAX_MAX_ORDERS_PER_DAY,
  MIN_MAX_ORDERS_PER_DAY,
  TIMEFRAME_MS,
} from "./types";
import type {
  DecisionRecord,
  FailurePattern,
  ImprovementProposal,
  LearningPolicy,
  RiskAppetite,
  TradingAuthority,
  TradingConfig,
} from "./types";

const DEFAULT_THRESHOLD = 3;
const DEFAULT_WINDOW = 60;
const SLOWER: Record<string, string> = {
  M1: "M5",
  M5: "M15",
  M15: "M30",
  M30: "H1",
  H1: "H4",
  H4: "D1",
  D1: "W1",
};

function iso(value: string | null | undefined): string {
  if (!value) return "";
  const t = new Date(value).getTime();
  return Number.isFinite(t) ? new Date(t).toISOString() : "";
}

/**
 * Group learnable failures by code over the last `window` decisions. A pattern is
 * returned only once it reaches `threshold`, so a single bad bar does not nag.
 */
export function analyzeFailures(
  decisions: readonly DecisionRecord[],
  options: { threshold?: number; window?: number } = {},
): FailurePattern[] {
  const threshold = Math.max(2, options.threshold ?? DEFAULT_THRESHOLD);
  const window = Math.max(5, options.window ?? DEFAULT_WINDOW);
  const recent = decisions.slice(-window).filter(isLearnableFailure);

  const groups = new Map<string, DecisionRecord[]>();
  for (const decision of recent) {
    const code = decision.code ?? "UNKNOWN";
    const list = groups.get(code) ?? [];
    list.push(decision);
    groups.set(code, list);
  }

  const patterns: FailurePattern[] = [];
  for (const [code, rows] of groups) {
    if (rows.length < threshold) continue;
    const times = rows
      .map((row) => iso(row.barTs))
      .filter(Boolean)
      .sort();
    patterns.push({
      code,
      count: rows.length,
      firstAt: times[0] ?? "",
      lastAt: times[times.length - 1] ?? "",
      samples: rows.slice(-3).map((row) => explainDecision(row)),
    });
  }
  return patterns.sort((a, b) => b.count - a.count);
}

function slowerTimeframe(timeframe: string): string {
  return SLOWER[timeframe?.toUpperCase()] ?? timeframe;
}

function shiftTime(time: string, minutes: number): string {
  const [h, m] = String(time || "00:00").split(":").map((n) => Number(n));
  if (!Number.isFinite(h) || !Number.isFinite(m)) return time;
  const total = (h * 60 + m + minutes + 24 * 60) % (24 * 60);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

function clampNumber(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function signature(code: string, kind: string, payload: unknown): string {
  return `${code}:${kind}:${JSON.stringify(payload)}`;
}

function nextAppetite(appetite: RiskAppetite): RiskAppetite {
  return appetite === "aggressive"
    ? "normal"
    : appetite === "normal"
      ? "conservative"
      : "conservative";
}

export interface ProposalContext {
  config: TradingConfig;
  authority: TradingAuthority;
}

/**
 * The improvement catalogue. Each entry answers "what would actually help?"
 * for one refusal code, with the narrowest change first.
 */
export function proposeImprovements(
  patterns: readonly FailurePattern[],
  context: ProposalContext,
): ImprovementProposal[] {
  return patterns.map((pattern) => buildProposal(pattern, context));
}

export function buildProposal(
  pattern: FailurePattern,
  context: ProposalContext,
): ImprovementProposal {
  const { config, authority } = context;
  const band = APPETITE_BANDS[authority.appetite];
  const since = pattern.firstAt ? new Date(pattern.firstAt).toLocaleString() : "recently";
  const lead = `I failed ${pattern.count}× with ${pattern.code} since ${since}.`;

  switch (pattern.code) {
    case "RISK_REFUSED":
    case "INSUFFICIENT_MARGIN":
    case "MANDATE_CAP_REQUIRED": {
      const volume = clampNumber(Number((config.volume * 0.5).toFixed(4)), 0.01, 1000);
      return proposal({
        pattern,
        kind: "tighten",
        title: "Halve the order size",
        rationale: `${pattern.code} means size or margin was too large for the venue. Halving the volume keeps the same strategy with half the exposure.`,
        changes: { volume },
        authorityChanges: authority.requireStop ? {} : { requireStop: true },
        riskDelta: "lower",
        autoApplicable: true,
        message: `${lead} I can halve the order size (${config.volume} → ${volume}) and keep the stop loss required. Want me to apply that?`,
      });
    }

    case "POSITION_ALREADY_OPEN":
    case "POSITION_CAP_REACHED": {
      const cap = clampNumber(authority.maxOpenPositions + 1, 1, band.maxPositions);
      const canRaise = cap > authority.maxOpenPositions;
      return proposal({
        pattern,
        kind: "config",
        title: canRaise
          ? `Allow ${cap} open positions`
          : "Keep one position and add a cooldown",
        rationale: canRaise
          ? `The strategy produced more concurrent entries than the cap allows. The ${authority.appetite} band permits up to ${band.maxPositions}.`
          : `The ${authority.appetite} band already caps this bot at ${band.maxPositions} position(s); adding a cooldown avoids immediate re-entry instead.`,
        changes: {},
        authorityChanges: canRaise
          ? { maxOpenPositions: cap }
          : { cooldownS: Math.max(authority.cooldownS, 1800) },
        riskDelta: canRaise ? "higher" : "lower",
        autoApplicable: !canRaise,
        message: canRaise
          ? `${lead} The ${authority.appetite} band allows up to ${band.maxPositions} open positions; you are at ${authority.maxOpenPositions}. Raising the cap increases exposure — shall I?`
          : `${lead} I can add a 30-minute cooldown so I stop re-entering the same move. Want that?`,
      });
    }

    case "SESSION_CLOSED": {
      const start = shiftTime(config.session?.start ?? "08:00", -60);
      const end = shiftTime(config.session?.end ?? "20:00", 60);
      return proposal({
        pattern,
        kind: "config",
        title: "Widen the session window",
        rationale: "Signals keep appearing just outside the configured window. Widening it by an hour each side lets the strategy act on them — it also means trading at less liquid times.",
        changes: config.session
          ? { session: { ...config.session, start, end } }
          : {},
        authorityChanges: {},
        riskDelta: "higher",
        autoApplicable: false,
        message: `${lead} I can widen the session to ${start}–${end} so signals just outside the window are not missed. That trades in quieter hours — your call.`,
      });
    }

    case "STALE_MARKET_DATA":
    case "QUOTE_UNAVAILABLE": {
      const next = slowerTimeframe(config.timeframe);
      return proposal({
        pattern,
        kind: "config",
        title: next !== config.timeframe ? `Move to ${next}` : "Check the data source",
        rationale: next !== config.timeframe
          ? `The ${config.timeframe} bar was not fresh when the bot ran. A slower timeframe tolerates a delayed feed at the cost of slower entries.`
          : "The feed is not producing fresh bars for this timeframe. The data source needs attention before this bot can trade reliably.",
        changes: next !== config.timeframe ? { timeframe: next } : {},
        authorityChanges: {},
        riskDelta: "lower",
        autoApplicable: next === config.timeframe,
        message: next !== config.timeframe
          ? `${lead} I can move this bot from ${config.timeframe} to ${next} so a delayed feed does not block every decision. Want that?`
          : `${lead} The feed is not delivering fresh bars. I have paused new entries; check the data source.`,
      });
    }

    case "SYMBOL_NOT_TRADABLE": {
      const missing = config.symbols.filter((symbol) =>
        pattern.samples.some((sample) => sample.toUpperCase().includes(symbol.toUpperCase())),
      );
      const excluded = Array.from(
        new Set([...config.excludedSymbols, ...(missing.length ? missing : [])]),
      );
      return proposal({
        pattern,
        kind: "tighten",
        title: "Drop the unavailable symbol",
        rationale: "The venue does not list one of the bot's symbols, so every attempt is refused. Removing it lets the remaining universe trade.",
        changes: { excludedSymbols: excluded },
        authorityChanges: {},
        riskDelta: "lower",
        autoApplicable: true,
        message: `${lead} I can stop scanning the symbol this venue does not offer and keep the rest of the universe. Apply it?`,
      });
    }

    case "COOLDOWN_ACTIVE":
      return proposal({
        pattern,
        kind: "config",
        title: "Review the cooldown",
        rationale: "The bot is deliberately waiting between orders. If the strategy is meant to trade more often, the cooldown is the wrong shape for it.",
        changes: {},
        authorityChanges: {},
        riskDelta: "same",
        autoApplicable: false,
        message: `${lead} This is my cooldown doing its job. If you want faster entries, lower it; otherwise nothing needs to change.`,
      });

    case "DAILY_LOSS_LIMIT":
      return proposal({
        pattern,
        kind: "tighten",
        title: "Step the risk down one band",
        rationale: `The daily loss brake fired ${pattern.count}×. A smaller appetite band trades less size until the strategy proves itself again.`,
        changes: {},
        authorityChanges: {
          appetite: nextAppetite(authority.appetite),
          maxDailyLossPct: Math.max(1, Math.round(authority.maxDailyLossPct * 0.75)),
        },
        riskDelta: "lower",
        autoApplicable: true,
        message: `${lead} I can step my risk appetite down to ${nextAppetite(authority.appetite)} and tighten the daily brake. That is strictly smaller — shall I?`,
      });

    case "ORDER_REFUSED":
      return proposal({
        pattern,
        kind: "tighten",
        title: "Reduce size and require a stop",
        rationale: "The broker refused these orders. The safe assumption is that size or the missing stop was the problem, so the next attempt is smaller and bracketed.",
        changes: { volume: clampNumber(Number((config.volume * 0.75).toFixed(4)), 0.01, 1000) },
        authorityChanges: { requireStop: true },
        riskDelta: "lower",
        autoApplicable: false,
        message: `${lead} I can retry with 25% smaller size and a mandatory stop. The broker's exact reason is in the run; want me to apply this?`,
      });

    case "TRADING_NOT_PREPARED":
      return proposal({
        pattern,
        kind: "repair",
        title: "Finish trading setup",
        rationale: "The bot was saved without a prepared trial or consent, so every run stops before it can decide.",
        changes: {},
        authorityChanges: {},
        riskDelta: "same",
        autoApplicable: false,
        message: `${lead} Trading was never prepared. Open the Trading tab and grant consent once; after that I will not ask again.`,
      });

    case "BROKER_UNAVAILABLE":
      return proposal({
        pattern,
        kind: "pause",
        title: "Pause until the broker is back",
        rationale: "The broker could not be reached. Repeating the same run wastes attempts and hides the real problem.",
        changes: { dryRun: true },
        authorityChanges: { autoRenew: false },
        riskDelta: "lower",
        autoApplicable: true,
        message: `${lead} I have switched myself to preview-only until the broker is reachable. Re-enable me when the connection is healthy.`,
      });

    default:
      return proposal({
        pattern,
        kind: "config",
        title: "Review this failure with me",
        rationale: `${pattern.code} is not one I can fix safely on my own. The samples show what was refused.`,
        changes: {},
        authorityChanges: {},
        riskDelta: "same",
        autoApplicable: false,
        message: `${lead} ${codeInfo(pattern.code).remedy} Shall we look at the decisions together before I change anything?`,
      });
  }
}

function proposal(input: {
  pattern: FailurePattern;
  kind: ImprovementProposal["kind"];
  title: string;
  rationale: string;
  changes: Partial<TradingConfig>;
  authorityChanges: Partial<TradingAuthority>;
  riskDelta: ImprovementProposal["riskDelta"];
  autoApplicable: boolean;
  message: string;
}): ImprovementProposal {
  return {
    id: signature(input.pattern.code, input.kind, {
      changes: input.changes,
      authority: input.authorityChanges,
    }),
    code: input.pattern.code,
    kind: input.kind,
    title: input.title,
    rationale: input.rationale,
    message: input.message,
    changes: input.changes,
    authorityChanges: input.authorityChanges,
    riskDelta: input.riskDelta,
    autoApplicable: input.autoApplicable,
  };
}

export interface ApplyResult {
  config: TradingConfig;
  authority: TradingAuthority;
  /** What actually changed, for the chat acknowledgement. */
  applied: string[];
}

/**
 * Apply one proposal. The bot may only tighten on its own; a `higher` risk delta
 * is refused unless `operatorApproved` is true. Every numeric field is clamped to
 * the appetite band, so a bad proposal cannot escape the leash.
 */
export function applyProposal(
  config: TradingConfig,
  authority: TradingAuthority,
  proposal: ImprovementProposal,
  operatorApproved = false,
): ApplyResult {
  if (proposal.riskDelta === "higher" && !operatorApproved) {
    return { config, authority, applied: [] };
  }
  const applied: string[] = [];
  const nextConfig: TradingConfig = { ...config, ...proposal.changes };
  const nextAuthority: TradingAuthority = { ...authority, ...proposal.authorityChanges };
  const band = APPETITE_BANDS[nextAuthority.appetite];

  for (const key of Object.keys(proposal.changes)) {
    const before = JSON.stringify((config as unknown as Record<string, unknown>)[key]);
    const after = JSON.stringify((nextConfig as unknown as Record<string, unknown>)[key]);
    if (before !== after) applied.push(key);
  }
  for (const key of Object.keys(proposal.authorityChanges)) {
    const before = JSON.stringify((authority as unknown as Record<string, unknown>)[key]);
    const after = JSON.stringify((nextAuthority as unknown as Record<string, unknown>)[key]);
    if (before !== after) applied.push(`authority.${key}`);
  }

  // The leash clamps everything, even a hand-edited proposal.
  nextConfig.volume = clampNumber(nextConfig.volume, 0.01, 1000);
  nextConfig.maxOrdersPerDay = clampNumber(
    Math.min(nextConfig.maxOrdersPerDay, band.maxOrdersPerDay),
    MIN_MAX_ORDERS_PER_DAY,
    MAX_MAX_ORDERS_PER_DAY,
  );
  nextAuthority.maxOpenPositions = clampNumber(
    nextAuthority.maxOpenPositions,
    1,
    band.maxPositions,
  );
  nextAuthority.cooldownS = clampNumber(nextAuthority.cooldownS, 0, 86_400);
  nextAuthority.maxDailyLossPct = clampNumber(nextAuthority.maxDailyLossPct, 0, 50);

  return { config: nextConfig, authority: nextAuthority, applied };
}

/** Proposals that are safe to apply silently because they only reduce risk. */
export function autoApplicable(proposals: readonly ImprovementProposal[]): ImprovementProposal[] {
  return proposals.filter((item) => item.autoApplicable && item.riskDelta === "lower");
}

/** Keep the proposal list stable and un-nagging. */
export function markProposed(
  policy: LearningPolicy,
  proposals: readonly ImprovementProposal[],
  now: number = Date.now(),
): LearningPolicy {
  const proposed = Array.from(
    new Set([...policy.proposed, ...proposals.map((item) => item.id)]),
  ).slice(-40);
  return {
    ...policy,
    proposed,
    lastProposedAt: proposals.length
      ? new Date(now).toISOString()
      : policy.lastProposedAt,
  };
}

export function acceptProposal(
  policy: LearningPolicy,
  proposal: ImprovementProposal,
  now: number = Date.now(),
): LearningPolicy {
  return {
    ...policy,
    lastAcceptedAt: new Date(now).toISOString(),
    proposed: Array.from(new Set([...policy.proposed, proposal.id])).slice(-40),
  };
}

/** The chat message the bot sends when it has lessons to discuss. */
export function learningDigest(
  patterns: readonly FailurePattern[],
  proposals: readonly ImprovementProposal[],
): string | null {
  if (!proposals.length) return null;
  const lines = proposals.slice(0, 2).map((item) => `• ${item.message}`);
  const lead =
    patterns.length > 1
      ? `I have ${patterns.length} patterns to fix.`
      : "I have a pattern to fix.";
  return [lead, ...lines, "Nothing changes until you say yes."].join("\n");
}

/** A one-line health summary for the detail panel. */
export function learningSummary(
  patterns: readonly FailurePattern[],
  policy: LearningPolicy,
): string {
  if (!policy.enabled) return "Learning is off for this bot.";
  if (!patterns.length) return "No repeated failures — nothing to learn yet.";
  const codes = patterns.map((item) => `${item.code}×${item.count}`).join(", ");
  return `Repeated failures: ${codes}.`;
}
