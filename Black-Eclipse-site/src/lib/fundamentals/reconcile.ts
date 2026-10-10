// ── Cross-source period reconciliation (P3) ──────────────────────────────────
// The same fiscal figure can come from several sources (SEC/vendor/exchange
// filings/research). When two sources report the SAME metric for the SAME period
// and disagree materially, that must be surfaced, not silently averaged. This is
// a pure comparator: it never "fixes" a value — it names the conflict so the UI
// can show it and the operator can investigate.

import type { FundamentalPeriod, FundamentalProviderId } from './types';

export interface PeriodConflict {
  metric: string;
  endDate: string;
  values: Array<{ provider: FundamentalProviderId; value: number }>;
  /** Largest pairwise relative difference, percent. */
  maxDeltaPct: number;
}

// Statement line items worth cross-checking (skip pure ratios/derived).
const CHECKED: Array<keyof FundamentalPeriod> = [
  'revenue', 'costOfRevenue', 'grossProfit', 'operatingIncome', 'ebitda', 'netIncome', 'eps',
  'operatingCashFlow', 'capex', 'freeCashFlow', 'dividendsPaid',
  'totalAssets', 'totalLiabilities', 'totalEquity', 'totalDebt', 'netDebt', 'cash', 'sharesOutstanding',
];

function relPct(a: number, b: number): number {
  const base = Math.max(Math.abs(a), Math.abs(b));
  if (base === 0) return 0;
  return (Math.abs(a - b) / base) * 100;
}

/**
 * Find material disagreements between provider period sets. `thresholdPct` is the
 * relative difference above which two values count as conflicting (default 1%,
 * to absorb rounding/scale — e.g. PSX thousands vs a vendor's exact rupees).
 */
export function reconcilePeriods(
  sources: Array<{ provider: FundamentalProviderId; periods: FundamentalPeriod[] }>,
  thresholdPct = 1,
): PeriodConflict[] {
  const byPeriod = new Map<string, Map<string, Array<{ provider: FundamentalProviderId; value: number }>>>();
  for (const s of sources) {
    for (const p of s.periods) {
      let metrics = byPeriod.get(p.endDate);
      if (!metrics) { metrics = new Map(); byPeriod.set(p.endDate, metrics); }
      for (const key of CHECKED) {
        const v = p[key];
        if (typeof v !== 'number' || !Number.isFinite(v)) continue;
        const arr = metrics.get(key as string) ?? [];
        arr.push({ provider: s.provider, value: v });
        metrics.set(key as string, arr);
      }
    }
  }

  const out: PeriodConflict[] = [];
  for (const [endDate, metrics] of byPeriod) {
    for (const [metric, values] of metrics) {
      if (values.length < 2) continue;
      let maxDeltaPct = 0;
      for (let i = 0; i < values.length; i++) {
        for (let j = i + 1; j < values.length; j++) {
          maxDeltaPct = Math.max(maxDeltaPct, relPct(values[i].value, values[j].value));
        }
      }
      if (maxDeltaPct > thresholdPct) {
        out.push({ metric, endDate, values, maxDeltaPct: +maxDeltaPct.toFixed(2) });
      }
    }
  }
  return out.sort((a, b) => b.maxDeltaPct - a.maxDeltaPct);
}
