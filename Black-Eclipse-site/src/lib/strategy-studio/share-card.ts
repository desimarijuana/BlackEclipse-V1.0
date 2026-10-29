// ── Share card (Markdown) ───────────────────────────────────────────────────
// A read-only summary of the strategy the studio is looking at: spec identity,
// window, the runtime's metrics, the evidence grade and the paper state. It is
// presentation only — every number comes from the runtime, and the disclaimer
// travels with it.

import { formatMetric, type StrategyRecord } from "@/lib/backtest/backtest-client";
import { splitSymbols } from "./preflight";

export interface ShareCardInput {
  name: string;
  id: string;
  version: string;
  description?: string | null;
  symbols: string[];
  timeframe?: string | null;
  start?: string | null;
  end?: string | null;
  metrics?: Record<string, number | null> | null;
  grade?: string | null;
  score?: number | null;
  flags?: Array<{ code: string; severity: string; message: string }> | null;
  paper?: { state: string; headline: string } | null;
  link?: string | null;
}

const METRICS: Array<{ key: string; label: string }> = [
  { key: "total_return", label: "Total return" },
  { key: "cagr", label: "CAGR" },
  { key: "max_drawdown", label: "Max drawdown" },
  { key: "sharpe", label: "Sharpe" },
  { key: "sortino", label: "Sortino" },
  { key: "win_rate", label: "Win rate" },
  { key: "profit_factor", label: "Profit factor" },
  { key: "trade_count", label: "Trades" },
];

export const SHARE_DISCLAIMER =
  "Computed by the Eclipse quant engine. Not investment advice; past performance does not indicate future results.";

/** Assemble the card input from the studio's state (presentation only). */
export function buildShareCardInput(input: {
  saved: StrategyRecord | null;
  spec: Record<string, unknown> | null;
  identity: { id: string; name: string };
  symbolInput: string;
  timeframe: string;
  start: string;
  end: string;
  metrics: Record<string, number | null> | null;
  grade: string | null;
  score: number | null;
  flags: ShareCardInput["flags"];
  paper: { state: string; headline: string };
  link: string | null;
}): ShareCardInput {
  const typed = splitSymbols(input.symbolInput);
  const specSymbols =
    ((input.spec?.universe as { symbols?: string[] } | undefined)?.symbols ?? []);
  return {
    name: input.saved?.name || input.identity.name || "Untitled strategy",
    id: input.saved?.id ?? input.identity.id ?? "draft",
    version: String(input.saved?.version ?? input.saved?.latestVersion ?? "draft"),
    description: String(
      ((input.spec?.strategy as { description?: string } | undefined)?.description) ?? "",
    ),
    symbols: typed.length ? typed : specSymbols,
    timeframe: input.timeframe,
    start: input.start,
    end: input.end,
    metrics: input.metrics,
    grade: input.grade,
    score: input.score,
    flags: input.flags,
    paper: input.paper,
    link: input.link,
  };
}

export function buildShareCardMarkdown(input: ShareCardInput): string {
  const lines: string[] = [`# ${input.name} (v${input.version})`, ""];
  if (input.description) lines.push(input.description, "");

  lines.push(`- **Strategy:** \`${input.id}\``);
  if (input.symbols.length) lines.push(`- **Universe:** ${input.symbols.join(", ")}`);
  if (input.timeframe) lines.push(`- **Timeframe:** ${input.timeframe}`);
  if (input.start && input.end) lines.push(`- **Window:** ${input.start} → ${input.end}`);
  lines.push("");

  if (input.metrics) {
    const rows = METRICS.filter((metric) => typeof input.metrics?.[metric.key] === "number");
    if (rows.length) {
      lines.push("## Performance", "", "| Metric | Value |", "|---|---|");
      for (const row of rows) {
        lines.push(`| ${row.label} | ${formatMetricSafely(row.key, input.metrics[row.key])} |`);
      }
      lines.push("");
    }
  }

  if (input.grade) {
    lines.push("## Evidence", "");
    lines.push(`Grade **${input.grade}**${input.score != null ? ` (score ${Math.round(input.score)}/100)` : ""}.`);
    for (const flag of input.flags ?? []) {
      lines.push(`- \`${flag.code}\` (${flag.severity}): ${flag.message}`);
    }
    lines.push("");
  }

  if (input.paper) {
    lines.push("## Paper", "", `**${input.paper.state}** — ${input.paper.headline}`, "");
  }

  if (input.link) lines.push("## Link", "", input.link, "");

  lines.push(`_${SHARE_DISCLAIMER}_`);
  return lines.join("\n").replace(/\n{3,}/g, "\n\n").trimEnd();
}

function formatMetricSafely(name: string, value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return formatMetric(name, value);
}
