// ── Journal tools — capabilities the journal agents can call ─────────────────
// Each tool wraps the deterministic analytics engine and returns a plain-text
// summary the LLM reasons over. The AI interprets real computed numbers — it
// never fabricates statistics.

import { getOrCreateProfile, loadTrades } from "@/lib/journal/data";
import { listBrokerLinks } from "@/lib/journal/broker/links";
import { computeJournalAnalytics } from "@/lib/journal/analytics";
import { buildWeeklyReview } from "@/lib/journal/analytics/weekly";
import { buildMonthlyWrapped } from "@/lib/journal/analytics/wrapped";
import { findSimilarTrades } from "@/lib/journal/analytics/similarity";
import { fmtR, fmtMoney } from "@/lib/journal/format";
import type { ToolDefinition } from "./tools";

async function getProfileTrades() {
  const profileId = await getOrCreateProfile();
  return loadTrades(profileId);
}

/** Full performance summary as plain text. */
async function getJournalSummary(): Promise<string> {
  const trades = await getProfileTrades();
  const a = computeJournalAnalytics(trades);
  const p = a.performance;
  const lines = [
    `Journal Summary (${p.totalTrades} closed trades):`,
    `  Win rate: ${(p.winRate * 100).toFixed(1)}% (${p.wins}W / ${p.losses}L / ${p.breakevens}B)`,
    `  Net P&L: ${fmtMoney(p.netPnl)} | Net R: ${fmtR(p.netR)}`,
    `  Expectancy: ${fmtR(p.expectancy)}/trade | Profit factor: ${p.profitFactor === Infinity ? "∞" : p.profitFactor.toFixed(2)}`,
    `  Max drawdown: ${fmtR(-p.maxDrawdown)} | Avg win: ${fmtMoney(p.averageWin)} | Avg loss: ${fmtMoney(p.averageLoss)}`,
    `  Current streak: ${p.currentStreak > 0 ? `${p.currentStreak}W` : p.currentStreak < 0 ? `${-p.currentStreak}L` : "flat"}`,
    `  Discipline: ${a.discipline.total}/100`,
  ];
  if (a.bySymbol.length) lines.push(`  Best market: ${a.bySymbol[0].key} (${fmtR(a.bySymbol[0].netR)})`);
  if (a.bySetup.length) lines.push(`  Best setup: ${a.bySetup[0].key} (${fmtR(a.bySetup[0].netR)})`);
  if (a.bySession.length) lines.push(`  Best session: ${a.bySession[0].key} (${fmtR(a.bySession[0].netR)})`);
  const leak = a.byEmotion.filter((e) => e.netR < 0).pop();
  if (leak) lines.push(`  Biggest emotional leak: ${leak.key} (${fmtR(leak.netR)})`);
  return lines.join("\n");
}

/** A specific trade's details + market context + similar trades. */
async function getTradeReview(tradeId: string): Promise<string> {
  const trades = await getProfileTrades();
  const trade = trades.find((t) => t.id === tradeId);
  if (!trade) return `No trade found with id ${tradeId}.`;
  const similar = findSimilarTrades(trade, trades, 5, 0.2);
  const lines = [
    `Trade ${trade.symbol} ${trade.direction}:`,
    `  Entry ${trade.entry} → Exit ${trade.exit} (${fmtR(trade.rMultiple)}, ${fmtMoney(trade.pnl)})`,
    `  Stop: ${trade.stopLoss ?? "none"} | Target: ${trade.takeProfit ?? "none"}`,
    `  Session: ${trade.session ?? "—"} | Timeframe: ${trade.timeframe ?? "—"} | Setup: ${trade.setupName ?? "—"}`,
    `  Emotion: ${trade.emotion ?? "—"} | Confidence: ${trade.confidence ?? "—"}`,
    trade.mfe != null ? `  MFE: ${fmtR(trade.mfe)} | MAE: ${fmtR(trade.mae ?? 0)}` : "",
    similar.count > 0
      ? `  ${similar.count} similar trades: ${(similar.winRate * 100).toFixed(0)}% win, avg ${fmtR(similar.averageR)}`
      : "  No similar historical trades.",
  ];
  return lines.filter(Boolean).join("\n");
}

/** Weekly review for a date range. */
async function getWeeklyReview(start: string, end: string): Promise<string> {
  const trades = await getProfileTrades();
  const w = buildWeeklyReview(trades, start, end);
  const lines = [
    `Weekly Review ${w.periodStart} to ${w.periodEnd}:`,
    `  ${w.performance.trades} trades, ${(w.performance.winRate * 100).toFixed(0)}% win, Net R ${fmtR(w.performance.netR)}, Net P&L ${fmtMoney(w.performance.netPnl)}`,
    `  Profit factor: ${w.performance.profitFactor === Infinity ? "∞" : w.performance.profitFactor.toFixed(2)} | Discipline: ${w.discipline}/100`,
  ];
  if (w.whatWorked.length) lines.push(`  What worked: ${w.whatWorked.map((x) => `${x.key} (${fmtR(x.netR)})`).join(", ")}`);
  if (w.whatHurt.length) lines.push(`  What hurt: ${w.whatHurt.map((x) => `${x.key} (${fmtR(x.netR)})`).join(", ")}`);
  if (w.biggestLeak) lines.push(`  Biggest leak: ${w.biggestLeak.key} (${fmtR(w.biggestLeak.netR)})`);
  return lines.join("\n");
}

/** Performance by strategy/setup. */
async function getStrategyAnalysis(): Promise<string> {
  const trades = await getProfileTrades();
  const a = computeJournalAnalytics(trades);
  const lines = ["Strategy / Setup analysis:"];
  if (a.bySetup.length) {
    lines.push("  By setup:");
    for (const s of a.bySetup.slice(0, 6)) {
      lines.push(`    ${s.key}: ${s.trades} trades, ${(s.winRate * 100).toFixed(0)}% win, ${fmtR(s.netR)}`);
    }
  } else {
    lines.push("  No setups recorded.");
  }
  return lines.join("\n");
}

/** Psychology / behavioral analysis. */
async function getPsychology(): Promise<string> {
  const trades = await getProfileTrades();
  const a = computeJournalAnalytics(trades);
  const lines = ["Psychology analysis:"];
  if (a.byEmotion.length) {
    lines.push("  By emotion:");
    for (const e of a.byEmotion.slice(0, 6)) {
      lines.push(`    ${e.key}: ${e.trades} trades, ${(e.winRate * 100).toFixed(0)}% win, ${fmtR(e.netR)}`);
    }
  } else {
    lines.push("  No emotions recorded.");
  }
  if (a.confidenceCorrelation != null) {
    lines.push(`  Confidence-outcome correlation: ${a.confidenceCorrelation.toFixed(2)}`);
  }
  return lines.join("\n");
}

/** Monthly wrapped report. */
async function getMonthlyWrapped(year: number, month: number): Promise<string> {
  const trades = await getProfileTrades();
  const w = buildMonthlyWrapped(trades, year, month);
  const lines = [
    `Monthly Wrapped ${w.label}:`,
    `  ${w.performance.trades} trades, ${(w.performance.winRate * 100).toFixed(0)}% win, Net R ${fmtR(w.performance.netR)}, Net P&L ${fmtMoney(w.performance.netPnl)}`,
    `  Profit factor: ${w.performance.profitFactor === Infinity ? "∞" : w.performance.profitFactor.toFixed(2)} | Discipline: ${w.discipline}/100`,
  ];
  if (w.bestSetup) lines.push(`  Best setup: ${w.bestSetup.key} (${fmtR(w.bestSetup.netR)})`);
  if (w.bestMarket) lines.push(`  Best market: ${w.bestMarket.key} (${fmtR(w.bestMarket.netR)})`);
  if (w.biggestLeak) lines.push(`  Biggest leak: ${w.biggestLeak.key} (${fmtR(w.biggestLeak.netR)})`);
  return lines.join("\n");
}

/** Broker link status (never a secret, never a fake connection). */
async function getBrokerStatus(): Promise<string> {
  const profileId = await getOrCreateProfile();
  const links = await listBrokerLinks(profileId);
  if (links.length === 0) return "No broker connection is linked to the journal.";
  const lines = [`Broker links (${links.length}):`];
  for (const link of links) {
    lines.push(
      `  ${link.connectionId}: ${link.enabled ? "enabled" : "disabled"}, ` +
        `auto-sync ${link.autoSync ? "on" : "off"}, status ${link.lastSyncStatus}, ` +
        `last synced ${link.lastSyncedAt ?? "never"}` +
        (link.lastError ? `, error: ${link.lastError}` : ""),
    );
  }
  return lines.join("\n");
}

/** Performance using only broker-projected trades, plus account/magic splits. */
async function getBrokerPerformance(): Promise<string> {
  const trades = await getProfileTrades();
  const brokerTrades = trades.filter((t) => t.source === "broker");
  if (brokerTrades.length === 0) {
    return "No broker-sourced trades in the journal yet. Link a broker in Journal → Settings → Broker Connection and sync.";
  }
  const a = computeJournalAnalytics(brokerTrades);
  const p = a.performance;
  const lines = [
    `Broker performance (${brokerTrades.length} trades, ${brokerTrades.filter((t) => t.status === "open").length} open):`,
    `  Closed: ${p.totalTrades} | Win rate: ${(p.winRate * 100).toFixed(1)}% (${p.wins}W / ${p.losses}L / ${p.breakevens}B)`,
    `  Net P&L: ${fmtMoney(p.netPnl)} | Net R: ${fmtR(p.netR)}`,
    `  Expectancy: ${fmtR(p.expectancy)}/trade | Profit factor: ${p.profitFactor === Infinity ? "∞" : p.profitFactor.toFixed(2)}`,
  ];
  if (a.byAccount.length) {
    lines.push("  By account:");
    for (const row of a.byAccount.slice(0, 6)) {
      lines.push(`    ${row.key}: ${row.trades} trades, ${(row.winRate * 100).toFixed(0)}% win, ${fmtR(row.netR)}, ${fmtMoney(row.netPnl)}`);
    }
  }
  if (a.byMagic.length) {
    lines.push("  By magic:");
    for (const row of a.byMagic.slice(0, 6)) {
      lines.push(`    ${row.key}: ${row.trades} trades, ${(row.winRate * 100).toFixed(0)}% win, ${fmtR(row.netR)}`);
    }
  }
  return lines.join("\n");
}

export const JOURNAL_TOOLS: ToolDefinition[] = [
  {
    name: "get_journal_summary",
    description: "Get an overall summary of the trader's performance: win rate, net R, expectancy, profit factor, drawdown, discipline, best market/setup/session, biggest leak.",
    parameters: { type: "object", properties: {} },
    execute: () => getJournalSummary(),
  },
  {
    name: "get_trade_review",
    description: "Get details of a specific trade by id, including its market context and similar historical trades.",
    parameters: {
      type: "object",
      properties: { tradeId: { type: "string", description: "The trade id to review" } },
      required: ["tradeId"],
    },
    execute: (a) => getTradeReview(String(a.tradeId || "")),
  },
  {
    name: "get_weekly_review",
    description: "Get the deterministic weekly review for a date range (YYYY-MM-DD).",
    parameters: {
      type: "object",
      properties: {
        start: { type: "string", description: "Start date YYYY-MM-DD" },
        end: { type: "string", description: "End date YYYY-MM-DD" },
      },
      required: ["start", "end"],
    },
    execute: (a) => getWeeklyReview(String(a.start || ""), String(a.end || "")),
  },
  {
    name: "get_strategy_analysis",
    description: "Get performance breakdown by strategy/setup.",
    parameters: { type: "object", properties: {} },
    execute: () => getStrategyAnalysis(),
  },
  {
    name: "get_psychology",
    description: "Get behavioral/psychology analysis: performance by emotion and confidence correlation.",
    parameters: { type: "object", properties: {} },
    execute: () => getPsychology(),
  },
  {
    name: "get_broker_status",
    description: "List the journal's linked broker connections, whether sync is enabled, and the last sync status. Use this before claiming broker data is available.",
    parameters: { type: "object", properties: {} },
    execute: () => getBrokerStatus(),
  },
  {
    name: "get_broker_performance",
    description: "Performance computed ONLY from broker-sourced trades, including per-account and per-magic splits. Never mixes in manual/demo trades.",
    parameters: { type: "object", properties: {} },
    execute: () => getBrokerPerformance(),
  },
  {
    name: "get_monthly_wrapped",
    description: "Get the monthly wrapped report for a year and month (0-indexed month).",
    parameters: {
      type: "object",
      properties: {
        year: { type: "number", description: "Year, e.g. 2026" },
        month: { type: "number", description: "Month 0-11" },
      },
    },
    execute: (a) => getMonthlyWrapped(Number(a.year) || new Date().getUTCFullYear(), Number(a.month) || new Date().getUTCMonth()),
  },
];

export function getJournalTool(name: string): ToolDefinition | undefined {
  return JOURNAL_TOOLS.find((t) => t.name === name);
}

export function journalToolSchemas() {
  return JOURNAL_TOOLS.map((t) => ({
    type: "function",
    function: { name: t.name, description: t.description, parameters: t.parameters },
  }));
}
