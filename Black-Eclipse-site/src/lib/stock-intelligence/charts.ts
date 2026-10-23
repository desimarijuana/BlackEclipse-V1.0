// Pure chart builders for the stock-detail intelligence panel. They take real
// price bars and reported fundamentals, never synthesize a missing value, and
// return an explicit UNAVAILABLE chart with a reason when inputs are missing.

import type { EarningsEntry, FundamentalPeriod } from '@/lib/fundamentals/types';
import type {
  StockChart,
  StockChartSeries,
  StockProvenance,
  StockSourceRef,
  StockSourceTier,
} from './types';

export interface PriceClosePoint {
  date: string;
  close: number;
}

export interface BenchmarkRef {
  symbol: string;
  label: string;
}

const DAY_MS = 86_400_000;

function unavailable(
  id: StockChart['id'],
  title: string,
  subtitle: string,
  unit: StockChart['unit'],
  reason: string,
  sources: StockProvenance['sources'],
): StockChart {
  return {
    id,
    title,
    subtitle,
    unit,
    state: 'UNAVAILABLE',
    labels: [],
    series: [],
    provenance: { state: 'UNAVAILABLE', sources },
    reason,
  };
}

function yahooSource(id: string, label: string): StockProvenance['sources'][number] {
  return { id, label, tier: 'provider' };
}

function priceSource(ref: StockSourceRef | undefined, fallbackId: string, fallbackLabel: string): StockSourceRef {
  return ref ?? yahooSource(fallbackId, fallbackLabel);
}

/**
 * A 1Y close line. This is the first chart to become ready for most symbols and
 * deliberately does not depend on fundamentals or a benchmark.
 */
export function buildPriceTrend(
  bars: PriceClosePoint[],
  source: StockSourceRef,
  symbol = 'Stock',
  currency: string | null = null,
): StockChart {
  const prices = finiteBars(bars).slice(-260);
  if (prices.length < 2) {
    return unavailable(
      'price-trend',
      'Price trend',
      '1Y daily closes',
      'price',
      'Daily price history is unavailable for this symbol.',
      [source],
    );
  }
  const points = downsample(prices, 160);
  return {
    id: 'price-trend',
    title: 'Price trend',
    subtitle: `1Y daily closes${currency ? ` · ${currency}` : ''}`,
    unit: 'price',
    state: 'READY',
    labels: points.map((p) => p.date),
    series: [{ name: symbol, values: points.map((p) => round(p.close, 4)) }],
    provenance: { state: 'HISTORICAL', sources: [source] },
    note: 'Close price only; splits and dividends are shown as reported by the provider.',
  };
}

/**
 * Drawdown from the running 1Y high. This converts an unreliable-looking price
 * chart into a risk view that is still derived from the same real closes.
 */
export function buildDrawdown(
  bars: PriceClosePoint[],
  source: StockSourceRef,
): StockChart {
  const prices = finiteBars(bars).slice(-260);
  if (prices.length < 2) {
    return unavailable(
      'drawdown',
      'Drawdown',
      '1Y decline from the running high',
      'percent',
      'Daily price history is unavailable for this symbol.',
      [source],
    );
  }
  let peak = prices[0].close;
  const points = prices.map((bar) => {
    peak = Math.max(peak, bar.close);
    return { date: bar.date, drawdown: round((bar.close / peak - 1) * 100) };
  });
  const sampled = downsample(points, 160);
  return {
    id: 'drawdown',
    title: 'Drawdown',
    subtitle: '1Y decline from the running high',
    unit: 'percent',
    state: 'READY',
    labels: sampled.map((p) => p.date),
    series: [{ name: 'Drawdown', values: sampled.map((p) => p.drawdown) }],
    provenance: { state: 'DERIVED', sources: [source] },
    note: '0% is a new 1Y high; negative values are below that high.',
  };
}

/** Keep first and last points while bounding the payload for the client. */
function downsample<T>(rows: T[], maxPoints: number): T[] {
  if (rows.length <= maxPoints) return rows;
  const step = (rows.length - 1) / (maxPoints - 1);
  const out: T[] = [];
  for (let i = 0; i < maxPoints; i++) {
    const index = Math.round(i * step);
    out.push(rows[index]);
  }
  return out;
}

function round(value: number, digits = 2): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function finiteBars(bars: PriceClosePoint[]): PriceClosePoint[] {
  return bars
    .filter((bar) => typeof bar.date === 'string' && Number.isFinite(bar.close) && bar.close > 0)
    .slice()
    .sort((a, b) => a.date.localeCompare(b.date));
}

/**
 * Total return of the stock vs its home-market benchmark over the requested
 * window. Only dates present in BOTH series are used, so holidays and differing
 * exchange calendars cannot fake an out/under-performance gap.
 */
export function buildRelativePerformance(
  stockBars: PriceClosePoint[],
  benchmarkBars: PriceClosePoint[],
  benchmark: BenchmarkRef,
  months = 6,
  symbol = 'Stock',
  stockSource?: StockSourceRef,
  benchmarkSource?: StockSourceRef,
): StockChart {
  const sources = [
    priceSource(stockSource, 'stock-price', `${symbol} daily closes`),
    priceSource(benchmarkSource, 'benchmark-price', `${benchmark.label} daily closes`),
  ];
  const stock = finiteBars(stockBars);
  const bench = finiteBars(benchmarkBars);

  if (stock.length < 2 || bench.length < 2) {
    return unavailable(
      'relative-performance',
      `Relative performance vs ${benchmark.label}`,
      `${months}M total return, both rebased to 0%`,
      'percent',
      'Daily price history is not available for both the stock and its benchmark.',
      sources,
    );
  }

  const benchByDate = new Map(bench.map((bar) => [bar.date, bar.close]));
  const latest = stock[stock.length - 1].date;
  const cutoffMs = Date.parse(latest) - months * 30.44 * DAY_MS;
  const common = stock
    .filter((bar) => {
      const ms = Date.parse(bar.date);
      return Number.isFinite(ms) && ms >= cutoffMs && benchByDate.has(bar.date);
    })
    .map((bar) => ({ date: bar.date, stock: bar.close, benchmark: benchByDate.get(bar.date)! }));

  if (common.length < 8) {
    return unavailable(
      'relative-performance',
      `Relative performance vs ${benchmark.label}`,
      `${months}M total return, both rebased to 0%`,
      'percent',
      'Too few overlapping trading days to compare the stock with its benchmark.',
      sources,
    );
  }

  const points = downsample(common, 90);
  const stockBase = points[0].stock;
  const benchBase = points[0].benchmark;
  const series: StockChartSeries[] = [
    {
      name: symbol,
      values: points.map((p) => round((p.stock / stockBase - 1) * 100)),
    },
    {
      name: benchmark.label,
      values: points.map((p) => round((p.benchmark / benchBase - 1) * 100)),
    },
  ];

  return {
    id: 'relative-performance',
    title: `Relative performance vs ${benchmark.label}`,
    subtitle: `${months}M total return, both rebased to 0%`,
    unit: 'percent',
    state: 'READY',
    labels: points.map((p) => p.date),
    series,
    provenance: { state: 'HISTORICAL', sources },
    note: 'Total return from daily closes; no dividends or fees are included.',
  };
}

function nearestCloseOnOrBefore(
  bars: PriceClosePoint[],
  endDate: string,
  maxGapDays = 45,
): number | null {
  const endMs = Date.parse(endDate);
  if (!Number.isFinite(endMs)) return null;
  for (let i = bars.length - 1; i >= 0; i--) {
    const bar = bars[i];
    if (bar.date > endDate) continue;
    const gap = (endMs - Date.parse(bar.date)) / DAY_MS;
    if (Number.isFinite(gap) && gap >= 0 && gap <= maxGapDays) return bar.close;
    if (gap > maxGapDays) return null;
  }
  return null;
}

/**
 * Trailing P/E at each fiscal year-end, using the actual close nearest that
 * fiscal period end — not today's price applied backwards. Loss years are
 * excluded because a negative P/E is not meaningful on this axis.
 */
export function buildValuationBand(
  periods: FundamentalPeriod[],
  bars: PriceClosePoint[],
  sourceLabel: string,
  sourceTier: StockSourceTier,
  priceRef?: StockSourceRef,
): StockChart {
  const sources = [
    { id: 'fundamentals', label: sourceLabel, tier: sourceTier },
    priceSource(priceRef, 'price-history', 'Daily price closes'),
  ];
  const prices = finiteBars(bars);
  const points = periods
    .filter((period) => period.eps !== null && Number.isFinite(period.eps) && period.eps > 0)
    .map((period) => {
      const close = nearestCloseOnOrBefore(prices, period.endDate);
      if (close === null) return null;
      const pe = close / (period.eps as number);
      if (!Number.isFinite(pe) || pe <= 0 || pe > 500) return null;
      return { date: period.endDate, pe: round(pe) };
    })
    .filter((point): point is { date: string; pe: number } => point !== null)
    .sort((a, b) => a.date.localeCompare(b.date));

  if (points.length < 2) {
    return unavailable(
      'valuation-band',
      'Historical P/E',
      'Price at fiscal year-end ÷ reported EPS',
      'ratio',
      'At least two profitable fiscal years with matching price history are required.',
      sources,
    );
  }

  return {
    id: 'valuation-band',
    title: 'Historical P/E',
    subtitle: 'Price at fiscal year-end ÷ reported EPS',
    unit: 'ratio',
    state: 'READY',
    labels: points.map((p) => p.date),
    series: [{ name: 'Trailing P/E', values: points.map((p) => p.pe) }],
    provenance: { state: 'DERIVED', sources },
    note: 'Loss-making years are excluded. This is a historical multiple, not a forecast.',
  };
}

/**
 * Earnings surprise in percent, derived from actual vs consensus EPS already
 * retrieved by the fundamentals layer.
 */
export function buildEarningsSurprise(
  history: EarningsEntry[],
  sourceLabel: string,
  sourceTier: StockSourceTier,
): StockChart {
  const sources = [{ id: 'earnings-history', label: sourceLabel, tier: sourceTier }];
  const points = history
    .filter(
      (entry) =>
        entry.actual !== null && Number.isFinite(entry.actual) && entry.estimate !== null && Number.isFinite(entry.estimate) && Math.abs(entry.estimate) > 0,
    )
    .map((entry) => ({
      date: entry.date,
      surprise: round(((entry.actual as number) - (entry.estimate as number)) / Math.abs(entry.estimate as number) * 100),
    }))
    .filter((point) => Number.isFinite(point.surprise))
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(-8);

  if (points.length === 0) {
    return unavailable(
      'earnings-surprise',
      'Earnings surprise',
      'Actual EPS vs consensus estimate',
      'percent',
      'No reported actual-versus-estimate EPS pairs are available.',
      sources,
    );
  }

  return {
    id: 'earnings-surprise',
    title: 'Earnings surprise',
    subtitle: 'Actual EPS vs consensus estimate',
    unit: 'percent',
    state: 'READY',
    labels: points.map((p) => p.date),
    series: [{ name: 'Surprise', values: points.map((p) => p.surprise) }],
    provenance: { state: 'DERIVED', sources },
    note: 'Positive = reported EPS above consensus. Estimates are provider-reported, not Eclipse forecasts.',
  };
}
