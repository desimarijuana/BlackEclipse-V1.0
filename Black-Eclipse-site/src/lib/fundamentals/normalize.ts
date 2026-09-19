// ── Provider → Eclipse normalization ────────────────────────────────────────
// A provider returns statement rows using ITS field names (or none at all, for
// SEC's XBRL tags). Everything funnels through here into one period shape, and
// per-period ratios are derived once. The UI never sees a provider field name.

import type { FundamentalPeriod, ProviderFundamentals } from './types';

function ratio(numerator: number | null, denominator: number | null): number | null {
  if (numerator === null || denominator === null) return null;
  if (denominator === 0 || !Number.isFinite(denominator)) return null;
  const r = numerator / denominator;
  return Number.isFinite(r) ? r : null;
}

/** Fiscal year from a period end date, using the calendar year. */
export function fiscalYearOf(endDate: string): number | null {
  const m = endDate.match(/^(\d{4})/);
  if (m) return Number(m[1]);
  const ts = Date.parse(endDate);
  return Number.isNaN(ts) ? null : new Date(ts).getUTCFullYear();
}

/**
 * Derive the per-period ratios. `roic` uses invested capital ≈ total debt +
 * total equity (falling back to assets when debt is unavailable), which is the
 * standard simple definition and is honest about its inputs.
 */
export function derivePeriodRatios(
  p: Omit<
    FundamentalPeriod,
    | 'fiscalYear'
    | 'grossMargin'
    | 'operatingMargin'
    | 'netMargin'
    | 'roe'
    | 'roa'
    | 'roic'
    | 'debtToEquity'
    | 'currentRatio'
    | 'quickRatio'
  >
): FundamentalPeriod {
  const investedCapital =
    p.totalDebt !== null && p.totalEquity !== null
      ? p.totalDebt + p.totalEquity
      : p.totalEquity;
  const operatingProfit = p.operatingIncome ?? p.ebitda;
  return {
    ...p,
    fiscalYear: fiscalYearOf(p.endDate),
    grossMargin: ratio(p.grossProfit, p.revenue),
    operatingMargin: ratio(p.operatingIncome, p.revenue),
    netMargin: ratio(p.netIncome, p.revenue),
    roe: ratio(p.netIncome, p.totalEquity),
    roa: ratio(p.netIncome, p.totalAssets),
    roic: ratio(operatingProfit, investedCapital),
    debtToEquity: ratio(p.totalDebt, p.totalEquity),
    currentRatio: ratio(p.currentAssets, p.currentLiabilities),
    quickRatio:
      p.currentAssets !== null && p.currentLiabilities !== null
        ? ratio(p.currentAssets - (p.inventory ?? 0), p.currentLiabilities)
        : null,
  };
}

/**
 * Normalize a provider result into the Eclipse period list. Periods are sorted
 * oldest → newest and de-duplicated by end date (later providers/entries win).
 */
export function normalizePeriods(provider: ProviderFundamentals): FundamentalPeriod[] {
  const byDate = new Map<string, FundamentalPeriod>();
  for (const raw of provider.periods) {
    if (!raw.endDate) continue;
    byDate.set(raw.endDate, derivePeriodRatios(raw));
  }
  return [...byDate.values()].sort((a, b) => a.endDate.localeCompare(b.endDate));
}

/** The most recent period that has a usable revenue figure. */
export function latestReportingPeriod(periods: FundamentalPeriod[]): FundamentalPeriod | null {
  for (let i = periods.length - 1; i >= 0; i--) {
    if (periods[i].revenue !== null || periods[i].netIncome !== null) return periods[i];
  }
  return periods.length ? periods[periods.length - 1] : null;
}
