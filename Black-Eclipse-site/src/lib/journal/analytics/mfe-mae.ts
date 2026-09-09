// ── MFE / MAE — Max Favorable & Adverse Excursion ────────────────────────────
// Computed from a price series over the trade's lifetime. MFE = the best
// unrealized R the trade reached; MAE = the worst unrealized R. These reveal
// whether a trade was "given back" (high MFE, low final R) or "held through
// drawdown" (deep MAE).

import type { Direction } from "../types";

export interface PricePoint {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume?: number | null;
}

export interface MfeMaeResult {
  mfe: number | null; // best favorable excursion in R
  mae: number | null; // worst adverse excursion in R
  mfePrice: number | null;
  maePrice: number | null;
}

/**
 * Compute MFE/MAE in R-multiples from a price series.
 *
 * @param series  chronological price bars (daily or intraday)
 * @param entry   entry price
 * @param stopLoss stop price (for risk per unit)
 * @param direction LONG | SHORT
 * @param entryTime ISO entry time
 * @param exitTime ISO exit time
 */
export function computeMfeMae(
  series: PricePoint[],
  entry: number,
  stopLoss: number | null,
  direction: Direction,
  entryTime: string,
  exitTime: string,
): MfeMaeResult {
  if (!stopLoss || stopLoss <= 0 || entry <= 0) {
    return { mfe: null, mae: null, mfePrice: null, maePrice: null };
  }

  const riskPerUnit = Math.abs(entry - stopLoss);
  if (riskPerUnit <= 0) return { mfe: null, mae: null, mfePrice: null, maePrice: null };

  // Daily bars are timestamped at midnight while trades happen intraday, so
  // compare by calendar date (YYYY-MM-DD) rather than exact timestamp.
  const entryDay = entryTime.slice(0, 10);
  const exitDay = exitTime.slice(0, 10);
  const sign = direction === "LONG" ? 1 : -1;

  let mfe = 0;
  let mae = 0;
  let mfePrice: number | null = null;
  let maePrice: number | null = null;

  for (const bar of series) {
    const day = bar.date.slice(0, 10);
    // Only consider bars within the trade window (entry day..exit day).
    if (day < entryDay || day > exitDay) continue;

    const high = bar.high ?? bar.close;
    const low = bar.low ?? bar.close;
    if (high == null || low == null) continue;

    // Favorable excursion: for LONG, the highest high; for SHORT, the lowest low.
    const favorable = direction === "LONG" ? high : low;
    const adverse = direction === "LONG" ? low : high;

    const favR = ((favorable - entry) * sign) / riskPerUnit;
    const advR = ((adverse - entry) * sign) / riskPerUnit;

    if (favR > mfe) { mfe = favR; mfePrice = favorable; }
    if (advR < mae) { mae = advR; maePrice = adverse; }
  }

  return { mfe, mae, mfePrice, maePrice };
}
