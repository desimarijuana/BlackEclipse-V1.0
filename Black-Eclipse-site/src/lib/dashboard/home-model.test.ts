import { describe, expect, it } from 'vitest';
import type { RegimeResult } from '@/lib/regime/types';
import {
  buildConcentration,
  buildActionList,
  buildAttribution,
  buildFeed,
  buildFxExposure,
  buildHealth,
  buildHoldingsHealth,
  buildMarketSessions,
  buildPortfolioRisk,
  buildSectorRotation,
  buildHomeHoldings,
  buildLeaders,
  buildPersonalBrief,
  buildPortfolioVsBenchmark,
  buildRadar,
  buildRecord,
  buildResultsSeason,
  buildTrendMix,
  buildWeekEvents,
  leadingSignal,
  momentum,
  regimeNeedle,
  regimeTone,
  sectorBreadth,
  sectorSignals,
  trendOf,
  weatherTone,
} from './home-model';

function rising(length: number, start = 100): number[] {
  return Array.from({ length }, (_, index) => start + index * 1.5);
}

function falling(length: number, start = 200): number[] {
  return Array.from({ length }, (_, index) => start - index * 1.5);
}

function flat(length: number, value = 100): number[] {
  return Array.from({ length }, () => value);
}

function regimePatch(patch: Partial<RegimeResult>): RegimeResult {
  return {
    scope: 'selected',
    market: 'US',
    regime: 'mixed',
    label: 'Mixed / uncertain',
    score: 0,
    confidence: 0.5,
    coverage: 0.5,
    components: [],
    drivers: [],
    benchmarkSymbol: '^GSPC',
    asOf: Date.now(),
    builtAt: Date.now(),
    source: 'jdds',
    coreAvailable: true,
    ...patch,
  };
}

describe('trend classification', () => {
  it('classifies a rising, aligned series as an uptrend', () => {
    expect(trendOf(rising(60))).toBe('uptrend');
  });

  it('classifies a falling series as a downtrend', () => {
    expect(trendOf(falling(60))).toBe('downtrend');
  });

  it('classifies a long-term rise with a short-term pullback as a weak uptrend', () => {
    const closes = [...rising(50, 100), ...falling(10, 175)];
    expect(trendOf(closes)).toBe('weak_uptrend');
  });

  it('never guesses without enough history', () => {
    expect(trendOf(flat(10))).toBe('unknown');
    expect(trendOf([])).toBe('unknown');
  });

  it('computes momentum over the requested window', () => {
    expect(momentum([100, 110, 120, 130], 3)).toBeCloseTo(30, 5);
    expect(momentum([100], 20)).toBeNull();
  });
});

describe('holdings and portfolio health', () => {
  const raw = [
    { symbol: 'AAA', name: 'AAA', valueUsd: 600, valueNative: 600, currency: 'USD', marketId: 'US', sector: 'Technology', changePercent: 1, closes: rising(60) },
    { symbol: 'BBB', name: 'BBB', valueUsd: 300, valueNative: 300, currency: 'USD', marketId: 'US', sector: 'Financials', changePercent: -1, closes: rising(60) },
    { symbol: 'CCC', name: 'CCC', valueUsd: 100, valueNative: 100, currency: 'USD', marketId: 'US', sector: 'Energy', changePercent: 0, closes: falling(60) },
    { symbol: 'PKR', name: 'PKR', valueUsd: 100, valueNative: 27800, currency: 'PKR', marketId: 'PK', sector: 'Finance', changePercent: 2, closes: rising(60) },
  ];

  it('filters to the selected market and computes weights from USD value', () => {
    const holdings = buildHomeHoldings(raw, 'US');
    expect(holdings.map((holding) => holding.symbol)).toEqual(['AAA', 'BBB', 'CCC']);
    expect(holdings[0].weightPct).toBeCloseTo(60, 5);
    expect(holdings[0].trend).toBe('uptrend');
    expect(holdings[2].trend).toBe('downtrend');
  });

  it('includes every market for the global scope', () => {
    expect(buildHomeHoldings(raw, 'GLOBAL')).toHaveLength(4);
  });

  it('reports a high score when the whole book is in uptrends', () => {
    const holdings = buildHomeHoldings([
      { ...raw[0], symbol: 'A', valueUsd: 250 },
      { ...raw[0], symbol: 'B', valueUsd: 250 },
      { ...raw[0], symbol: 'C', valueUsd: 250 },
      { ...raw[0], symbol: 'D', valueUsd: 250 },
    ], 'US');
    const health = buildHealth(holdings);
    expect(health.score).toBe(100);
    expect(health.label).toBe('Excellent');
    expect(health.coveragePct).toBe(100);
  });

  it('penalises concentration and reports coverage honestly', () => {
    const holdings = buildHomeHoldings([
      { ...raw[0], valueUsd: 950, valueNative: 950 },
      { ...raw[1], valueUsd: 50, valueNative: 50, closes: [] },
    ], 'US');
    const health = buildHealth(holdings);
    expect(health.score).toBeLessThan(100);
    expect(health.coveragePct).toBeCloseTo(95, 3);
    expect(health.penalty).toBeGreaterThan(0);
  });

  it('never returns a score when trend history covers too little of the book', () => {
    const holdings = buildHomeHoldings([
      { ...raw[0], valueUsd: 100 },
      { ...raw[1], valueUsd: 900, closes: [] },
    ], 'US');
    const health = buildHealth(holdings);
    expect(health.score).toBeNull();
    expect(health.label).toBe('Unavailable');
  });

  it('splits the trend mix by weight', () => {
    const holdings = buildHomeHoldings(raw, 'US');
    const mix = buildTrendMix(holdings);
    expect(mix.uptrend).toBeCloseTo(90, 5);
    expect(mix.downtrend).toBeCloseTo(10, 5);
    expect(mix.unknown).toBeCloseTo(0, 5);
  });
});

describe('sector strength', () => {
  const signals = sectorSignals([
    { name: 'Tech', change: 2, weight: 10, stocks: 4 },
    { name: 'Banks', change: 0.5, weight: 8, stocks: 3 },
    { name: 'Energy', change: -0.5, weight: 6, stocks: 2 },
    { name: 'Utilities', change: -2, weight: 4, stocks: 2 },
  ], 0.6);

  it('classifies each sector against the market', () => {
    const byName = new Map(signals.map((signal) => [signal.name, signal]));
    expect(byName.get('Tech')?.tone).toBe('leading');
    expect(byName.get('Banks')?.tone).toBe('weakening');
    expect(byName.get('Energy')?.tone).toBe('lagging');
    expect(byName.get('Utilities')?.tone).toBe('lagging');
  });

  it('calls a down sector improving when it is down less than the market', () => {
    const downTape = sectorSignals([
      { name: 'Energy', change: -0.5, weight: 6, stocks: 2 },
      { name: 'Utilities', change: -2, weight: 4, stocks: 2 },
    ], -1);
    expect(downTape.find((signal) => signal.name === 'Energy')?.tone).toBe('improving');
    expect(downTape.find((signal) => signal.name === 'Utilities')?.tone).toBe('lagging');
  });

  it('counts advancing and beating sectors', () => {
    expect(sectorBreadth(signals)).toEqual({ tracked: 4, advancing: 2, beating: 1 });
  });

  it('picks the strongest relative sector as the leader', () => {
    expect(leadingSignal(signals)?.name).toBe('Tech');
  });
});

describe('concentration', () => {
  it('groups by sector and folds the tail into Other', () => {
    const holdings = buildHomeHoldings([
      { symbol: 'A', name: 'A', valueUsd: 50, valueNative: 50, currency: 'USD', marketId: 'US', sector: 'Tech', changePercent: 0, closes: [] },
      { symbol: 'B', name: 'B', valueUsd: 20, valueNative: 20, currency: 'USD', marketId: 'US', sector: 'Tech', changePercent: 0, closes: [] },
      { symbol: 'C', name: 'C', valueUsd: 15, valueNative: 15, currency: 'USD', marketId: 'US', sector: 'Banks', changePercent: 0, closes: [] },
      { symbol: 'D', name: 'D', valueUsd: 10, valueNative: 10, currency: 'USD', marketId: 'US', sector: 'Energy', changePercent: 0, closes: [] },
      { symbol: 'E', name: 'E', valueUsd: 5, valueNative: 5, currency: 'USD', marketId: 'US', sector: 'Utilities', changePercent: 0, closes: [] },
    ], 'US');
    const concentration = buildConcentration(holdings, 3);
    expect(concentration.sectorCount).toBe(4);
    expect(concentration.topSector).toBe('Tech');
    expect(concentration.topSharePct).toBeCloseTo(70, 5);
    expect(concentration.slices.map((slice) => slice.name)).toEqual(['Tech', 'Banks', 'Energy', 'Other']);
    expect(concentration.diversified).toBe(false);
  });
});

describe('regime mapping', () => {
  it('maps scores to tones and clamps the needle', () => {
    expect(regimeTone(regimePatch({ score: 0.5 }))).toBe('bullish');
    expect(regimeTone(regimePatch({ score: -0.5 }))).toBe('bearish');
    expect(regimeTone(regimePatch({ score: 0 }))).toBe('neutral');
    expect(regimeNeedle(regimePatch({ score: -1 }))).toBe(0);
    expect(regimeNeedle(regimePatch({ score: 1 }))).toBe(100);
  });

  it('treats a missing core input as unavailable, never neutral', () => {
    expect(regimeTone(regimePatch({ coreAvailable: false, score: 0 }))).toBe('unavailable');
    expect(regimeTone(null)).toBe('unavailable');
  });

  it('derives market weather from breadth when the regime read is unavailable', () => {
    expect(weatherTone(0.5, 8, 10)).toBe('bullish');
    expect(weatherTone(-0.5, 2, 10)).toBe('bearish');
    expect(weatherTone(0.1, 5, 10)).toBe('neutral');
    expect(weatherTone(0, 0, 0)).toBe('unavailable');
  });
});

describe('watchlist radar', () => {
  it('excludes held names and ranks by absolute move', () => {
    const rows = buildRadar([
      { symbol: 'HELD', name: 'Held', price: 10, changePercent: 9, currency: 'USD', marketId: 'US' },
      { symbol: 'AAA', name: 'A', price: 10, changePercent: -4, currency: 'USD', marketId: 'US' },
      { symbol: 'BBB', name: 'B', price: 10, changePercent: 6, currency: 'USD', marketId: 'US' },
    ], new Set(['HELD']));
    expect(rows.map((row) => row.symbol)).toEqual(['BBB', 'AAA']);
  });
});

describe('personal brief', () => {
  const base = {
    tone: 'bullish' as const,
    health: { score: 82, label: 'Strong' as const, coveragePct: 100, topWeightPct: 30, penalty: 0 },
    review: [],
    leading: { name: 'Technology', change: 2.4, relative: 1.2, weight: 10, stocks: 4, tone: 'leading' as const },
    radar: [{ symbol: 'TSLA', name: 'Tesla', price: 200, changePercent: 3.1, currency: 'USD', marketId: 'US' }],
    holdings: 12,
    marketLabel: 'Global markets',
    tracked: 10,
    trackedLabel: 'markets' as const,
    advancing: 7,
  };

  it('leads with a market read when the book is clear', () => {
    const brief = buildPersonalBrief(base);
    expect(brief.headline).toBe('Markets are constructive');
    expect(brief.detail).toContain('Technology leads');
    expect(brief.detail).toContain('Trend health is strong at 82/100');
  });

  it('leads with the review queue when holdings need attention', () => {
    const brief = buildPersonalBrief({
      ...base,
      review: [{ symbol: 'X', weightPct: 3 } as never],
    });
    expect(brief.headline).toBe('1 holding needs review');
  });

  it('does not invent a leadership call when no signal exists', () => {
    const brief = buildPersonalBrief({ ...base, leading: null });
    expect(brief.detail).toContain('Leadership data is unavailable');
  });

  it('says positions/history are loading instead of calling health unavailable', () => {
    const positions = buildPersonalBrief({ ...base, health: { ...base.health, score: null, label: 'Unavailable' }, positionsLoading: true });
    expect(positions.detail).toContain('Live position values are still loading');
    const history = buildPersonalBrief({ ...base, health: { ...base.health, score: null, label: 'Unavailable' }, historyLoading: true });
    expect(history.detail).toContain('Trend history is still loading');
  });
});

function mkHolding(overrides: Partial<import('./home-model').HomeHolding> = {}): import('./home-model').HomeHolding {
  return {
    symbol: 'AAA',
    name: 'AAA',
    valueUsd: 100,
    valueNative: 100,
    currency: 'USD',
    marketId: 'US',
    sector: 'Technology',
    changePercent: 0,
    closes: [],
    dates: [],
    weightPct: 100,
    trend: 'unknown',
    momentum20: null,
    ...overrides,
  };
}

describe('alpha-style home model', () => {
  it('classifies holdings into healthy/sideways/broken/falling', () => {
    const summary = buildHoldingsHealth([
      mkHolding({ symbol: 'UP', weightPct: 50, closes: rising(60) }),
      mkHolding({ symbol: 'DOWN', weightPct: 50, closes: falling(60) }),
    ]);
    expect(summary.counts.healthy).toBe(1);
    expect(summary.counts.falling).toBe(1);
    expect(summary.turningWeak?.symbol).toBe('UP');
  });

  it('builds a portfolio line against a benchmark', () => {
    const dates = ['2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04', '2026-01-05'];
    const points = buildPortfolioVsBenchmark(
      [mkHolding({ closes: [100, 110, 120, 130, 140], dates })],
      { dates, closes: [100, 100, 100, 100, 100] },
    );
    expect(points).toHaveLength(5);
    expect(points[4].portfolio).toBeCloseTo(140, 5);
    expect(points[4].benchmark).toBeCloseTo(100, 5);
  });

  it('ranks leaders and excludes held/watchlist names', () => {
    const leaders = buildLeaders([
      {
        id: 'US',
        country: 'United States',
        name: 'United States',
        index: { changePct: 1 },
        stocks: [
          { symbol: 'STRONG', name: 'Strong', changePct: 3 },
          { symbol: 'HELD', name: 'Held', changePct: 4 },
          { symbol: 'WATCH', name: 'Watch', changePct: 2 },
        ],
      },
    ], new Set(['HELD']), new Set(['WATCH']));
    expect(leaders.map((leader) => leader.symbol)).toEqual(['STRONG']);
    expect(leaders[0].score).toBeGreaterThan(50);
  });

  it('counts confirmed earnings for results season', () => {
    const date = new Date(Date.now() + 2 * 86_400_000).toISOString().slice(0, 10);
    const season = buildResultsSeason([{ symbol: 'AAA', name: 'AAA', date }], 'alphavantage');
    expect(season.next7).toBe(1);
    expect(season.windows[0].symbols).toEqual(['AAA']);
  });

  it('tags feed items for held and watched symbols', () => {
    const feed = buildFeed({
      news: [
        { id: 'n1', ticker: 'AAA', headline: 'AAA wins a contract', timestamp: new Date().toISOString() },
        { id: 'n2', ticker: 'BBB', headline: 'BBB results', timestamp: new Date().toISOString() },
      ],
      alerts: [],
      earnings: [],
      held: new Set(['AAA']),
      watching: new Set(['BBB']),
      pulse: null,
    });
    expect(feed.find((item) => item.symbol === 'AAA')?.tag).toBe('You own');
    expect(feed.find((item) => item.symbol === 'BBB')?.tag).toBe('Watching');
  });

  it('does not claim a record when there are no trades or theses', () => {
    expect(buildRecord(null, []).hasData).toBe(false);
    expect(buildRecord({ totalTrades: 4, winRate: 0.5, netPnl: 12, profitFactor: 2 }, []).hasData).toBe(true);
  });

  it('only includes week events for held/watched names plus macro', () => {
    const date = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
    const events = buildWeekEvents(
      [{ symbol: 'AAA', name: 'AAA', date }, { symbol: 'CCC', name: 'CCC', date }],
      [{ id: 'm1', date, country: 'US', title: 'CPI', importance: 'high' }],
      new Set(['AAA']),
      new Set(),
    );
    expect(events.some((event) => event.symbol === 'AAA')).toBe(true);
    expect(events.some((event) => event.symbol === 'CCC')).toBe(false);
    expect(events.some((event) => event.kind === 'macro')).toBe(true);
  });
});
describe('dashboard insights model', () => {
  it('attributes today P&L to the biggest movers', () => {
    const attribution = buildAttribution([
      mkHolding({ symbol: 'UP', valueUsd: 1000, changePercent: 2 }),
      mkHolding({ symbol: 'DOWN', valueUsd: 1000, changePercent: -3 }),
    ]);
    expect(attribution.gainers[0].symbol).toBe('UP');
    expect(attribution.losers[0].symbol).toBe('DOWN');
    expect(attribution.gainers[0].contribution).toBeCloseTo(20, 4);
    expect(attribution.losers[0].contribution).toBeCloseTo(-30, 4);
  });

  it('flags holdings near support and falling', () => {
    const health = buildHoldingsHealth([
      mkHolding({ symbol: 'UP', weightPct: 100, closes: rising(60) }),
      mkHolding({ symbol: 'DOWN', weightPct: 0, closes: falling(60) }),
    ]);
    const list = buildActionList(health, new Map());
    expect(list.some((row) => row.symbol === 'DOWN')).toBe(true);
  });

  it('marks market sessions open or closed', () => {
    const sessions = buildMarketSessions(new Date('2026-10-22T14:00:00Z'));
    expect(sessions).toHaveLength(12);
    expect(sessions.some((session) => session.status === 'open')).toBe(true);
  });

  it('splits FX exposure by currency', () => {
    const slices = buildFxExposure([
      mkHolding({ currency: 'USD', valueUsd: 75 }),
      mkHolding({ currency: 'PKR', valueUsd: 25 }),
    ]);
    expect(slices[0]).toMatchObject({ currency: 'USD', weightPct: 75 });
    expect(slices[1]).toMatchObject({ currency: 'PKR', weightPct: 25 });
  });

  it('groups sectors into rotation buckets', () => {
    const rotation = buildSectorRotation([
      { name: 'Tech', change: 2, weight: 1, stocks: 1, relative: 1, tone: 'leading' },
      { name: 'Banks', change: -1, weight: 1, stocks: 1, relative: -1, tone: 'lagging' },
    ]);
    expect(rotation.find((group) => group.tone === 'leading')?.sectors).toContain('Tech');
    expect(rotation.find((group) => group.tone === 'lagging')?.count).toBe(1);
  });

  it('computes portfolio risk from holding history', () => {
    const risk = buildPortfolioRisk([mkHolding({ weightPct: 100, closes: rising(60) })], null);
    expect(risk.volatilityPct).not.toBeNull();
    expect(risk.concentrationPct).toBe(100);
  });
});