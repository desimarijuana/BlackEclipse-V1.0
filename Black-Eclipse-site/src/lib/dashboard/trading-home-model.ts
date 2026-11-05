// Pure model for the Home dashboard's Trading section.
// Everything here is computed from broker-reported numbers (positions, fills,
// account) or journal analytics — nothing is invented, and no synthetic
// contract sizes are assumed. Keep this file free of React and fetch calls.

import type { BrokerAccount, BrokerFill, BrokerPosition } from '@/lib/harness/trading-client';

/** Local midnight for the given instant — the boundary for "today". */
export function startOfLocalDay(now: number): number {
  const date = new Date(now);
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

export interface TodayPnl {
  /** Sum of broker deals since local midnight (profit + swap + commission). */
  realized: number;
  /** Open P&L reported by the broker on the account (account.profit). */
  floating: number;
  total: number;
  dealCount: number;
}

export function computeTodayPnl(
  fills: BrokerFill[],
  floatingProfit: number | null,
  now: number = Date.now(),
): TodayPnl {
  const start = startOfLocalDay(now);
  const today = fills.filter((fill) => Number.isFinite(fill.dealtAt) && fill.dealtAt >= start);
  const realized = today.reduce(
    (sum, fill) => sum + (fill.profit || 0) + (fill.swap || 0) + (fill.commission || 0),
    0,
  );
  const floating = floatingProfit != null && Number.isFinite(floatingProfit) ? floatingProfit : 0;
  return { realized, floating, total: realized + floating, dealCount: today.length };
}

export interface SymbolExposureRow {
  symbol: string;
  /** Broker volume in lots (NOT comparable across asset classes). */
  volume: number;
  profit: number;
}

export type MarginHealth = 'healthy' | 'watch' | 'danger' | 'unavailable';

/**
 * Broker-reported margin level bands. These are display guidelines, not
 * trading advice: above 300% comfortably healthy, below 150% a call-risk
 * zone, below 100% the broker may start closing positions.
 */
export function marginHealth(marginLevel: number | null | undefined): MarginHealth {
  if (marginLevel == null || !Number.isFinite(marginLevel)) return 'unavailable';
  if (marginLevel < 100) return 'danger';
  if (marginLevel < 150) return 'watch';
  return 'healthy';
}

export interface ExposureSummary {
  openCount: number;
  netFloating: number;
  /** Sum |profit| across positions — scale of open risk, in account currency. */
  grossAbsFloating: number | null;
  /** margin / equity as a percentage, broker-reported. Null when unusable. */
  marginUsagePct: number | null;
  /** Broker-reported margin level (%). Null when not reported. */
  marginLevel: number | null;
  freeMargin: number | null;
  /** Positions aggregated per symbol, sorted by |profit| desc (top first). */
  bySymbol: SymbolExposureRow[];
}

export function computeExposure(
  positions: BrokerPosition[],
  account: BrokerAccount | null,
): ExposureSummary {
  const netFloating = positions.reduce((sum, position) => sum + (position.profit || 0), 0);
  const grossAbsFloating = positions.length
    ? positions.reduce((sum, position) => sum + Math.abs(position.profit || 0), 0)
    : null;

  const margin = account?.margin;
  const equity = account?.equity;
  const marginUsagePct =
    margin != null && equity != null && Number.isFinite(margin) && Number.isFinite(equity) && equity > 0
      ? (margin / equity) * 100
      : null;

  const marginLevel =
    account?.marginLevel != null && Number.isFinite(account.marginLevel) ? account.marginLevel : null;
  const freeMargin =
    account?.marginFree != null && Number.isFinite(account.marginFree) ? account.marginFree : null;

  const bySymbolMap = new Map<string, SymbolExposureRow>();
  for (const position of positions) {
    const key = position.symbol;
    const row = bySymbolMap.get(key) ?? { symbol: key, volume: 0, profit: 0 };
    row.volume += position.volume || 0;
    row.profit += position.profit || 0;
    bySymbolMap.set(key, row);
  }
  const bySymbol = [...bySymbolMap.values()].sort(
    (a, b) => Math.abs(b.profit) - Math.abs(a.profit) || b.volume - a.volume,
  );

  return {
    openCount: positions.length,
    netFloating,
    grossAbsFloating,
    marginUsagePct,
    marginLevel,
    freeMargin,
    bySymbol,
  };
}

export interface SeriesPoint {
  /** Local calendar day key (YYYY-MM-DD). */
  day: string;
  /** Cumulative realized P&L at the close of that day, in account currency. */
  value: number;
}

export interface RealizedSeries {
  points: SeriesPoint[];
  /** Broker deals that fall inside the window. */
  dealCount: number;
  firstDay: string | null;
  lastDay: string | null;
}

function dayKey(ms: number): string {
  const date = new Date(ms);
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

/**
 * Cumulative realized P&L per local calendar day, built from the broker's deals.
 * This is NOT an equity curve: Eclipse stores no balance history, and floating
 * P&L is a single current number. Days with no deals carry the previous value
 * forward so the line is continuous rather than inventing gaps.
 */
export function buildDailyRealized(
  fills: BrokerFill[],
  now: number = Date.now(),
  days = 30,
): RealizedSeries {
  const count = Math.max(2, Math.floor(days));
  const end = new Date(now);
  end.setHours(0, 0, 0, 0);
  const start = new Date(end);
  start.setDate(start.getDate() - (count - 1));

  const deltas = new Map<string, number>();
  let dealCount = 0;
  for (const fill of fills) {
    if (!Number.isFinite(fill.dealtAt) || fill.dealtAt < start.getTime()) continue;
    dealCount += 1;
    const key = dayKey(fill.dealtAt);
    deltas.set(key, (deltas.get(key) ?? 0) + (fill.profit || 0) + (fill.swap || 0) + (fill.commission || 0));
  }

  const points: SeriesPoint[] = [];
  let cumulative = 0;
  const cursor = new Date(start);
  for (let index = 0; index < count; index += 1) {
    const key = dayKey(cursor.getTime());
    cumulative += deltas.get(key) ?? 0;
    points.push({ day: key, value: cumulative });
    cursor.setDate(cursor.getDate() + 1);
  }

  return {
    points,
    dealCount,
    firstDay: points[0]?.day ?? null,
    lastDay: points[points.length - 1]?.day ?? null,
  };
}

/** Keep the most recent `maxPoints` entries (journal curves can be long). */
export function trimSeries<T>(points: T[], maxPoints: number): T[] {
  if (maxPoints <= 0) return [];
  return points.length <= maxPoints ? points : points.slice(points.length - maxPoints);
}
