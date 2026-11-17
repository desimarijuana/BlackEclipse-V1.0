"use client";

// ── Chat context for a trading bot ─────────────────────────────────────────
// Two things a trading bot's conversation needs beyond its persona:
//   * its reference images, sent as REAL image parts (not just captions);
//   * the lessons it has learned from recent decisions, so "why didn't you
//     trade?" and "can we improve?" are answered from real refusals.
//
// Both are best-effort: a runtime that is down must not block the chat. The
// lesson text is included as a system message; the operator still approves any
// change in the Trading panel.

import {
  getBotTrading,
  type AutomationView,
} from "@/lib/harness/clients/automation-browser";
import type { RunImageInput } from "@/lib/harness/types";
import { buildTradingAuthority, buildTradingConfig, draftFromTradingAction } from "./draft";
import { analyzeFailures, learningDigest, proposeImprovements } from "./learning";
import type { DecisionRecord, StrategyVisual } from "./types";

/** The images attached to this bot, in the runtime's wire shape. */
export function referenceImages(bot: AutomationView): RunImageInput[] {
  const config = bot.action.config ?? {};
  const visuals = Array.isArray(config.visuals)
    ? (config.visuals as StrategyVisual[])
    : [];
  return visuals
    .filter((visual) => typeof visual?.dataUrl === "string" && visual.dataUrl.startsWith("data:image/"))
    .slice(0, 4)
    .map((visual) => ({
      dataUrl: visual.dataUrl,
      caption: visual.caption ?? "",
      mime: visual.mime ?? "image/png",
    }));
}

/** True when this bot has any trading context worth fetching. */
export function isTradingBot(bot: AutomationView): boolean {
  if (bot.action.type === "run_strategy") return true;
  const config = bot.action.config ?? {};
  if (typeof config.mode === "string" && config.mode) return true;
  if (config.consent) return true;
  return (bot.executionAuthority?.tier ?? "l0") !== "l0";
}

/**
 * The lesson digest for a bot chat turn, or null.
 *
 * The bot is told about repeated failures and the exact fix it would propose;
 * it must not claim a change happened. The operator applies it in the Trading
 * panel (which re-prepares under the standing consent).
 */
export async function tradingChatContext(bot: AutomationView): Promise<string | null> {
  if (!isTradingBot(bot)) return null;
  const config = bot.action.config ?? {};
  const learning = config.learning as { enabled?: boolean } | undefined;
  if (learning && learning.enabled === false) return null;
  try {
    const status = await getBotTrading(bot.id, 40);
    const decisions = (status.decisions ?? []) as unknown as DecisionRecord[];
    if (!decisions.length) return null;
    const draft = draftFromTradingAction(config, bot.executionAuthority);
    const patterns = analyzeFailures(decisions, {
      threshold: draft.improveAfterFailures,
      window: 60,
    });
    if (!patterns.length) return null;
    const proposals = proposeImprovements(patterns, {
      config: buildTradingConfig(draft),
      authority: buildTradingAuthority(draft),
    });
    const digest = learningDigest(patterns, proposals);
    if (!digest) return null;
    return [
      "Recent trading lessons (operator-facing context, from this bot's own decisions):",
      digest,
      "If the operator asks about them, explain the failures and the proposed change.",
      "Do not claim a change was applied: it needs their approval in the Trading panel.",
    ].join("\n");
  } catch {
    // An unavailable trading status is not a chat failure.
    return null;
  }
}
