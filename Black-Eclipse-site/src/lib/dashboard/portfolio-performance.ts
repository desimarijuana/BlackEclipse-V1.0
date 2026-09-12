// ── Aggregate portfolio performance (pure) ───────────────────────────────────
// Builds an indexed performance curve for ALL funds from the transaction ledger
// and REAL price histories. Holdings are valued at each date's close (last close
// on/before that date); a symbol without history falls back to its current live
// price (a flat contribution, never a fabricated trend). The portfolio and every
// selected comparison benchmark are indexed to 100 at the first date the
// portfolio holds value.

export interface PriceHistorySeries {
  dates: string[];
  closes: number[];
}

export interface BenchmarkSeries {
  symbol: string;
  /** Indexed to 100 at the same date as the portfolio. */
  data: number[];
}

export interface PerformanceSeries {
  dates: string[];
  /** Portfolio value indexed to 100 at the first holding date. */
  portfolio: number[];
  benchmarks: BenchmarkSeries[];
}

interface TxLike {
  type: string;
  symbol: string;
  quantity: number;
  price: number;
  fee: number;
  date: string;
}

function closeOnOrBefore(history: PriceHistorySeries, date: string): number | null {
  const { dates, closes } = history;
  if (!dates.length) return null;
  let lo = 0;
  let hi = dates.length - 1;
  let res = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (dates[mid] <= date) { res = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return res >= 0 ? closes[res] : null;
}

function longestDates(histories: Iterable<PriceHistorySeries>): string[] {
  let best: string[] = [];
  for (const h of histories) if (h.dates.length > best.length) best = h.dates;
  return best;
}

export function buildPortfolioPerformance(
  transactions: TxLike[],
  holdings: Map<string, PriceHistorySeries>,
  benchmarks: Array<{ symbol: string; history: PriceHistorySeries }>,
  fx: Map<string, number>,
  livePrice: Map<string, number>,
): PerformanceSeries {
  const empty: PerformanceSeries = { dates: [], portfolio: [], benchmarks: [] };
  const txs = [...transactions].sort((a, b) => a.date.localeCompare(b.date));

  // Daily axis: prefer a benchmark with history (typically SPY), else the
  // longest holding series.
  const benchWithHistory = benchmarks.find(b => b.history.dates.length >= 2);
  const axis = benchWithHistory?.history.dates
    ?? longestDates([...holdings.values(), ...benchmarks.map(b => b.history)]);
  if (axis.length < 2) return empty;

  const qty = new Map<string, number>();
  let ti = 0;
  const portfolio: number[] = [];
  const benchRaw: number[][] = benchmarks.map(() => []);
  const lastBench: number[] = benchmarks.map(() => NaN);

  for (const date of axis) {
    while (ti < txs.length && txs[ti].date <= date) {
      const t = txs[ti++];
      const s = t.symbol.toUpperCase();
      if (t.type === 'BUY') qty.set(s, (qty.get(s) ?? 0) + t.quantity);
      else if (t.type === 'SELL') qty.set(s, (qty.get(s) ?? 0) - t.quantity);
    }

    let value = 0;
    for (const [symbol, q] of qty) {
      if (q <= 0) continue;
      const h = holdings.get(symbol);
      const px = h ? closeOnOrBefore(h, date) : null;
      const price = px ?? livePrice.get(symbol) ?? 0;
      value += q * price * (fx.get(symbol) ?? 1);
    }
    portfolio.push(value);
    // Forward-fill benchmark closes so a missing trading day never creates a
    // gap in the comparison line.
    benchmarks.forEach((b, i) => {
      const v = closeOnOrBefore(b.history, date);
      if (v != null) lastBench[i] = v;
      benchRaw[i].push(lastBench[i]);
    });
  }

  // Anchor: first date the portfolio holds value and the first benchmark has a
  // price (so all lines start on the same day).
  const firstBench = benchRaw.find(arr => arr.some(v => Number.isFinite(v)));
  const start = portfolio.findIndex((v, i) => v > 0 && (!firstBench || Number.isFinite(firstBench[i])));
  if (start < 0) return empty;

  const dates = axis.slice(start);
  const pv = portfolio.slice(start);
  const p0 = pv[0] || 1;

  return {
    dates,
    portfolio: pv.map(v => +((v / p0) * 100).toFixed(2)),
    benchmarks: benchmarks.map((b, i) => {
      const raw = benchRaw[i].slice(start);
      const firstFinite = raw.findIndex(v => Number.isFinite(v));
      const fallback = firstFinite >= 0 ? raw[firstFinite] : 1;
      const filled = raw.map(v => (Number.isFinite(v) ? v : fallback));
      const base = filled[0] || 1;
      return { symbol: b.symbol, data: filled.map(v => +((v / base) * 100).toFixed(2)) };
    }),
  };
}
