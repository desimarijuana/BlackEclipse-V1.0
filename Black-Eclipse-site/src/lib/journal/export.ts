// ── Journal export — deterministic CSV serialization ─────────────────────────
// Pure helpers used by the export API route. Every column round-trips back
// through the CSV importer, so the export is a faithful backup of the journal.

import type { TradeRecord } from "./types";

export const EXPORT_COLUMNS = [
  "Date",
  "Symbol",
  "Direction",
  "Entry",
  "Exit",
  "StopLoss",
  "TakeProfit",
  "Quantity",
  "EntryTime",
  "ExitTime",
  "Timeframe",
  "Session",
  "Emotion",
  "Confidence",
  "Strategy",
  "Setup",
  "Account",
  "Tags",
  "Mistakes",
  "Grade",
  "GrossPnL",
  "Commission",
  "Fee",
  "PnL",
  "RMultiple",
  "DurationSec",
  "Status",
  "Notes",
] as const;

function csvCell(value: unknown): string {
  if (value == null) return "";
  const s = String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function parseMistakes(raw: string | null | undefined): string {
  if (!raw) return "";
  try {
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? (arr as string[]).join("; ") : "";
  } catch {
    return "";
  }
}

/** Serialize trades to CSV (RFC-4180 quoting). */
export function tradesToCsv(trades: TradeRecord[]): string {
  const lines: string[] = [EXPORT_COLUMNS.join(",")];
  for (const t of trades) {
    lines.push(
      [
        t.exitTime.slice(0, 10),
        t.symbol,
        t.direction,
        t.entry,
        t.exit,
        t.stopLoss,
        t.takeProfit,
        t.quantity,
        t.entryTime,
        t.exitTime,
        t.timeframe,
        t.session,
        t.emotion,
        t.confidence,
        t.strategyName,
        t.setupName,
        t.accountName,
        (t.tags ?? []).join("; "),
        parseMistakes(t.mistakes),
        t.grade,
        t.grossPnl,
        t.commission,
        t.fee,
        t.pnl,
        t.rMultiple,
        t.durationSec,
        t.status,
        t.notes,
      ].map(csvCell).join(","),
    );
  }
  return lines.join("\r\n");
}
