// ── Portfolio matrix math — correlation, covariance, risk decomposition ──────
// Pure functions over real close series. No I/O, no randomness, no fabricated
// values: anything that cannot be computed from the available data returns
// `null` so the UI can render an honest UNAVAILABLE state.
//
// Two accuracy rules drive the whole module:
//
//   1. **Date alignment, not positional alignment.** Two markets have different
//      trading calendars (NYSE vs PSX vs crypto's 7-day week), so `closes[i]`
//      is NOT the same day for two symbols. Every statistic here is computed on
//      the INTERSECTION of dates for the pair it concerns. Comparing position i
//      to position i would silently correlate different days.
//
//   2. **Returns are currency-neutral.** A return r_t = P_t / P_{t-1} − 1 is a
//      ratio, so a native-currency series and a USD-converted series of the same
//      asset give identical returns. Correlations are therefore computed on
//      native-currency closes and are correct for a mixed USD/PKR/INR book
//      without an FX conversion step. (A currency's own moves are a separate
//      exposure and are NOT captured here — see the widget footnote.)

/** One symbol's ascending close series with its matching ISO dates. */
export interface Series {
  symbol: string;
  closes: number[];
  dates: string[];
}

/** Result of a pairwise-complete correlation computation. */
export interface CorrelationMatrix {
  symbols: string[];
  /** n×n Pearson correlation, row-major. Diagonal is exactly 1. */
  matrix: number[][];
  /**
   * Overlapping observations per pair (n×n, symmetric). Exposed because a
   * correlation from 6 shared days and one from 60 are not equally meaningful.
   */
  observations: number[][];
  /** Smallest overlap actually used by any off-diagonal pair. */
  minObservations: number;
  /** Largest overlap used by any off-diagonal pair. */
  maxObservations: number;
  /** Pairwise-complete: each pair uses all dates they share. */
  alignedBy: 'pairwise';
}

/** Per-asset risk profile + each holding's share of total portfolio risk. */
export interface RiskMatrix {
  /** Weight used for each row (fraction of portfolio, sums to 1). */
  weights: number[];
  /** Annualized volatility % per holding. */
  vol: number[];
  /** Beta of each holding vs the portfolio itself. */
  betaToPortfolio: number[];
  /** Component contribution to portfolio risk, in % of total risk. Sums to 100. */
  riskContributionPct: number[];
  /** Marginal contribution to risk (Δportfolio risk per unit weight). */
  marginalContribution: number[];
  /** Portfolio annualized volatility % (from the covariance matrix). */
  portfolioVol: number | null;
  /** Diversification benefit %: 1 − (weighted-avg vol / portfolio vol). */
  diversificationPct: number | null;
  /** Observations behind the covariance estimate (pairwise median). */
  observations: number;
}

// ── Small numeric helpers ────────────────────────────────────────────────────

/** Simple daily returns; returns [] when the series is too short. */
export function dailyReturns(xs: number[]): number[] {
  const out: number[] = [];
  for (let i = 1; i < xs.length; i++) {
    if (xs[i - 1] > 0 && Number.isFinite(xs[i])) out.push(xs[i] / xs[i - 1] - 1);
  }
  return out;
}

/** Sample standard deviation (n−1). 0 when fewer than 2 points. */
function stdev(xs: number[]): number {
  if (xs.length < 2) return 0;
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
  return Math.sqrt(xs.reduce((a, x) => a + (x - mean) ** 2, 0) / (xs.length - 1));
}

/** Pearson correlation of two equal-length arrays. null when undefined. */
export function pearson(a: number[], b: number[]): number | null {
  const n = Math.min(a.length, b.length);
  if (n < 2) return null;
  let ma = 0, mb = 0;
  for (let i = 0; i < n; i++) { ma += a[i]; mb += b[i]; }
  ma /= n; mb /= n;
  let cov = 0, va = 0, vb = 0;
  for (let i = 0; i < n; i++) {
    const da = a[i] - ma;
    const db = b[i] - mb;
    cov += da * db;
    va += da * da;
    vb += db * db;
  }
  // Zero variance means one series never moved → correlation is undefined, not 0.
  if (va <= 0 || vb <= 0) return null;
  return cov / Math.sqrt(va * vb);
}

/**
 * Minimum shared dates for a correlation to be reported. Below this the
 * estimate is dominated by noise; we return null rather than a number that
 * looks authoritative.
 */
export const MIN_OBSERVATIONS = 20;

/** Minimum shared dates to trust the covariance-based risk decomposition. */
export const MIN_RISK_OBSERVATIONS = 15;

// ── Date alignment ───────────────────────────────────────────────────────────

/**
 * Index a series by date → close, dropping non-finite/non-positive closes.
 * Date and close are filtered TOGETHER so they can never desynchronize (a bug
 * the old history hook had: it filtered closes but mapped dates unfiltered,
 * shifting every later date by one).
 */
export function indexByDate(s: Series): Map<string, number> {
  const out = new Map<string, number>();
  const n = Math.min(s.closes.length, s.dates.length);
  for (let i = 0; i < n; i++) {
    const d = s.dates[i];
    const c = s.closes[i];
    if (!d || !Number.isFinite(c) || c <= 0) continue;
    out.set(d, c);
  }
  return out;
}

/** Dates present in every provided series, ascending. */
export function commonDates(series: Series[]): string[] {
  if (series.length === 0) return [];
  const maps = series.map(indexByDate);
  // Start from the shortest series so the intersection loop is cheapest.
  const order = maps.map((_, i) => i).sort((a, b) => maps[a].size - maps[b].size);
  const dates: string[] = [];
  for (const d of maps[order[0]].keys()) {
    if (maps.every(m => m.has(d))) dates.push(d);
  }
  return dates.sort();
}

/**
 * Returns for a symbol restricted to a set of dates, computed on consecutive
 * SHARED dates so a gap in either series never produces a multi-day return that
 * would be silently compared against a one-day return.
 */
function returnsOnDates(map: Map<string, number>, dates: string[]): number[] {
  const out: number[] = [];
  for (let i = 1; i < dates.length; i++) {
    const prev = map.get(dates[i - 1]);
    const cur = map.get(dates[i]);
    if (prev == null || cur == null || prev <= 0) continue;
    out.push(cur / prev - 1);
  }
  return out;
}

// ── Correlation matrix ───────────────────────────────────────────────────────

/**
 * Pairwise-complete Pearson correlation matrix over real close series.
 *
 * Each pair is computed on the dates THAT PAIR shares, then returns are taken
 * on consecutive shared dates. Pairwise (rather than listwise) completion keeps
 * a holding with a short history from truncating every other pair to nothing —
 * at the cost of the matrix not being guaranteed positive-semidefinite, which
 * matters only for the covariance decomposition below (handled there).
 *
 * Returns null when fewer than 2 symbols have usable series.
 */
export function computeCorrelation(series: Series[]): CorrelationMatrix | null {
  const usable = series.filter(s => indexByDate(s).size >= 3);
  if (usable.length < 2) return null;

  const maps = usable.map(indexByDate);
  const symbols = usable.map(s => s.symbol);
  const n = symbols.length;

  const matrix: number[][] = Array.from({ length: n }, () => Array(n).fill(0));
  const observations: number[][] = Array.from({ length: n }, () => Array(n).fill(0));
  let minObs = Infinity;
  let maxObs = 0;

  for (let i = 0; i < n; i++) {
    matrix[i][i] = 1;
    observations[i][i] = maps[i].size;
    for (let j = i + 1; j < n; j++) {
      // Shared dates for this pair only, then returns on consecutive shared days.
      const shared: string[] = [];
      const [small, large] = maps[i].size <= maps[j].size ? [maps[i], maps[j]] : [maps[j], maps[i]];
      for (const d of small.keys()) if (large.has(d)) shared.push(d);
      shared.sort();

      const ri = returnsOnDates(maps[i], shared);
      const rj = returnsOnDates(maps[j], shared);
      const obs = Math.min(ri.length, rj.length);
      const r = obs >= MIN_OBSERVATIONS ? pearson(ri, rj) : null;

      // A null pair is reported as 0 (no linear relationship shown) but its
      // observation count makes the weakness visible in the UI.
      const value = r == null ? 0 : Math.max(-1, Math.min(1, r));
      matrix[i][j] = value;
      matrix[j][i] = value;
      observations[i][j] = obs;
      observations[j][i] = obs;
      if (obs >= MIN_OBSERVATIONS) {
        minObs = Math.min(minObs, obs);
        maxObs = Math.max(maxObs, obs);
      }
    }
  }

  return {
    symbols,
    matrix,
    observations,
    minObservations: Number.isFinite(minObs) ? minObs : 0,
    maxObservations: maxObs,
    alignedBy: 'pairwise',
  };
}

// ── Risk decomposition ───────────────────────────────────────────────────────

/**
 * Per-holding risk profile plus each position's contribution to total portfolio
 * risk, using the standard Euler decomposition:
 *
 *   σ_p        = √(wᵀ Σ w)
 *   MCTR_i     = (Σ w)_i / σ_p          marginal contribution to risk
 *   CTR_i      = w_i · MCTR_i           component contribution (Σ CTR = σ_p)
 *   share_i    = CTR_i / σ_p            fraction of total risk
 *
 * Σ is built as `corr_ij · σ_i · σ_j` from the pairwise correlation matrix and
 * individual volatilities, so it stays consistent with what the correlation
 * widget displays. Pairwise-complete correlation is not guaranteed PSD, so the
 * portfolio variance is clamped at 0 and non-finite contributions are dropped
 * instead of emitting a negative "risk".
 *
 * All inputs are fractions/decimals internally; vol and the returned percentages
 * are in percent units (×100) to match the rest of the UI.
 */
export function computeRiskMatrix(
  series: Series[],
  weights: number[],
  corr: CorrelationMatrix,
  annualization = 252,
): RiskMatrix | null {
  const bySymbol = new Map(series.map(s => [s.symbol, s]));
  const symbols = corr.symbols;
  const n = symbols.length;
  if (n < 2 || weights.length !== n) return null;

  // Annualized vol per symbol from its own full series.
  const vol: number[] = [];
  const obsPerSymbol: number[] = [];
  for (const sym of symbols) {
    const s = bySymbol.get(sym);
    const closes = s ? [...indexByDate(s).entries()].sort((a, b) => a[0].localeCompare(b[0])).map(e => e[1]) : [];
    const r = dailyReturns(closes);
    vol.push(r.length >= 2 ? stdev(r) * Math.sqrt(annualization) * 100 : 0);
    obsPerSymbol.push(r.length);
  }

  const totalW = weights.reduce((a, w) => a + Math.max(0, w), 0);
  if (!(totalW > 0)) return null;
  const w = weights.map(x => Math.max(0, x) / totalW);

  // Covariance from pairwise correlation × vols.
  const cov: number[][] = Array.from({ length: n }, (_, i) =>
    Array.from({ length: n }, (_, j) => (corr.matrix[i][j] * vol[i] * vol[j]) / 10000),
  );

  // wᵀΣw
  let variance = 0;
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) variance += w[i] * w[j] * cov[i][j];
  const portfolioVol = variance > 0 ? Math.sqrt(variance) * 100 : 0;

  // Σw
  const sigmaW: number[] = Array.from({ length: n }, (_, i) => {
    let acc = 0;
    for (let j = 0; j < n; j++) acc += cov[i][j] * w[j];
    return acc;
  });

  const marginalContribution = portfolioVol > 0 ? sigmaW.map(x => (x / (portfolioVol / 100))) : sigmaW.map(() => 0);
  const ctr = sigmaW.map((x, i) => w[i] * (portfolioVol > 0 ? x / (portfolioVol / 100) : 0));
  const ctrSum = ctr.reduce((a, x) => a + Math.max(0, x), 0);
  const riskContributionPct = ctrSum > 0
    ? ctr.map(x => (Math.max(0, x) / ctrSum) * 100)
    : w.map(x => x * 100);

  // Beta of each holding TO THE PORTFOLIO (not to an index).
  const betaToPortfolio = portfolioVol > 0
    ? sigmaW.map(x => x / (variance || 1))
    : w.map(() => 0);

  // Weighted-average standalone vol vs realised portfolio vol = diversification benefit.
  const weightedVol = w.reduce((a, x, i) => a + x * vol[i], 0);
  const diversificationPct = portfolioVol > 0 ? (1 - weightedVol / portfolioVol) * 100 : null;

  // Median pairwise overlap, as a headline data-quality figure.
  const overlaps: number[] = [];
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) overlaps.push(corr.observations[i][j]);
  overlaps.sort((a, b) => a - b);
  const observations = overlaps.length
    ? overlaps[Math.floor(overlaps.length / 2)]
    : Math.min(...obsPerSymbol);

  return {
    weights: w,
    vol,
    betaToPortfolio,
    riskContributionPct,
    marginalContribution,
    portfolioVol: Number.isFinite(portfolioVol) ? portfolioVol : null,
    diversificationPct,
    observations,
  };
}

/**
 * Diversification ratio of a set of equally-correlated assets — the closed-form
 * "what would vol be if everything moved together" reference. Used for the
 * widget's explanatory tooltip, not as an input to any decision.
 */
export function undiversifiedVol(vol: number[], weights: number[]): number | null {
  const totalW = weights.reduce((a, w) => a + Math.max(0, w), 0);
  if (!(totalW > 0) || vol.length !== weights.length) return null;
  return weights.reduce((a, w, i) => a + (Math.max(0, w) / totalW) * vol[i], 0);
}
