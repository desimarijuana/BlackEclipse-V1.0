import { describe, it, expect } from 'vitest';
import {
  assembleRegime,
  formatAge,
  marketNewsRegions,
  resolveRegimeMarket,
  scoreMacroSurprises,
  scoreNews,
  scorePriceBreadth,
  scoreVolatility,
  tanhScore,
  NEWS_HALF_LIFE_HOURS,
  type RawComponent,
} from './scoring';
import type { RegimeComponent, RegimeResult } from './types';

const NOW = Date.UTC(2026, 0, 5, 12, 0, 0);
const min = 60_000;

function raw(over: Partial<RawComponent> & Pick<RawComponent, 'id'>): RawComponent {
  return {
    score: 0,
    asOf: NOW,
    maxAgeMs: 10 * min,
    source: 'test',
    detail: 'test',
    ...over,
  };
}

function comp(result: RegimeResult, id: string): RegimeComponent {
  const c = result.components.find((x) => x.id === id);
  if (!c) throw new Error(`missing component ${id}`);
  return c;
}

describe('resolveRegimeMarket (scope selection)', () => {
  it('selected uses the active market, falling back to US', () => {
    expect(resolveRegimeMarket('selected', 'pk')).toBe('PK');
    expect(resolveRegimeMarket('selected', null)).toBe('US');
    expect(resolveRegimeMarket('selected', '')).toBe('US');
  });
  it('us and global ignore the selected market', () => {
    expect(resolveRegimeMarket('us', 'PK')).toBe('US');
    expect(resolveRegimeMarket('global', 'PK')).toBe('GLOBAL');
  });
});

describe('tanhScore', () => {
  it('compresses sign-preserving into [-1,1]', () => {
    expect(tanhScore(0)).toBe(0);
    expect(tanhScore(1.5)).toBeGreaterThan(0.7);
    expect(tanhScore(-1.5)).toBeLessThan(-0.7);
    expect(tanhScore(100)).toBeLessThanOrEqual(1);
    expect(tanhScore(NaN)).toBe(0);
  });
});

describe('scorePriceBreadth', () => {
  it('is positive when the index average and breadth are up', () => {
    expect(scorePriceBreadth(1.2, 0.9, 0.8)).toBeGreaterThan(0.35);
  });
  it('is negative when everything is red', () => {
    expect(scorePriceBreadth(-1.2, 0.1, 0.2)).toBeLessThan(-0.35);
  });
  it('still works when breadth inputs are unknown', () => {
    expect(Number.isFinite(scorePriceBreadth(0.8, null, null))).toBe(true);
  });
});

describe('scoreVolatility', () => {
  it('returns null when VIX is missing', () => {
    expect(scoreVolatility(null)).toBeNull();
    expect(scoreVolatility(undefined)).toBeNull();
    expect(scoreVolatility(0)).toBeNull();
  });
  it('reads low VIX as risk-on and high VIX as risk-off', () => {
    expect(scoreVolatility(12)).toBeGreaterThan(0);
    expect(scoreVolatility(20)).toBe(0);
    expect(scoreVolatility(32)).toBeLessThan(-0.5);
  });
});

describe('scoreMacroSurprises', () => {
  it('returns null without usable surprises', () => {
    expect(scoreMacroSurprises([])).toBeNull();
  });
  it('scores a positive growth beat as risk-on', () => {
    const s = scoreMacroSurprises([{ actual: 2.5, forecast: 2, importance: 'high', polarity: 1 }]);
    expect(s).toBeGreaterThan(0);
  });
  it('scores a hot inflation print as risk-off', () => {
    const s = scoreMacroSurprises([{ actual: 4, forecast: 3, importance: 'high', polarity: -1 }]);
    expect(s).toBeLessThan(0);
  });
});

describe('scoreNews (tier + recency + dedup-weighted)', () => {
  it('returns null with no items', () => {
    expect(scoreNews([], NOW)).toBeNull();
  });
  it('a fresh tier-1 bullish wire outweighs a stale tier-4 item', () => {
    const s = scoreNews(
      [
        { sentiment: 'bullish', tier: 1, at: NOW, relevance: 1 },
        { sentiment: 'bearish', tier: 4, at: NOW - 36 * 3600_000, relevance: 1 },
      ],
      NOW,
    );
    expect(s).toBeGreaterThan(0);
  });
  it('recency decay makes a fresh item dominate a stale opposite one', () => {
    const freshBull = scoreNews(
      [
        { sentiment: 'bullish', tier: 2, at: NOW, relevance: 1 },
        { sentiment: 'bearish', tier: 2, at: NOW - 3 * NEWS_HALF_LIFE_HOURS * 3600_000, relevance: 1 },
      ],
      NOW,
    );
    // With both items equally fresh the pair nets ~0; decay tilts it bullish.
    const sameAge = scoreNews(
      [
        { sentiment: 'bullish', tier: 2, at: NOW, relevance: 1 },
        { sentiment: 'bearish', tier: 2, at: NOW, relevance: 1 },
      ],
      NOW,
    );
    expect(sameAge).toBe(0);
    expect(freshBull as number).toBeGreaterThan(0);
  });
  it('neutral items produce a near-flat score', () => {
    const s = scoreNews([{ sentiment: 'neutral', tier: 1, at: NOW, relevance: 1 }], NOW);
    expect(s).toBe(0);
  });
});

describe('marketNewsRegions', () => {
  it('maps markets to relevant feed regions', () => {
    expect(marketNewsRegions('US')).toContain('US');
    expect(marketNewsRegions('IN')).toContain('INDIA');
    expect(marketNewsRegions('GLOBAL')).toContain('US');
  });
});

describe('assembleRegime — availability, staleness, confidence', () => {
  it('renormalizes weights over available components', () => {
    const r = assembleRegime({
      scope: 'us',
      market: 'US',
      now: NOW,
      raw: [
        raw({ id: 'price_breadth', score: 0.5 }),
        raw({ id: 'volatility', score: null, asOf: null }),
      ],
    });
    expect(comp(r, 'price_breadth').usedWeight).toBe(1);
    expect(comp(r, 'volatility').available).toBe(false);
  });

  it('treats stale data as unavailable and excludes it', () => {
    const r = assembleRegime({
      scope: 'us',
      market: 'US',
      now: NOW,
      raw: [
        raw({ id: 'price_breadth', score: 0.5 }),
        raw({ id: 'news_narrative', score: 0.9, asOf: NOW - 10 * min, maxAgeMs: 5 * min }),
      ],
    });
    const news = comp(r, 'news_narrative');
    expect(news.stale).toBe(true);
    expect(news.available).toBe(false);
    expect(news.usedWeight).toBe(0);
  });

  it('unavailable components lower coverage and confidence', () => {
    const full = assembleRegime({
      scope: 'us',
      market: 'US',
      now: NOW,
      raw: [
        raw({ id: 'price_breadth', score: 0.5 }),
        raw({ id: 'volatility', score: 0.2 }),
        raw({ id: 'news_narrative', score: 0.1 }),
      ],
    });
    const partial = assembleRegime({
      scope: 'us',
      market: 'US',
      now: NOW,
      raw: [
        raw({ id: 'price_breadth', score: 0.5 }),
        raw({ id: 'volatility', score: null, asOf: null }),
        raw({ id: 'news_narrative', score: null, asOf: null }),
      ],
    });
    expect(partial.coverage).toBeLessThan(full.coverage);
    expect(partial.confidence).toBeLessThan(full.confidence);
  });

  it('missing core input yields UNAVAILABLE, never a false neutral', () => {
    const r = assembleRegime({
      scope: 'us',
      market: 'US',
      now: NOW,
      raw: [
        raw({ id: 'price_breadth', score: null, asOf: null }),
        raw({ id: 'news_narrative', score: 0.8 }),
      ],
    });
    expect(r.regime).toBe('unavailable');
    expect(r.score).toBeNull();
    expect(r.confidence).toBe(0);
    expect(r.coreAvailable).toBe(false);
  });

  it('all-missing inputs never read bullish', () => {
    const r = assembleRegime({
      scope: 'global',
      market: 'GLOBAL',
      now: NOW,
      raw: [raw({ id: 'price_breadth', score: null, asOf: null })],
    });
    expect(r.regime).toBe('unavailable');
    expect(r.label).toBe('Unavailable');
  });
});

describe('assembleRegime — regime taxonomy', () => {
  const base = { scope: 'us' as const, market: 'US', now: NOW };

  it('broad up with wide breadth and calm VIX is risk-on broadening', () => {
    const r = assembleRegime({
      ...base,
      raw: [
        raw({ id: 'price_breadth', score: 0.8, metrics: { breadthUp: 0.75 } }),
        raw({ id: 'volatility', score: 0.4 }),
      ],
    });
    expect(r.regime).toBe('risk_on_broadening');
  });

  it('up but narrow breadth is a fragile rally', () => {
    const r = assembleRegime({
      ...base,
      raw: [
        raw({ id: 'price_breadth', score: 0.6, metrics: { breadthUp: 0.3 } }),
        raw({ id: 'volatility', score: 0.2 }),
      ],
    });
    expect(r.regime).toBe('fragile_rally');
  });

  it('broadly negative is risk-off', () => {
    const r = assembleRegime({
      ...base,
      raw: [raw({ id: 'price_breadth', score: -0.7 })],
    });
    expect(r.regime).toBe('risk_off');
  });

  it('high VIX forces risk-off even when price is flat', () => {
    const r = assembleRegime({
      ...base,
      raw: [
        raw({ id: 'price_breadth', score: 0.1 }),
        raw({ id: 'volatility', score: -0.8 }),
      ],
    });
    expect(r.regime).toBe('risk_off');
  });

  it('a strong negative news tape without price confirmation is a narrative shock', () => {
    const r = assembleRegime({
      ...base,
      raw: [
        raw({ id: 'price_breadth', score: 0.05 }),
        raw({ id: 'news_narrative', score: -0.8 }),
      ],
    });
    expect(r.regime).toBe('narrative_shock');
  });

  it('a mild, balanced tape is mixed', () => {
    const r = assembleRegime({
      ...base,
      raw: [
        raw({ id: 'price_breadth', score: 0.1 }),
        raw({ id: 'volatility', score: 0.0 }),
        raw({ id: 'news_narrative', score: -0.1 }),
      ],
    });
    expect(r.regime).toBe('mixed');
  });
});

describe('formatAge', () => {
  it('formats a compact relative age', () => {
    expect(formatAge(0)).toBe('just now');
    expect(formatAge(5 * min)).toBe('5m ago');
    expect(formatAge(3 * 3600_000)).toBe('3h ago');
    expect(formatAge(2 * 24 * 3600_000)).toBe('2d ago');
    expect(formatAge(null)).toBe('unknown');
  });
});
