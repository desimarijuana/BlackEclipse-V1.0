// Portfolio Decision Engine — pure, deterministic analysis functions.
//
// Everything here is a pure function of (holdings, metadata, inputs) so it can
// be unit-tested and reused by the UI without side effects. No network, no
// randomness, no fabricated market data. Where a metric cannot be supported by
// the available data (e.g. valuation/quality for crypto assets) it is reported
// as `null` rather than invented.

export interface HoldingMeta {
  name: string;
  category: string;
  dayPct: number; // 24h % change
  beta: number; // vs benchmark
  vol: number; // annualized volatility %
  sharpe: number;
  mdd: number; // max drawdown % (negative)
  target: number; // model target allocation %
  aiTag?: string;
}

export interface Holding {
  symbol: string;
  quantity: number;
  avgCost: number;
  currentPrice: number;
  value: number;
  unrealizedPnL: number;
  allocation: number; // % of portfolio
  realizedPnL: number;
}

export interface PortfolioTotals {
  totalValue: number;
  costBasis: number;
  unrealizedPnL: number;
  realizedPnL: number;
  roiPercent: number;
  dailyChangeValue: number;
  dailyChangePercent: number;
}

const clamp = (n: number, lo = 0, hi = 100) => Math.min(hi, Math.max(lo, n));

// ── Health score ────────────────────────────────────────────────────────────
// Transparent sub-scores, each 0–100 (higher = better). Valuation and Quality
// are not computable for crypto assets and are returned as null.
export interface HealthBreakdown {
  diversification: number;
  risk: number;
  momentum: number;
  concentration: number;
  valuation: number | null;
  quality: number | null;
}

export interface HealthScore {
  total: number;
  breakdown: HealthBreakdown;
}

export function computeHealthScore(
  holdings: Holding[],
  meta: Record<string, HoldingMeta>
): HealthScore {
  if (holdings.length === 0) {
    return {
      total: 0,
      breakdown: { diversification: 0, risk: 0, momentum: 0, concentration: 0, valuation: null, quality: null },
    };
  }
  const n = Math.max(holdings.length, 1);
  const totalValue = holdings.reduce((a, h) => a + h.value, 0) || 1;

  // Diversification: normalized inverse Herfindahl–Hirschman index.
  const hhi = holdings.reduce((a, h) => a + (h.value / totalValue) ** 2, 0);
  const diversification = n === 1 ? 0 : clamp(((1 - hhi) / (1 - 1 / n)) * 100);

  // Concentration: inverse of the largest position weight.
  const topWeight = holdings.length ? Math.max(...holdings.map(h => h.value / totalValue)) : 1;
  const concentration = clamp((1 - topWeight) * 100);

  // Risk: lower weighted volatility → higher score.
  const wVol = holdings.reduce((a, h) => a + (meta[h.symbol]?.vol ?? 60) * (h.value / totalValue), 0);
  const risk = clamp(100 - wVol);

  // Momentum: weighted 24h change mapped onto 0–100 (0 at −5%, 100 at +5%).
  const wDay = holdings.reduce((a, h) => a + (meta[h.symbol]?.dayPct ?? 0) * (h.value / totalValue), 0);
  const momentum = clamp(50 + wDay * 10);

  // Weighted total from the four supported sub-scores.
  const total = Math.round(
    diversification * 0.3 + risk * 0.3 + momentum * 0.2 + concentration * 0.2
  );

  return {
    total,
    breakdown: {
      diversification: Math.round(diversification),
      risk: Math.round(risk),
      momentum: Math.round(momentum),
      concentration: Math.round(concentration),
      valuation: null,
      quality: null,
    },
  };
}

// ── Eclipse Brief ───────────────────────────────────────────────────────────
// Deterministic, data-driven sentences. Never fabricates events.
export function buildBrief(
  totals: PortfolioTotals,
  holdings: Holding[],
  meta: Record<string, HoldingMeta>
): string[] {
  const lines: string[] = [];
  if (holdings.length === 0) {
    return ['Your portfolio is empty. Add a transaction to begin tracking performance.'];
  }

  const totalValue = totals.totalValue || 1;
  const day = totals.dailyChangeValue;
  const dayPct = totals.dailyChangePercent;

  lines.push(
    `Your portfolio is ${day >= 0 ? 'up' : 'down'} ${Math.abs(dayPct).toFixed(2)}% today (${day >= 0 ? '+' : ''}${fmtUsd(day)}).`
  );

  // Top contributors to today's move.
  const movers = [...holdings]
    .map(h => ({ symbol: h.symbol, day: (meta[h.symbol]?.dayPct ?? 0) }))
    .sort((a, b) => Math.abs(b.day) - Math.abs(a.day))
    .slice(0, 2);
  if (movers.length) {
    const names = movers.map(m => m.symbol).join(' and ');
    lines.push(`Today's move is led by ${names}.`);
  }

  // Concentration.
  const top = [...holdings].sort((a, b) => b.value - a.value)[0];
  if (top) {
    const w = (top.value / totalValue) * 100;
    if (w > 40) lines.push(`${top.symbol} is ${w.toFixed(1)}% of the portfolio — concentration is elevated.`);
  }

  // Drift vs target.
  const drifters = holdings
    .map(h => ({ symbol: h.symbol, drift: (h.value / totalValue) * 100 - (meta[h.symbol]?.target ?? 10) }))
    .filter(d => Math.abs(d.drift) >= 1.5)
    .sort((a, b) => Math.abs(b.drift) - Math.abs(a.drift));
  if (drifters.length) {
    const d = drifters[0];
    lines.push(`${d.symbol} is ${d.drift > 0 ? 'above' : 'below'} its target allocation by ${Math.abs(d.drift).toFixed(1)} pts.`);
  }

  // Volatility flag.
  const wVol = holdings.reduce((a, h) => a + (meta[h.symbol]?.vol ?? 60) * (h.value / totalValue), 0);
  if (wVol > 70) lines.push('Portfolio volatility is elevated relative to a balanced book.');

  return lines;
}

// ── What Changed ───────────────────────────────────────────────────────────
// Real, current-state deltas: allocation drift vs target, concentration level,
// today's movers, and risk posture. Each item links to a holding where relevant.
export interface ChangeItem {
  id: string;
  symbol: string | null;
  text: string;
  severity: 'positive' | 'negative' | 'neutral';
}

export function buildChanges(
  holdings: Holding[],
  meta: Record<string, HoldingMeta>
): ChangeItem[] {
  const changes: ChangeItem[] = [];
  const totalValue = holdings.reduce((a, h) => a + h.value, 0) || 1;

  // Allocation drift vs target.
  const drifters = holdings
    .map(h => ({ symbol: h.symbol, drift: (h.value / totalValue) * 100 - (meta[h.symbol]?.target ?? 10) }))
    .filter(d => Math.abs(d.drift) >= 1.5)
    .sort((a, b) => Math.abs(b.drift) - Math.abs(a.drift))
    .slice(0, 3);
  for (const d of drifters) {
    changes.push({
      id: `drift-${d.symbol}`,
      symbol: d.symbol,
      text: `${d.symbol} allocation ${d.drift > 0 ? '↑' : '↓'} ${Math.abs(d.drift).toFixed(1)} pts vs target`,
      severity: d.drift > 0 ? 'negative' : 'positive',
    });
  }

  // Today's movers.
  const movers = [...holdings]
    .map(h => ({ symbol: h.symbol, day: meta[h.symbol]?.dayPct ?? 0 }))
    .sort((a, b) => b.day - a.day);
  if (movers.length) {
    const best = movers[0];
    const worst = movers[movers.length - 1];
    if (best.day > 0) {
      changes.push({ id: 'mover-up', symbol: best.symbol, text: `${best.symbol} +${best.day.toFixed(2)}% today`, severity: 'positive' });
    }
    if (worst.day < 0 && worst.symbol !== best.symbol) {
      changes.push({ id: 'mover-down', symbol: worst.symbol, text: `${worst.symbol} ${worst.day.toFixed(2)}% today`, severity: 'negative' });
    }
  }

  // Concentration.
  const top = [...holdings].sort((a, b) => b.value - a.value)[0];
  if (top) {
    const w = (top.value / totalValue) * 100;
    if (w > 40) {
      changes.push({ id: 'concentration', symbol: top.symbol, text: `${top.symbol} concentration at ${w.toFixed(1)}%`, severity: 'negative' });
    }
  }

  return changes.slice(0, 5);
}

// ── Performance attribution ────────────────────────────────────────────────
export interface AttributionRow {
  symbol: string;
  dollar: number;
  pts: number; // contribution to total return in percentage points
}

export function computeAttribution(holdings: Holding[], costBasis: number): AttributionRow[] {
  const base = costBasis || 1;
  return holdings
    .map(h => ({ symbol: h.symbol, dollar: h.unrealizedPnL, pts: (h.unrealizedPnL / base) * 100 }))
    .sort((a, b) => b.dollar - a.dollar);
}

// ── Stress test ────────────────────────────────────────────────────────────
export interface StressScenario {
  id: string;
  label: string;
  desc: string;
  mkt: number; // market-wide shock %
  alt: number; // additional alt-coin shock %
}

export interface StressRow {
  symbol: string;
  pct: number;
  dollar: number;
}

export interface StressResult {
  rows: StressRow[];
  dollar: number;
  worstSymbol: string;
  worstPct: number;
}

export function computeStress(
  holdings: Holding[],
  meta: Record<string, HoldingMeta>,
  scenario: StressScenario,
  severity: number
): StressResult {
  const rows = holdings
    .map(h => {
      const m = meta[h.symbol];
      const beta = m?.beta ?? 1;
      const isMajor = ['BTC', 'ETH'].includes(h.symbol);
      const pct = (scenario.mkt * beta + scenario.alt * (isMajor ? 0.4 : 1.1)) * severity;
      return { symbol: h.symbol, pct, dollar: h.value * (pct / 100) };
    })
    .sort((a, b) => a.pct - b.pct);

  const dollar = rows.reduce((a, r) => a + r.dollar, 0);
  const worst = rows[0];
  return {
    rows,
    dollar,
    worstSymbol: worst?.symbol ?? '—',
    worstPct: worst?.pct ?? 0,
  };
}

// ── What-if trade ──────────────────────────────────────────────────────────
export interface WhatIfParams {
  symbol: string;
  side: 'Buy' | 'Sell';
  qty: number;
  cash: number;
}

export interface WhatIfResult {
  delta: number;
  cost: number;
  newCash: number;
  newWeight: number;
  oldWeight: number;
  newBeta: number;
  oldBeta: number;
  categoryDelta: number; // change in the traded asset's category exposure (pts)
  concentration: 'LOW' | 'MEDIUM' | 'HIGH';
}

export function computeWhatIf(
  holdings: Holding[],
  meta: Record<string, HoldingMeta>,
  params: WhatIfParams
): WhatIfResult {
  const totalValue = holdings.reduce((a, h) => a + h.value, 0) || 1;
  const price = holdings.find(h => h.symbol === params.symbol)?.currentPrice ?? 0;
  const holding = holdings.find(h => h.symbol === params.symbol);
  const heldQty = holding?.quantity ?? 0;
  const qty = Math.max(0, params.qty);
  const delta = params.side === 'Buy' ? qty : -Math.min(qty, heldQty);
  const cost = delta * price;
  const newCash = params.cash - cost;

  const newVal = ((holding?.quantity ?? 0) + delta) * price;
  const projTotal = totalValue + cost;
  const newWeight = projTotal > 0 ? (newVal / projTotal) * 100 : 0;
  const oldWeight = holding ? (holding.value / totalValue) * 100 : 0;

  const betaOf = (h: Holding) => meta[h.symbol]?.beta ?? 1;
  const oldBeta = holdings.reduce((a, h) => a + betaOf(h) * (h.value / totalValue), 0);
  const newBeta = holdings.reduce((a, h) => {
    const w = h.symbol === params.symbol ? newVal / (projTotal || 1) : h.value / (projTotal || 1);
    return a + betaOf(h) * w;
  }, 0) + (!holding && delta > 0 ? (meta[params.symbol]?.beta ?? 1) * (newVal / (projTotal || 1)) : 0);

  // Category exposure delta (percentage points of portfolio).
  const cat = meta[params.symbol]?.category ?? 'Other';
  const catBefore = holdings.filter(h => (meta[h.symbol]?.category ?? 'Other') === cat)
    .reduce((a, h) => a + h.value, 0) / totalValue * 100;
  const catAfter = (holdings.filter(h => (meta[h.symbol]?.category ?? 'Other') === cat)
    .reduce((a, h) => a + (h.symbol === params.symbol ? newVal : h.value), 0)) / (projTotal || 1) * 100;

  const concentration = newWeight > 40 ? 'HIGH' : newWeight > 25 ? 'MEDIUM' : 'LOW';

  return {
    delta, cost, newCash, newWeight, oldWeight, newBeta, oldBeta,
    categoryDelta: catAfter - catBefore,
    concentration,
  };
}

// ── Position sizing ────────────────────────────────────────────────────────
export interface SizingParams {
  accountValue: number;
  riskPct: number; // % of account risked per trade
  entry: number;
  stop: number;
  target: number;
}

export interface SizingResult {
  riskDollar: number;
  perUnit: number;
  units: number;
  posValue: number;
  maxLoss: number;
  potentialProfit: number;
  rr: number;
  allocationPct: number;
}

export function computePositionSize(p: SizingParams): SizingResult {
  const riskDollar = p.accountValue * (p.riskPct / 100);
  const perUnit = p.entry - p.stop;
  const units = perUnit > 0 ? riskDollar / perUnit : 0;
  const posValue = units * p.entry;
  const maxLoss = units * perUnit;
  const potentialProfit = units * (p.target - p.entry);
  const rr = perUnit > 0 ? (p.target - p.entry) / perUnit : 0;
  const allocationPct = p.accountValue > 0 ? (posValue / p.accountValue) * 100 : 0;
  return { riskDollar, perUnit, units, posValue, maxLoss, potentialProfit, rr, allocationPct };
}

// ── Monte Carlo projection ─────────────────────────────────────────────────
// Lognormal GBM closed-form percentiles (no simulation loop → deterministic).
export interface MonteCarloParams {
  totalValue: number;
  vol: number; // annualized volatility %
  years: number;
  monthly: number; // monthly contribution
  mu?: number; // expected annual return (default 0.45)
}

export interface MonteCarloResult {
  months: number[];
  p05: number[];
  p50: number[];
  p95: number[];
  end: { lo: number; mid: number; hi: number };
  totalContrib: number;
}

export function computeMonteCarlo(p: MonteCarloParams): MonteCarloResult {
  const mu = p.mu ?? 0.45;
  const sigma = p.vol / 100 || 0.6;
  const years = p.years;
  const monthly = Math.max(0, p.monthly);
  const steps = Math.max(12, years * 12);

  const proj = (z: number, tYears: number) => {
    const g = Math.exp((mu - 0.5 * sigma * sigma) * tYears + z * sigma * Math.sqrt(tYears));
    const annual = tYears > 0 ? Math.pow(g, 1 / tYears) - 1 : mu;
    const contrib = monthly * 12 * (annual !== 0 ? ((Math.pow(1 + annual, tYears) - 1) / annual) : tYears);
    return p.totalValue * g + contrib;
  };

  const months = Array.from({ length: steps + 1 }, (_, i) => i);
  const p05 = months.map(m => proj(-1.645, m / 12));
  const p50 = months.map(m => proj(0, m / 12));
  const p95 = months.map(m => proj(1.645, m / 12));
  const totalContrib = monthly * 12 * years;

  return {
    months, p05, p50, p95,
    end: { lo: p05[steps], mid: p50[steps], hi: p95[steps] },
    totalContrib,
  };
}

// ── Shared formatting (kept here so tests can assert on it) ────────────────
export function fmtUsd(n: number, dp = 2): string {
  return `${n < 0 ? '-' : ''}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp })}`;
}
export function fmtK(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e6) return `${n < 0 ? '-' : ''}$${(a / 1e6).toFixed(2)}M`;
  if (a >= 1000) return `$${Math.round(n / 1000)}k`;
  return `$${Math.round(n)}`;
}
export function fmtPct(n: number): string {
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}
