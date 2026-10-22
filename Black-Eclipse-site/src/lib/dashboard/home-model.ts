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
