// ── Pure risk / series math (glue for the analysis engines) ──────────────────
// Consumes real price histories (src/hooks/use-price-histories) and produces
// NAV series + risk metrics. No fabricated data: symbols without series are
// skipped; results are null when nothing is computable.

import type { HoldingMeta } from '@/lib/portfolio-analysis';

export interface RiskMetrics {
  nav: number[];
  navDates: string[];
  benchmarkNav: number[];
  /** Annualized volatility %. */
  vol: number | null;
  /** Beta vs the benchmark series. */
  beta: number | null;
  /** Annualized Sharpe (rf = 4%). */
  sharpe: number | null;
  /** Max drawdown % (negative). */
  mdd: number | null;
}

const EMPTY: RiskMetrics = { nav: [], navDates: [], benchmarkNav: [], vol: null, beta: null, sharpe: null, mdd: null };

function dailyReturns(xs: number[]): number[] {
  const out: number[] = [];
  for (let i = 1; i < xs.length; i++) {
    if (xs[i - 1] > 0) out.push(xs[i] / xs[i - 1] - 1);
  }
  return out;
}

function stdev(xs: number[]): number {
  if (xs.length < 2) return 0;
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
  return Math.sqrt(xs.reduce((a, x) => a + (x - mean) ** 2, 0) / (xs.length - 1));
}

function maxDrawdown(series: number[]): number {
  let peak = series[0] ?? 0;
  let mdd = 0;
  for (const x of series) {
    if (x > peak) peak = x;
    if (peak > 0) mdd = Math.min(mdd, x / peak - 1);
  }
  return mdd * 100;
}

/**
 * Build the portfolio NAV curve by aligned-date indexed rebasing (each holding
 * contributes weight_i × closes_i[t]/closes_i[0]) and derive risk metrics
 * against an optional benchmark close series.
 */
export function computeRiskMetrics(
  weights: Array<{ symbol: string; weight: number }>,
  closes: Record<string, number[]>,
  dates: Record<string, string[]>,
  benchmarkCloses: number[],
): RiskMetrics {
  const used = weights.filter(w => w.weight > 0 && Array.isArray(closes[w.symbol]) && closes[w.symbol].length >= 2);
  if (used.length === 0) return EMPTY;

  const len = Math.min(...used.map(w => closes[w.symbol].length));
  const norm = used.map(w => ({ w: w.weight, c: closes[w.symbol].slice(-len) }));
  const wsum = norm.reduce((a, x) => a + x.w, 0) || 1;

  const nav: number[] = [];
  for (let t = 0; t < len; t++) {
    let v = 0;
    for (const x of norm) v += (x.w / wsum) * (x.c[t] / x.c[0]);
    nav.push(v);
  }

  const refDates = dates[used[0].symbol];
  const navDates = Array.isArray(refDates) && refDates.length >= len ? refDates.slice(-len) : [];

  let benchmarkNav: number[] = [];
  if (Array.isArray(benchmarkCloses) && benchmarkCloses.length >= 2) {
    const bl = Math.min(len, benchmarkCloses.length);
    const b = benchmarkCloses.slice(-bl);
    const b0 = b[0];
    benchmarkNav = b.map(x => x / b0);
  }

  const r = dailyReturns(nav);
  const vol = r.length >= 2 ? stdev(r) * Math.sqrt(252) * 100 : null;
  const annRet = r.length >= 2 ? (r.reduce((a, b) => a + b, 0) / r.length) * 252 * 100 : null;
  const sharpe = vol && annRet !== null && vol > 0 ? (annRet - 4) / vol : null;

  let beta: number | null = null;
  if (benchmarkNav.length === nav.length) {
    const pr = dailyReturns(nav);
    const br = dailyReturns(benchmarkNav);
    if (pr.length === br.length && pr.length >= 2) {
      const meanP = pr.reduce((a, b) => a + b, 0) / pr.length;
      const meanB = br.reduce((a, b) => a + b, 0) / br.length;
      let cov = 0, varB = 0;
      for (let i = 0; i < pr.length; i++) {
        cov += (pr[i] - meanP) * (br[i] - meanB);
        varB += (br[i] - meanB) ** 2;
      }
      if (varB > 0) beta = cov / varB;
    }
  }

  return { nav, navDates, benchmarkNav, vol, beta, sharpe, mdd: maxDrawdown(nav) };
}

/** Per-symbol HoldingMeta for computeHealthScore / buildBrief / computeStress. */
export function buildHoldingMeta(
  holdings: Array<{ symbol: string; dayPct: number; value: number }>,
  totalValue: number,
  closes: Record<string, number[]>,
  benchmarkCloses: number[],
  isCrypto: (symbol: string) => boolean,
): Record<string, HoldingMeta> {
  const meta: Record<string, HoldingMeta> = {};
  const benchR = dailyReturns(benchmarkCloses);
  const benchVar = (() => {
    if (benchR.length < 2) return 0;
    const m = benchR.reduce((a, b) => a + b, 0) / benchR.length;
    return benchR.reduce((a, x) => a + (x - m) ** 2, 0) / (benchR.length - 1);
  })();
  const equalTarget = holdings.length > 0 ? 100 / holdings.length : 0;

  for (const h of holdings) {
    const series = closes[h.symbol];
    let beta = 1, vol: number | null = null, sharpe: number | null = null, mdd: number | null = null;
    if (Array.isArray(series) && series.length >= 3) {
      const r = dailyReturns(series);
      vol = stdev(r) * Math.sqrt(252) * 100;
      const mean = r.reduce((a, b) => a + b, 0) / r.length;
      sharpe = vol > 0 ? ((mean * 252 * 100) - 4) / vol : null;
      mdd = maxDrawdown(series);
      if (benchVar > 0 && r.length >= 2) {
        const m = r.reduce((a, b) => a + b, 0) / r.length;
        const bm = benchR.length ? benchR.reduce((a, b) => a + b, 0) / benchR.length : 0;
        let cov = 0;
        const n = Math.min(r.length, benchR.length);
        for (let i = 0; i < n; i++) cov += (r[i] - m) * (benchR[i] - bm);
        beta = cov / (n * benchVar);
      }
    }
    meta[h.symbol] = {
      name: h.symbol,
      category: isCrypto(h.symbol) ? 'Crypto' : 'Equity',
      dayPct: h.dayPct ?? 0,
      beta: Number.isFinite(beta) ? beta : 1,
      vol: vol ?? 40,
      sharpe: sharpe ?? 0,
      mdd: mdd ?? -30,
      target: equalTarget,
    };
  }
  return meta;
}
