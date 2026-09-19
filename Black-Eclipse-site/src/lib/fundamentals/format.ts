// ── Fundamentals display formatting (pure) ──────────────────────────────────
// One place that knows how an Eclipse metric renders. Percent metrics are
// stored as FRACTIONS, so the ×100 lives here and nowhere else.

import type { FundamentalMetric, MetricUnit } from './types';

/** Compact large numbers ("416.16B", "4.90T", "12.4M"). */
export function fmtCompact(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs >= 1e12) return `${sign}${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(1)}K`;
  return `${sign}${abs.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
}

export function fmtNumber(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtPercent(fraction: number | null | undefined, digits = 1): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return '—';
  return `${(fraction * 100).toFixed(digits)}%`;
}

/** Format a metric value according to its declared unit. */
export function fmtMetricValue(value: number | null, unit: MetricUnit, currency?: string | null): string {
  if (value === null || !Number.isFinite(value)) return '—';
  switch (unit) {
    case 'percent':
      return fmtPercent(value);
    case 'ratio':
      return `${fmtNumber(value, 2)}×`;
    case 'currency':
      return currency ? `${currency} ${fmtCompact(value)}` : fmtCompact(value);
    case 'shares':
    case 'number':
    default:
      return fmtNumber(value, Math.abs(value) >= 1000 ? 0 : 2);
  }
}

/** Directional tone for a change vs a metric's polarity. */
export function metricTone(metric: FundamentalMetric): 'up' | 'down' | 'flat' {
  const { value, polarity } = metric;
  if (value === null) return 'flat';
  if (polarity === 'neutral') return 'flat';
  if (value > 0) return polarity === 'higher' ? 'up' : 'down';
  if (value < 0) return polarity === 'higher' ? 'down' : 'up';
  return 'flat';
}

/** Tone for a raw signed change (growth, YoY). */
export function changeTone(v: number | null): 'up' | 'down' | 'flat' {
  if (v === null || !Number.isFinite(v)) return 'flat';
  if (v > 0) return 'up';
  if (v < 0) return 'down';
  return 'flat';
}

export const TONE_CLASS: Record<'up' | 'down' | 'flat', string> = {
  up: 'text-emerald-400',
  down: 'text-rose-400',
  flat: 'text-muted-foreground',
};

/** "FY2025" label from an ISO end date. */
export function fiscalLabel(endDate: string | null | undefined): string {
  if (!endDate) return '—';
  const m = endDate.match(/^(\d{4})/);
  return m ? `FY${m[1]}` : endDate;
}

/** Short month/year for chart axes ("Sep '25"). */
export function axisLabel(endDate: string): string {
  const ts = Date.parse(endDate);
  if (Number.isNaN(ts)) return endDate;
  const d = new Date(ts);
  return `${d.toLocaleString('en-US', { month: 'short', timeZone: 'UTC' })} '${String(d.getUTCFullYear()).slice(2)}`;
}
