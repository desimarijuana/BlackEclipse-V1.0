import type { HeatmapPayload } from '@/lib/heatmap';
import type { RegimeResult } from '@/lib/regime/types';

export type TrendClass = 'uptrend' | 'weak_uptrend' | 'downtrend' | 'unknown';
export type Tone = 'bullish' | 'bearish' | 'neutral' | 'unavailable';
export type SectorTone = 'leading' | 'improving' | 'weakening' | 'lagging';

export interface RawHolding {
  symbol: string;
  name: string;
  valueUsd: number;
  valueNative: number;
  currency: string;
  marketId: string;
  sector?: string;
  changePercent: number;
  closes: number[];
  dates?: string[];
  avgCost?: number;
  quantity?: number;
  unrealizedPct?: number | null;
  fxMissing?: boolean;
}

export interface HomeHolding extends RawHolding {
  sector: string;
  weightPct: number;
  trend: TrendClass;
  momentum20: number | null;
}

export interface TrendMix {
  uptrend: number;
  weakUptrend: number;
  downtrend: number;
  unknown: number;
  knownPct: number;
}

export interface HealthScore {
  score: number | null;
  label: 'Excellent' | 'Strong' | 'Mixed' | 'Weak' | 'Fragile' | 'Unavailable';
  coveragePct: number;
  topWeightPct: number;
  penalty: number;
}

export interface SectorInput {
  name: string;
  change: number;
  weight: number;
  stocks: number;
  topSymbol?: string;
  topName?: string;
  topChange?: number;
}

export interface SectorSignal extends SectorInput {
  relative: number;
  tone: SectorTone;
}

export interface SectorBreadth {
  tracked: number;
  advancing: number;
  beating: number;
}

export interface SectorSlice {
  name: string;
  valueUsd: number;
  weightPct: number;
}

export interface Concentration {
  slices: SectorSlice[];
  sectorCount: number;
  topSharePct: number;
  topSector: string | null;
  diversified: boolean;
}

export interface RadarRow {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
  currency: string;
  marketId: string;
}

export interface Brief {
  headline: string;
  detail: string;
  tone: Tone;
}

export interface BriefInput {
  tone: Tone;
  health: HealthScore;
  review: HomeHolding[];
  leading: SectorSignal | null;
  radar: RadarRow[];
  holdings: number;
  marketLabel: string;
  tracked: number;
  trackedLabel: 'markets' | 'sectors';
  advancing: number;
  positionsLoading?: boolean;
  historyLoading?: boolean;
}

const HEALTH_SCORE: Record<TrendClass, number> = {
  uptrend: 100,
  weak_uptrend: 62,
  downtrend: 24,
  unknown: 0,
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

export function mean(values: number[]): number | null {
  const usable = values.filter(finite);
  if (usable.length === 0) return null;
  return usable.reduce((sum, value) => sum + value, 0) / usable.length;
}

export function sma(values: number[], period: number): number | null {
  if (period <= 0 || values.length < period) return null;
  return mean(values.slice(-period));
}

export function trendOf(closes: number[]): TrendClass {
  const usable = closes.filter((value) => finite(value) && value > 0);
  if (usable.length < 30) return 'unknown';
  const last = usable[usable.length - 1];
  const short = sma(usable, 20);
  const long = sma(usable, Math.min(50, usable.length));
  if (last == null || short == null || long == null) return 'unknown';
  if (last > short && short > long) return 'uptrend';
  if (last > long) return 'weak_uptrend';
  return 'downtrend';
}

export function momentum(closes: number[], period: number): number | null {
  if (closes.length <= period) return null;
  const start = closes[closes.length - 1 - period];
  const end = closes[closes.length - 1];
  if (!finite(start) || start <= 0 || !finite(end)) return null;
  return (end / start - 1) * 100;
}

export function buildHomeHoldings(raw: RawHolding[], market: string): HomeHolding[] {
  const wanted = market.trim().toUpperCase();
  const scoped = wanted === 'GLOBAL'
    ? raw
    : raw.filter((holding) => holding.marketId.toUpperCase() === wanted);
  const total = scoped.reduce((sum, holding) => sum + (finite(holding.valueUsd) ? holding.valueUsd : 0), 0);
  return scoped.map((holding) => ({
    ...holding,
    sector: holding.sector?.trim() || 'Unclassified',
    weightPct: total > 0 ? (holding.valueUsd / total) * 100 : 0,
    trend: trendOf(holding.closes),
    momentum20: momentum(holding.closes, 20),
  }));
}

export function buildTrendMix(holdings: HomeHolding[]): TrendMix {
  const totals: Record<TrendClass, number> = { uptrend: 0, weak_uptrend: 0, downtrend: 0, unknown: 0 };
  for (const holding of holdings) totals[holding.trend] += holding.weightPct;
  const knownPct = clamp(totals.uptrend + totals.weak_uptrend + totals.downtrend, 0, 100);
  return {
    uptrend: totals.uptrend,
    weakUptrend: totals.weak_uptrend,
    downtrend: totals.downtrend,
    unknown: totals.unknown,
    knownPct,
  };
}

export function buildHealth(holdings: HomeHolding[]): HealthScore {
  const known = holdings.filter((holding) => holding.trend !== 'unknown');
  const coveragePct = holdings.reduce((sum, holding) => sum + holding.weightPct, 0) > 0
    ? (known.reduce((sum, holding) => sum + holding.weightPct, 0) / holdings.reduce((sum, holding) => sum + holding.weightPct, 0)) * 100
    : 0;
  const topWeightPct = holdings.reduce((max, holding) => Math.max(max, holding.weightPct), 0);
  const penalty = clamp((topWeightPct - 35) * 0.5, 0, 8);
  if (coveragePct < 30) {
    return { score: null, label: 'Unavailable', coveragePct, topWeightPct, penalty };
  }
  const knownWeight = known.reduce((sum, holding) => sum + holding.weightPct, 0);
  const weighted = knownWeight > 0
    ? known.reduce((sum, holding) => sum + HEALTH_SCORE[holding.trend] * holding.weightPct, 0) / knownWeight
    : 0;
  const score = Math.round(clamp(weighted - penalty, 0, 100));
  const label: HealthScore['label'] =
    score >= 85 ? 'Excellent'
      : score >= 70 ? 'Strong'
        : score >= 55 ? 'Mixed'
          : score >= 40 ? 'Weak'
            : 'Fragile';
  return { score, label, coveragePct, topWeightPct, penalty };
}

export function sectorSignals(sectors: SectorInput[], marketChange: number): SectorSignal[] {
  return sectors
    .map((sector) => {
      const relative = sector.change - marketChange;
      const tone: SectorTone =
        relative > 0 && sector.change > 0 ? 'leading'
          : relative > 0 ? 'improving'
            : sector.change > 0 ? 'weakening'
              : 'lagging';
      return { ...sector, relative, tone };
    })
    .sort((a, b) => b.relative - a.relative || b.change - a.change);
}

export function sectorBreadth(signals: SectorSignal[]): SectorBreadth {
  return {
    tracked: signals.length,
    advancing: signals.filter((signal) => signal.change > 0).length,
    beating: signals.filter((signal) => signal.relative > 0).length,
  };
}

export function leadingSignal(signals: SectorSignal[]): SectorSignal | null {
  return signals.find((signal) => signal.weight > 0 && signal.stocks > 0) ?? signals[0] ?? null;
}

export function buildConcentration(holdings: HomeHolding[], limit = 4): Concentration {
  const bySector = new Map<string, SectorSlice>();
  for (const holding of holdings) {
    const current = bySector.get(holding.sector) ?? { name: holding.sector, valueUsd: 0, weightPct: 0 };
    current.valueUsd += holding.valueUsd;
    current.weightPct += holding.weightPct;
    bySector.set(holding.sector, current);
  }
  const sorted = [...bySector.values()].sort((a, b) => b.weightPct - a.weightPct);
  const top = sorted.slice(0, limit);
  const rest = sorted.slice(limit);
  if (rest.length > 0) {
    top.push({
      name: 'Other',
      valueUsd: rest.reduce((sum, slice) => sum + slice.valueUsd, 0),
      weightPct: rest.reduce((sum, slice) => sum + slice.weightPct, 0),
    });
  }
  const topSharePct = sorted[0]?.weightPct ?? 0;
  return {
    slices: top,
    sectorCount: sorted.length,
    topSharePct,
    topSector: sorted[0]?.name ?? null,
    diversified: sorted.length >= 4 && topSharePct <= 40,
  };
}

export function regimeTone(regime: RegimeResult | null): Tone {
  if (!regime || !regime.coreAvailable || !finite(regime.score)) return 'unavailable';
  if (regime.score >= 0.35) return 'bullish';
  if (regime.score <= -0.35) return 'bearish';
  return 'neutral';
}

export function weatherTone(marketChange: number, advancing: number, tracked: number): Tone {
  if (tracked <= 0) return 'unavailable';
  const breadth = advancing / tracked;
  if (marketChange > 0.15 && breadth >= 0.55) return 'bullish';
  if (marketChange < -0.15 && breadth <= 0.45) return 'bearish';
  if (breadth >= 0.6) return 'bullish';
  if (breadth <= 0.35) return 'bearish';
  return 'neutral';
}

export function regimeNeedle(regime: RegimeResult | null): number | null {
  if (!regime || !finite(regime.score)) return null;
  return clamp(((regime.score + 1) / 2) * 100, 0, 100);
}

export function buildRadar(quotes: RadarRow[], held: ReadonlySet<string>, limit = 4): RadarRow[] {
  return quotes
    .filter((quote) => quote.price > 0 && !held.has(quote.symbol.toUpperCase()))
    .sort((a, b) => Math.abs(b.changePercent) - Math.abs(a.changePercent))
    .slice(0, limit);
}

function signed(value: number, digits = 2): string {
  const rounded = Number(value.toFixed(digits));
  return `${rounded >= 0 ? '+' : ''}${rounded}%`;
}

export function buildPersonalBrief(input: BriefInput): Brief {
  const reviewCount = input.review.length;
  const headline = reviewCount > 0
    ? `${reviewCount} holding${reviewCount === 1 ? '' : 's'} need${reviewCount === 1 ? 's' : ''} review`
    : input.tone === 'bullish' ? 'Markets are constructive'
      : input.tone === 'bearish' ? 'Markets are defensive'
        : input.tone === 'neutral' ? 'Signals are mixed'
          : 'Market read is unavailable';

  const parts: string[] = [];
  if (input.leading) {
    parts.push(`${input.leading.name} leads at ${signed(input.leading.change)}.`);
  } else {
    parts.push(`Leadership data is unavailable for ${input.marketLabel}.`);
  }
  if (input.positionsLoading) {
    parts.push('Live position values are still loading.');
  } else if (input.historyLoading) {
    parts.push('Trend history is still loading.');
  } else if (input.health.score != null) {
    parts.push(`Trend health is ${input.health.label.toLowerCase()} at ${input.health.score}/100.`);
  } else if (input.holdings === 0) {
    parts.push('Add holdings to unlock portfolio health.');
  } else {
    parts.push('Portfolio health is unavailable — trend history is missing.');
  }
  if (input.radar[0]) {
    parts.push(`${input.radar[0].symbol} leads the watchlist at ${signed(input.radar[0].changePercent)}.`);
  }
  if (input.tracked > 0) {
    parts.push(`${input.advancing}/${input.tracked} tracked ${input.trackedLabel} are advancing.`);
  }
  return { headline, detail: parts.slice(0, 3).join(' '), tone: input.tone };
}

// ── AlphaGen-style Home model ───────────────────────────────────────────────

export type HoldingState = 'healthy' | 'sideways' | 'broken' | 'falling' | 'unknown';

export interface HealthRow extends HomeHolding {
  state: HoldingState;
  distanceToWeakPct: number | null;
  fallingDays: number;
  unrealizedPct: number | null;
}

export interface HoldingsHealthSummary {
  rows: HealthRow[];
  counts: Record<HoldingState, number>;
  weight: Record<HoldingState, number>;
  total: number;
  healthyWeightPct: number;
  turningWeak: HealthRow | null;
}

export interface PortfolioBenchmarkPoint {
  date: string;
  portfolio: number;
  benchmark: number;
}

export interface FeedItem {
  id: string;
  kind: 'news' | 'alert' | 'earnings' | 'market' | 'sector';
  title: string;
  detail?: string;
  symbol?: string;
  market?: string;
  tag: 'You own' | 'Watching' | 'Market';
  at: number;
}

export interface WeekEvent {
  id: string;
  date: string;
  dayLabel: string;
  title: string;
  subtitle?: string;
  symbol?: string;
  kind: 'earnings' | 'macro';
  tag: string;
}

export interface PulseMover {
  symbol: string;
  name: string;
  market: string;
  changePct: number;
}

export interface MarketPulseData {
  scopeLabel: string;
  indexChange: number;
  advancing: number;
  declining: number;
  tracked: number;
  leading: SectorSignal | null;
  sectors: SectorSignal[];
  movers: PulseMover[];
}

export interface LeaderRow {
  symbol: string;
  name: string;
  market: string;
  marketId: string;
  changePct: number;
  score: number;
  reason: string;
}

export interface ResultsWindow {
  date: string;
  label: string;
  count: number;
  symbols: string[];
}

export interface ResultsSeason {
  upcoming: number;
  next7: number;
  windows: ResultsWindow[];
  source: string;
}

export interface ResearchRow {
  id: string;
  symbol: string;
  title: string;
  status: string;
  updatedAt: string;
  watching: boolean;
}

export interface RecordSummary {
  hasData: boolean;
  totalTrades: number;
  winRate: number;
  netPnl: number;
  profitFactor: number;
  closedTheses: number;
  activeTheses: number;
}

export interface OverviewGroupLike {
  id: string;
  country: string;
  name?: string;
  index?: { changePct: number } | null;
  stocks: Array<{ symbol: string; name: string; changePct: number; marketCap?: number | null }>;
}

export interface NewsLike {
  id: string;
  ticker?: string | null;
  headline: string;
  summary?: string | null;
  sentiment?: string;
  timestamp: string;
  source?: string;
}

export interface AlertLike {
  id: string;
  name: string;
  symbols: string[];
  lastFiredAt: string | null;
}

export interface EarningsLike {
  symbol: string;
  name: string;
  date: string;
  time?: 'BMO' | 'AMC' | null;
  epsActual?: number | null;
  epsEstimate?: number | null;
}

export interface EconEventLike {
  id: string;
  date: string;
  country: string;
  title: string;
  importance: 'high' | 'medium' | 'low';
}

export interface ThesisLike {
  id: string;
  symbol: string;
  title: string;
  status: string;
  updatedAt: string;
  companyName?: string | null;
}

export interface JournalPerformanceLike {
  totalTrades: number;
  winRate: number;
  netPnl: number;
  profitFactor: number;
}

function dayStart(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

function parseDay(date: string): number {
  const value = Date.parse(date.length === 10 ? `${date}T00:00:00` : date);
  return Number.isFinite(value) ? value : NaN;
}

function dayLabel(date: string, now = new Date()): string {
  const ts = parseDay(date);
  if (!Number.isFinite(ts)) return date;
  const today = dayStart(now);
  const diff = Math.round((ts - today) / 86_400_000);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Tomorrow';
  return new Date(ts).toLocaleDateString('en-US', { weekday: 'short', day: 'numeric', month: 'short' });
}

function closeOnOrBefore(closes: number[], dates: string[] | undefined, date: string): number | null {
  if (!dates || dates.length !== closes.length || closes.length === 0) return null;
  let lo = 0;
  let hi = dates.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (dates[mid] <= date) { found = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return found >= 0 ? closes[found] : null;
}

export function buildHoldingsHealth(holdings: HomeHolding[]): HoldingsHealthSummary {
  const counts: Record<HoldingState, number> = { healthy: 0, sideways: 0, broken: 0, falling: 0, unknown: 0 };
  const weight: Record<HoldingState, number> = { healthy: 0, sideways: 0, broken: 0, falling: 0, unknown: 0 };

  const rows: HealthRow[] = holdings.map((holding) => {
    const closes = holding.closes;
    const last = closes.length > 0 ? closes[closes.length - 1] : null;
    const s20 = sma(closes, 20);
    const s50 = sma(closes, 50);
    const s200 = sma(closes, 200);
    const mom20 = momentum(closes, 20);
    let state: HoldingState = 'unknown';
    if (closes.length >= 30 && last != null && s50 != null) {
      if (s20 != null && last > s20 && s20 > s50 && (mom20 ?? 0) > 0) state = 'healthy';
      else if (last > s50) state = 'sideways';
      else if ((s200 != null && last > s200) || (mom20 ?? 0) > -3) state = 'broken';
      else state = 'falling';
    }

    let fallingDays = 0;
    for (let index = closes.length - 1; index >= 19; index -= 1) {
      const average = mean(closes.slice(index - 19, index + 1));
      if (average == null || closes[index] >= average) break;
      fallingDays += 1;
    }

    const distanceToWeakPct = (state === 'healthy' || state === 'sideways') && last != null && s50 != null && s50 > 0
      ? ((last - s50) / s50) * 100
      : null;
    const unrealizedPct = typeof holding.unrealizedPct === 'number' && Number.isFinite(holding.unrealizedPct)
      ? holding.unrealizedPct
      : null;
    return { ...holding, state, distanceToWeakPct, fallingDays, unrealizedPct };
  });

  for (const row of rows) {
    counts[row.state] += 1;
    weight[row.state] += row.weightPct;
  }
  const totalWeight = rows.reduce((sum, row) => sum + row.weightPct, 0);
  const turningWeak = rows
    .filter((row) => (row.state === 'healthy' || row.state === 'sideways') && row.distanceToWeakPct != null)
    .sort((a, b) => (a.distanceToWeakPct ?? Infinity) - (b.distanceToWeakPct ?? Infinity))[0] ?? null;

  return {
    rows,
    counts,
    weight,
    total: rows.length,
    healthyWeightPct: totalWeight > 0 ? (weight.healthy / totalWeight) * 100 : 0,
    turningWeak,
  };
}

export function buildPortfolioVsBenchmark(
  holdings: HomeHolding[],
  benchmark: { dates: string[]; closes: number[] } | null,
): PortfolioBenchmarkPoint[] {
  if (!benchmark || benchmark.dates.length < 2 || benchmark.closes.length < 2) return [];
  const usable = holdings.filter((holding) => holding.closes.length >= 2 && holding.weightPct > 0);
  if (usable.length === 0) return [];

  const dates = benchmark.dates.slice(Math.max(0, benchmark.dates.length - 90));
  if (dates.length < 2) return [];
  const firstDate = dates[0];
  const bases = usable.map((holding) => {
    const base = closeOnOrBefore(holding.closes, holding.dates, firstDate) ?? holding.closes[0];
    return { holding, base };
  }).filter((item) => Number.isFinite(item.base) && item.base > 0);
  if (bases.length === 0) return [];

  const benchBase = closeOnOrBefore(benchmark.closes, benchmark.dates, firstDate)
    ?? benchmark.closes.find((value) => Number.isFinite(value) && value > 0)
    ?? null;
  if (benchBase == null || benchBase <= 0) return [];

  const points: PortfolioBenchmarkPoint[] = [];
  for (const date of dates) {
    let weighted = 0;
    let weights = 0;
    for (const { holding, base } of bases) {
      const close = closeOnOrBefore(holding.closes, holding.dates, date);
      if (close == null || close <= 0) continue;
      weighted += (close / base) * holding.weightPct;
      weights += holding.weightPct;
    }
    const bench = closeOnOrBefore(benchmark.closes, benchmark.dates, date);
    if (weights <= 0 || bench == null || bench <= 0) continue;
    points.push({
      date,
      portfolio: +((weighted / weights) * 100).toFixed(2),
      benchmark: +((bench / benchBase) * 100).toFixed(2),
    });
  }
  return points;
}

export function buildMarketPulse(input: {
  market: string;
  marketLabel: string;
  overview: OverviewGroupLike[];
  heatmap: HeatmapPayload | null;
  signals: SectorSignal[];
  breadth: SectorBreadth;
  marketChange: number;
  leading: SectorSignal | null;
}): MarketPulseData {
  if (input.market === 'GLOBAL') {
    const withIndex = input.overview.filter((group) => group.index && Number.isFinite(group.index.changePct));
    const changes = withIndex.map((group) => group.index!.changePct);
    const movers = input.overview
      .flatMap((group) => group.stocks.map((stock) => ({
        symbol: stock.symbol,
        name: stock.name,
        market: group.name || group.country,
        changePct: stock.changePct,
      })))
      .filter((stock) => Math.abs(stock.changePct) <= 20)
      .sort((a, b) => Math.abs(b.changePct) - Math.abs(a.changePct))
      .slice(0, 5);
    return {
      scopeLabel: 'Global markets',
      indexChange: mean(changes) ?? 0,
      advancing: changes.filter((change) => change > 0).length,
      declining: changes.filter((change) => change < 0).length,
      tracked: changes.length,
      leading: input.leading,
      sectors: input.signals.slice(0, 6),
      movers,
    };
  }

  const sectors = input.heatmap?.sectors ?? [];
  const stocks = sectors.flatMap((sector) => sector.stocks);
  const movers = stocks
    .map((stock) => ({ symbol: stock.symbol, name: stock.name, market: stock.sector, changePct: stock.changePct }))
    .filter((stock) => Math.abs(stock.changePct) <= 20)
    .sort((a, b) => Math.abs(b.changePct) - Math.abs(a.changePct))
    .slice(0, 5);
  return {
    scopeLabel: input.marketLabel,
    indexChange: input.marketChange,
    advancing: stocks.filter((stock) => stock.changePct > 0).length,
    declining: stocks.filter((stock) => stock.changePct < 0).length,
    tracked: stocks.length,
    leading: input.leading,
    sectors: input.signals.slice(0, 6),
    movers,
  };
}

export function buildLeaders(
  overview: OverviewGroupLike[],
  held: ReadonlySet<string>,
  watching: ReadonlySet<string>,
  limit = 4,
): LeaderRow[] {
  const rows: LeaderRow[] = [];
  for (const group of overview) {
    group.stocks.forEach((stock, index) => {
      const symbol = stock.symbol.toUpperCase();
      if (held.has(symbol) || watching.has(symbol)) return;
      const indexChange = group.index?.changePct ?? 0;
      const score = Math.round(clamp(
        50 + clamp(stock.changePct * 8, -25, 25) + (indexChange > 0 ? 10 : indexChange < 0 ? -10 : 0) + (index < 3 ? 8 : 0),
        0,
        100,
      ));
      rows.push({
        symbol: stock.symbol,
        name: stock.name,
        market: group.name || group.country,
        marketId: group.id,
        changePct: stock.changePct,
        score,
        reason: indexChange > 0 ? 'Market advancing' : indexChange < 0 ? 'Outperforming a weak market' : 'Market flat',
      });
    });
  }
  return rows.sort((a, b) => b.score - a.score || b.changePct - a.changePct).slice(0, limit);
}

export function buildResultsSeason(rows: EarningsLike[], source: string, now = new Date()): ResultsSeason {
  const today = dayStart(now);
  const upcoming = rows.filter((row) => {
    const ts = parseDay(row.date);
    return Number.isFinite(ts) && ts >= today;
  });
  const next7 = upcoming.filter((row) => parseDay(row.date) <= today + 7 * 86_400_000);
  const byDate = new Map<string, string[]>();
  for (const row of upcoming) {
    const list = byDate.get(row.date) ?? [];
    list.push(row.symbol);
    byDate.set(row.date, list);
  }
  const windows: ResultsWindow[] = [...byDate.entries()]
    .sort((a, b) => parseDay(a[0]) - parseDay(b[0]))
    .slice(0, 5)
    .map(([date, symbols]) => ({
      date,
      label: dayLabel(date, now),
      count: symbols.length,
      symbols: symbols.slice(0, 4),
    }));
  return { upcoming: upcoming.length, next7: next7.length, windows, source };
}

export function buildWeekEvents(
  earnings: EarningsLike[],
  econ: EconEventLike[],
  held: ReadonlySet<string>,
  watching: ReadonlySet<string>,
  now = new Date(),
): WeekEvent[] {
  const today = dayStart(now);
  const end = today + 7 * 86_400_000;
  const events: WeekEvent[] = [];

  for (const row of earnings) {
    const ts = parseDay(row.date);
    if (!Number.isFinite(ts) || ts < today || ts > end) continue;
    const symbol = row.symbol.toUpperCase();
    const isHeld = held.has(symbol);
    if (!isHeld && !watching.has(symbol)) continue;
    events.push({
      id: `earnings-${row.symbol}-${row.date}`,
      date: row.date,
      dayLabel: dayLabel(row.date, now),
      title: `${row.symbol} reports results`,
      subtitle: `${row.time ?? 'Time TBD'}${isHeld ? ' · You hold it' : ' · On your watchlist'}`,
      symbol: row.symbol,
      kind: 'earnings',
      tag: isHeld ? 'You own' : 'Watching',
    });
  }

  for (const event of econ) {
    if (event.importance === 'low') continue;
    const ts = parseDay(event.date);
    if (!Number.isFinite(ts) || ts < today || ts > end) continue;
    events.push({
      id: `macro-${event.id}`,
      date: event.date,
      dayLabel: dayLabel(event.date, now),
      title: event.title,
      subtitle: `${event.country} · Macro`,
      kind: 'macro',
      tag: 'Macro',
    });
  }

  return events
    .sort((a, b) => parseDay(a.date) - parseDay(b.date))
    .slice(0, 6);
}

export function buildFeed(input: {
  news: NewsLike[];
  alerts: AlertLike[];
  earnings: EarningsLike[];
  held: ReadonlySet<string>;
  watching: ReadonlySet<string>;
  pulse: MarketPulseData | null;
  now?: number;
}): FeedItem[] {
  const now = input.now ?? Date.now();
  const items: FeedItem[] = [];
  for (const row of input.news) {
    const symbol = row.ticker?.toUpperCase();
    const isHeld = Boolean(symbol && input.held.has(symbol));
    const isWatching = Boolean(symbol && input.watching.has(symbol));
    items.push({
      id: `news-${row.id}`,
      kind: 'news',
      title: row.headline,
      detail: row.summary ?? undefined,
      symbol: row.ticker ?? undefined,
      tag: isHeld ? 'You own' : isWatching ? 'Watching' : 'Market',
      at: Date.parse(row.timestamp) || now,
    });
  }
  for (const alert of input.alerts) {
    if (!alert.lastFiredAt) continue;
    const isHeld = alert.symbols.some((symbol) => input.held.has(symbol.toUpperCase()));
    const isWatching = alert.symbols.some((symbol) => input.watching.has(symbol.toUpperCase()));
    items.push({
      id: `alert-${alert.id}`,
      kind: 'alert',
      title: alert.name,
      detail: `Alert fired · ${alert.symbols.join(', ')}`,
      symbol: alert.symbols[0],
      tag: isHeld ? 'You own' : isWatching ? 'Watching' : 'Market',
      at: Date.parse(alert.lastFiredAt) || now,
    });
  }
  const today = dayStart(new Date(now));
  for (const row of input.earnings) {
    const symbol = row.symbol.toUpperCase();
    const ts = parseDay(row.date);
    // Only published results belong in the feed. Upcoming reports live in
    // "This week for you", not in "what changed".
    if (!Number.isFinite(ts) || ts > today) continue;
    if (ts < today - 7 * 86_400_000) continue;
    const isHeld = input.held.has(symbol);
    if (!isHeld && !input.watching.has(symbol)) continue;
    items.push({
      id: `earnings-${row.symbol}-${row.date}`,
      kind: 'earnings',
      title: `${row.symbol} published results`,
      detail: `${dayLabel(row.date)}${row.time ? ` · ${row.time}` : ''}`,
      symbol: row.symbol,
      tag: isHeld ? 'You own' : 'Watching',
      at: ts,
    });
  }
  if (input.pulse?.leading) {
    items.push({
      id: `sector-${input.pulse.leading.name}`,
      kind: 'sector',
      title: `${input.pulse.leading.name} leads the market`,
      detail: `${input.pulse.scopeLabel} · ${signed(input.pulse.leading.change)}`,
      tag: 'Market',
      at: now - 60_000,
    });
  }
  const seen = new Set<string>();
  const tagRank = (item: FeedItem) => item.tag === 'You own' ? 0 : item.tag === 'Watching' ? 1 : 2;
  return items
    .sort((a, b) => tagRank(a) - tagRank(b) || b.at - a.at)
    .filter((item) => (seen.has(item.id) ? false : (seen.add(item.id), true)))
    .slice(0, 10);
}

export function buildResearch(
  theses: ThesisLike[],
  held: ReadonlySet<string>,
  watching: ReadonlySet<string>,
  limit = 4,
): ResearchRow[] {
  return theses
    .filter((thesis) => held.has(thesis.symbol.toUpperCase()) || watching.has(thesis.symbol.toUpperCase()))
    .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt))
    .slice(0, limit)
    .map((thesis) => ({
      id: thesis.id,
      symbol: thesis.symbol,
      title: thesis.title,
      status: thesis.status,
      updatedAt: thesis.updatedAt,
      watching: !held.has(thesis.symbol.toUpperCase()),
    }));
}

export function buildRecord(
  performance: JournalPerformanceLike | null,
  theses: ThesisLike[],
): RecordSummary {
  const closedTheses = theses.filter((thesis) => thesis.status === 'closed').length;
  const activeTheses = theses.filter((thesis) => thesis.status === 'active' || thesis.status === 'weakening').length;
  const totalTrades = performance?.totalTrades ?? 0;
  return {
    hasData: totalTrades > 0 || theses.length > 0,
    totalTrades,
    winRate: performance?.winRate ?? 0,
    netPnl: performance?.netPnl ?? 0,
    profitFactor: performance?.profitFactor ?? 0,
    closedTheses,
    activeTheses,
  };
}
export interface AttributionRow {
  symbol: string;
  name: string;
  contribution: number;
  changePercent: number;
  weightPct: number;
}

export interface ActionRow {
  symbol: string;
  reason: string;
  severity: 'high' | 'medium' | 'low';
}

export interface MarketSession {
  name: string;
  zone: string;
  status: 'open' | 'closed';
  localTime: string;
  hours: string;
}

export interface PortfolioRisk {
  volatilityPct: number | null;
  maxDrawdownPct: number | null;
  beta: number | null;
  concentrationPct: number;
  sample: number;
}

export interface FxSlice {
  currency: string;
  weightPct: number;
  value: number;
}

export interface SectorRotationGroup {
  tone: SectorTone;
  label: string;
  sectors: string[];
  count: number;
}

function stdev(values: number[]): number | null {
  if (values.length < 2) return null;
  const average = mean(values);
  if (average == null) return null;
  const variance = values.reduce((sum, value) => sum + (value - average) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

export function buildAttribution(holdings: HomeHolding[], useNative = false): { gainers: AttributionRow[]; losers: AttributionRow[]; net: number } {
  const rows: AttributionRow[] = holdings
    .map((holding) => {
      const value = useNative ? holding.valueNative : holding.valueUsd;
      return {
        symbol: holding.symbol,
        name: holding.name,
        contribution: value * (holding.changePercent / 100),
        changePercent: holding.changePercent,
        weightPct: holding.weightPct,
      };
    })
    .filter((row) => Math.abs(row.contribution) > 0.005);
  const gainers = rows.filter((row) => row.contribution > 0).sort((a, b) => b.contribution - a.contribution).slice(0, 3);
  const losers = rows.filter((row) => row.contribution < 0).sort((a, b) => a.contribution - b.contribution).slice(0, 3);
  const net = rows.reduce((sum, row) => sum + row.contribution, 0);
  return { gainers, losers, net };
}

export function buildActionList(
  health: HoldingsHealthSummary,
  earningsBySymbol: ReadonlyMap<string, number>,
  now = new Date(),
): ActionRow[] {
  const rows: ActionRow[] = [];
  for (const row of health.rows) {
    const reasons: Array<{ reason: string; severity: ActionRow['severity'] }> = [];
    if (row.distanceToWeakPct != null && row.distanceToWeakPct <= 1.5) {
      reasons.push({ reason: `${row.distanceToWeakPct.toFixed(1)}% above 50-day support`, severity: 'high' });
    }
    if (row.fallingDays >= 3) {
      reasons.push({ reason: `Falling for ${row.fallingDays} days`, severity: row.fallingDays >= 7 ? 'high' : 'medium' });
    }
    const earnings = earningsBySymbol.get(row.symbol.toUpperCase());
    if (earnings != null) {
      const days = Math.round((earnings - now.getTime()) / 86_400_000);
      if (days >= 0 && days <= 5) reasons.push({ reason: `Reports in ${days === 0 ? 'today' : `${days} day${days === 1 ? '' : 's'}`}`, severity: 'medium' });
    }
    if (row.distanceToWeakPct != null && row.distanceToWeakPct >= 18) {
      reasons.push({ reason: `Extended ${Math.round(row.distanceToWeakPct)}% above its 50-day`, severity: 'low' });
    }
    if (reasons.length === 0) continue;
    const severity = reasons.some((item) => item.severity === 'high') ? 'high' : reasons.some((item) => item.severity === 'medium') ? 'medium' : 'low';
    rows.push({ symbol: row.symbol, reason: reasons.map((item) => item.reason).slice(0, 2).join(' · '), severity });
  }
  const rank = { high: 0, medium: 1, low: 2 };
  return rows.sort((a, b) => rank[a.severity] - rank[b.severity]);
}

const SESSION_DEFS: Array<{ name: string; zone: string; open: number; close: number }> = [
  { name: 'US equities', zone: 'America/New_York', open: 9 * 60 + 30, close: 16 * 60 },
  { name: 'London', zone: 'Europe/London', open: 8 * 60, close: 16 * 60 + 30 },
  { name: 'Frankfurt', zone: 'Europe/Berlin', open: 9 * 60, close: 17 * 60 + 30 },
  { name: 'Tokyo', zone: 'Asia/Tokyo', open: 9 * 60, close: 15 * 60 },
  { name: 'Hong Kong', zone: 'Asia/Hong_Kong', open: 9 * 60 + 30, close: 16 * 60 },
  { name: 'Seoul', zone: 'Asia/Seoul', open: 9 * 60, close: 15 * 60 + 30 },
  { name: 'Singapore', zone: 'Asia/Singapore', open: 9 * 60, close: 17 * 60 },
  { name: 'Sydney', zone: 'Australia/Sydney', open: 10 * 60, close: 16 * 60 },
  { name: 'Toronto', zone: 'America/Toronto', open: 9 * 60 + 30, close: 16 * 60 },
  { name: 'Mumbai', zone: 'Asia/Kolkata', open: 9 * 60 + 15, close: 15 * 60 + 30 },
  { name: 'Karachi', zone: 'Asia/Karachi', open: 9 * 60 + 30, close: 15 * 60 + 30 },
  { name: 'Sao Paulo', zone: 'America/Sao_Paulo', open: 10 * 60, close: 17 * 60 },
];

function zoneParts(now: Date, zone: string): { minutes: number; weekday: string; time: string } | null {
  try {
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: zone,
      hour: '2-digit',
      minute: '2-digit',
      weekday: 'short',
      hour12: false,
    });
    const parts = formatter.formatToParts(now);
    const hour = Number(parts.find((part) => part.type === 'hour')?.value ?? '0');
    const minute = Number(parts.find((part) => part.type === 'minute')?.value ?? '0');
    const weekday = parts.find((part) => part.type === 'weekday')?.value ?? '';
    const display = new Intl.DateTimeFormat('en-US', { timeZone: zone, hour: '2-digit', minute: '2-digit', hour12: false }).format(now);
    return { minutes: hour * 60 + minute, weekday, time: display };
  } catch {
    return null;
  }
}

export function buildMarketSessions(now = new Date()): MarketSession[] {
  return SESSION_DEFS.map((session) => {
    const local = zoneParts(now, session.zone);
    if (!local) return { name: session.name, zone: session.zone, status: 'closed' as const, localTime: '—', hours: '—' };
    const weekend = local.weekday === 'Sat' || local.weekday === 'Sun';
    const open = !weekend && local.minutes >= session.open && local.minutes < session.close;
    const format = (total: number) => `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
    return {
      name: session.name,
      zone: session.zone,
      status: open ? 'open' as const : 'closed' as const,
      localTime: local.time,
      hours: `${format(session.open)}–${format(session.close)}`,
    };
  });
}

export function buildPortfolioRisk(holdings: HomeHolding[], benchmark: { dates: string[]; closes: number[] } | null): PortfolioRisk {
  const withHistory = holdings.filter((holding) => holding.closes.length >= 30);
  const concentrationPct = holdings.reduce((max, holding) => Math.max(max, holding.weightPct), 0);
  if (withHistory.length === 0) {
    return { volatilityPct: null, maxDrawdownPct: null, beta: null, concentrationPct, sample: 0 };
  }
  const usable = withHistory.length;
  const series = withHistory.map((holding) => holding.closes.slice(-60).map((value, index, arr) => index === 0 ? 0 : value / arr[index - 1] - 1).slice(1));
  const length = Math.min(...series.map((values) => values.length));
  const portfolioReturns: number[] = [];
  for (let index = 0; index < length; index += 1) {
    let sum = 0;
    let weights = 0;
    series.forEach((values, i) => {
      const offset = values.length - length + index;
      const holding = withHistory[i];
      sum += values[offset] * holding.weightPct;
      weights += holding.weightPct;
    });
    if (weights > 0) portfolioReturns.push(sum / weights);
  }
  const volatility = stdev(portfolioReturns);
  let nav = 100;
  let peak = 100;
  let maxDrawdown = 0;
  for (const daily of portfolioReturns) {
    nav *= 1 + daily;
    peak = Math.max(peak, nav);
    maxDrawdown = Math.min(maxDrawdown, (nav - peak) / peak * 100);
  }
  let beta: number | null = null;
  if (benchmark && benchmark.closes.length >= 30) {
    const benchReturns = benchmark.closes.slice(-(length + 1)).map((value, index, arr) => index === 0 ? 0 : value / arr[index - 1] - 1).slice(1);
    const benchAligned = benchReturns.slice(-portfolioReturns.length);
    if (benchAligned.length === portfolioReturns.length && benchAligned.length >= 20) {
      const pMean = mean(portfolioReturns) ?? 0;
      const bMean = mean(benchAligned) ?? 0;
      let covariance = 0;
      let variance = 0;
      for (let index = 0; index < portfolioReturns.length; index += 1) {
        covariance += (portfolioReturns[index] - pMean) * (benchAligned[index] - bMean);
        variance += (benchAligned[index] - bMean) ** 2;
      }
      beta = variance > 0 ? covariance / variance : null;
    }
  }
  return {
    volatilityPct: volatility != null ? volatility * Math.sqrt(252) * 100 : null,
    maxDrawdownPct: maxDrawdown,
    beta,
    concentrationPct,
    sample: usable,
  };
}

export function buildFxExposure(holdings: HomeHolding[]): FxSlice[] {
  const total = holdings.reduce((sum, holding) => sum + holding.valueUsd, 0);
  if (total <= 0) return [];
  const byCurrency = new Map<string, number>();
  for (const holding of holdings) {
    byCurrency.set(holding.currency, (byCurrency.get(holding.currency) ?? 0) + holding.valueUsd);
  }
  return [...byCurrency.entries()]
    .map(([currency, value]) => ({ currency, value, weightPct: (value / total) * 100 }))
    .sort((a, b) => b.weightPct - a.weightPct);
}

const ROTATION_ORDER: SectorTone[] = ['leading', 'improving', 'weakening', 'lagging'];
const ROTATION_LABEL: Record<SectorTone, string> = {
  leading: 'Leading',
  improving: 'Improving',
  weakening: 'Weakening',
  lagging: 'Lagging',
};

export function buildSectorRotation(signals: SectorSignal[]): SectorRotationGroup[] {
  const byTone = new Map<SectorTone, string[]>();
  for (const signal of signals) {
    const list = byTone.get(signal.tone) ?? [];
    list.push(signal.name);
    byTone.set(signal.tone, list);
  }
  return ROTATION_ORDER.map((tone) => {
    const sectors = byTone.get(tone) ?? [];
    return { tone, label: ROTATION_LABEL[tone], sectors: sectors.slice(0, 4), count: sectors.length };
  });
}