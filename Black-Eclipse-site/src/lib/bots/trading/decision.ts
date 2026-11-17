// ── Decision vocabulary ────────────────────────────────────────────────────
// Every run ends in a decision. This module is the ONE place that turns a
// decision (or a refusal code) into words a person can act on, so the bot chat,
// run history and the trading panel cannot disagree about what happened.

import type { DecisionOutcome, DecisionRecord, TradingAction } from "./types";

export interface RefusalCodeInfo {
  /** What the code means, in one sentence. */
  label: string;
  /** What the operator can do about it. */
  remedy: string;
  /** `info` = normal no-trade, `warning` = fixable, `error` = needs a human. */
  severity: "info" | "warning" | "error";
  /** Whether this code should feed the learning loop. */
  learnable: boolean;
}

export const REFUSAL_CODES: Record<string, RefusalCodeInfo> = {
  // Strategy / preparation
  STRATEGY_UNAVAILABLE: {
    label: "The strategy or version no longer exists.",
    remedy: "Re-pin the bot to an active strategy version.",
    severity: "error",
    learnable: false,
  },
  STRATEGY_NOT_APPROVED: {
    label: "This strategy version has no approval.",
    remedy: "Approve the version in Strategy Studio.",
    severity: "warning",
    learnable: false,
  },
  STRATEGY_NO_BACKTEST: {
    label: "This strategy version has no completed backtest.",
    remedy: "Run a backtest, then re-prepare the bot.",
    severity: "warning",
    learnable: false,
  },
  TRADING_NOT_PREPARED: {
    label: "Trading was never prepared for this bot.",
    remedy: "Finish the Trading tab and grant consent.",
    severity: "warning",
    learnable: false,
  },
  SYMBOL_NOT_TRADABLE: {
    label: "The venue does not offer this symbol.",
    remedy: "Remove the symbol or pick a venue that lists it.",
    severity: "warning",
    learnable: true,
  },
  MODE_MISMATCH: {
    label: "The bot's mode and the connection's mode disagree.",
    remedy: "Use a demo bot on a demo connection, live on live.",
    severity: "error",
    learnable: false,
  },

  // Market / timing
  SESSION_CLOSED: {
    label: "Outside the bot's trading session.",
    remedy: "Widen or shift the session window.",
    severity: "info",
    learnable: true,
  },
  STALE_MARKET_DATA: {
    label: "The last bar or quote is too old to trade.",
    remedy: "Check the market-data source, or use a slower timeframe.",
    severity: "warning",
    learnable: true,
  },
  BAR_ALREADY_PROCESSED: {
    label: "This bar was already decided.",
    remedy: "Nothing to do — the bot is idempotent per bar.",
    severity: "info",
    learnable: false,
  },
  QUOTE_UNAVAILABLE: {
    label: "No broker quote was available.",
    remedy: "Check the venue connection.",
    severity: "warning",
    learnable: true,
  },

  // Position / risk
  POSITION_ALREADY_OPEN: {
    label: "A position already exists for this bot and symbol.",
    remedy: "Raise the position cap, or let the open trade finish.",
    severity: "info",
    learnable: true,
  },
  RISK_REFUSED: {
    label: "The risk engine refused the order.",
    remedy: "Reduce size, add a stop, or loosen a limit if it is wrong.",
    severity: "warning",
    learnable: true,
  },
  DAILY_LOSS_LIMIT: {
    label: "The daily loss brake stopped trading.",
    remedy: "Wait for the next session, or review what is losing.",
    severity: "warning",
    learnable: true,
  },
  COOLDOWN_ACTIVE: {
    label: "The bot is inside its cooldown window.",
    remedy: "Lower the cooldown if it is too strict.",
    severity: "info",
    learnable: true,
  },
  POSITION_CAP_REACHED: {
    label: "The bot is at its open-position cap.",
    remedy: "Raise the cap or close a position.",
    severity: "info",
    learnable: true,
  },

  // Authority / mandate
  BOT_TIER_INSUFFICIENT: {
    label: "This bot's tier does not allow that mode.",
    remedy: "Raise the tier after the track record qualifies.",
    severity: "warning",
    learnable: false,
  },
  BOT_VERSION_STALE: {
    label: "The bot changed since its authority was granted.",
    remedy: "Re-grant trading authority.",
    severity: "warning",
    learnable: false,
  },
  LIVE_NOT_ARMED: {
    label: "The live connection is not armed.",
    remedy: "Arm the connection (typed phrase, time-boxed).",
    severity: "warning",
    learnable: false,
  },
  BOT_TIER_REQUIRED: {
    label: "Live execution needs tier L2.",
    remedy: "Raise the tier once the bot qualifies.",
    severity: "warning",
    learnable: false,
  },
  AUTHORIZATION_REQUIRED: {
    label: "The order had no approval or mandate.",
    remedy: "Grant standing consent, then re-prepare.",
    severity: "error",
    learnable: false,
  },
  MANDATE_CAP_REQUIRED: {
    label: "The mandate needs a positive margin cap.",
    remedy: "Set a max margin per order.",
    severity: "warning",
    learnable: true,
  },
  APPROVAL_REQUIRED: {
    label: "This order needs the operator's approval.",
    remedy: "Approve the card, or raise the bot's tier.",
    severity: "info",
    learnable: false,
  },

  // Broker
  BROKER_UNAVAILABLE: {
    label: "The broker could not be reached.",
    remedy: "Check the terminal/connection, then retry.",
    severity: "error",
    learnable: true,
  },
  ORDER_REFUSED: {
    label: "The broker refused the order.",
    remedy: "Read the broker's reason; it usually names the field.",
    severity: "warning",
    learnable: true,
  },
  INSUFFICIENT_MARGIN: {
    label: "Not enough free margin for this order.",
    remedy: "Reduce size or free margin.",
    severity: "warning",
    learnable: true,
  },
  SHADOW: {
    label: "Shadow mode: recorded, nothing was sent.",
    remedy: "Switch to demo (or live) when the decisions look right.",
    severity: "info",
    learnable: false,
  },
};

/** A code we do not know is shown honestly, never mapped to success. */
export function codeInfo(code: string | null | undefined): RefusalCodeInfo {
  if (!code) {
    return {
      label: "No code was recorded.",
      remedy: "Check the run's decision record.",
      severity: "warning",
      learnable: false,
    };
  }
  return (
    REFUSAL_CODES[code] ?? {
      label: `Unrecognised outcome (${code}).`,
      remedy: "Treat this as an error and inspect the run.",
      severity: "error",
      learnable: false,
    }
  );
}

const ACTION_LABEL: Record<TradingAction, string> = {
  buy: "BUY",
  sell: "SELL",
  close: "CLOSE",
  none: "—",
};

const OUTCOME_LABEL: Record<DecisionOutcome, string> = {
  filled: "filled",
  placed: "working",
  preview: "preview",
  refused: "refused",
  skipped: "skipped",
  failed: "failed",
  none: "no trade",
};

export function formatDecisionLine(decision: DecisionRecord): string {
  const size =
    decision.action !== "none" && decision.risk?.quantity
      ? ` ${decision.risk.quantity}`
      : "";
  const action = `${ACTION_LABEL[decision.action] ?? decision.action}${size}`;
  const bits = [decision.symbol || "—", action];
  bits.push(OUTCOME_LABEL[decision.outcome] ?? decision.outcome);
  if (decision.code) bits.push(`(${decision.code})`);
  return bits.join(" · ");
}

/** The sentence the bot says in chat for a decision. */
export function explainDecision(decision: DecisionRecord): string {
  const head = formatDecisionLine(decision);
  const info = codeInfo(decision.code);
  if (decision.outcome === "none" || decision.outcome === "skipped") {
    return `${head}: ${decision.reason}`;
  }
  if (decision.outcome === "refused" || decision.outcome === "failed") {
    const why = decision.reason ? `${decision.reason} — ` : "";
    return `${head}: ${why}${info.label} ${info.remedy}`;
  }
  return `${head}: ${decision.reason}`;
}

export function decisionNeedsAttention(decision: DecisionRecord): boolean {
  if (decision.outcome === "failed") return true;
  if (decision.outcome === "refused") return true;
  return codeInfo(decision.code).severity === "error";
}

export type DecisionTone = "positive" | "warning" | "danger" | "info" | "muted";

/** The restrained tone the UI paints a decision with. */
export function decisionTone(decision: DecisionRecord): DecisionTone {
  if (decision.outcome === "filled" || decision.outcome === "placed") return "positive";
  if (decision.outcome === "preview") return "info";
  if (decision.outcome === "failed") return "danger";
  if (decision.outcome === "refused") {
    return codeInfo(decision.code).severity === "error" ? "danger" : "warning";
  }
  if (decision.outcome === "skipped") return "info";
  return "muted";
}

/** Whether a decision counts as a failure for the learning loop. */
export function isLearnableFailure(
  decision: Pick<DecisionRecord, "outcome" | "code">,
): boolean {
  if (decision.outcome === "filled" || decision.outcome === "placed") return false;
  if (decision.outcome === "preview" || decision.outcome === "none") return false;
  if (!decision.code) return false;
  // An unrecognised code is exactly what the bot should raise with its operator,
  // so it is learnable even though the catalog cannot explain it.
  return REFUSAL_CODES[decision.code]?.learnable ?? true;
}

/** Decisions that were made but traded nothing (honest no-ops). */
export function isNoTrade(decision: Pick<DecisionRecord, "outcome" | "action">): boolean {
  return decision.action === "none" || decision.outcome === "none";
}
