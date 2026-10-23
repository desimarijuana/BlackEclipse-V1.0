import { describe, expect, it } from 'vitest';
import type { ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import type { HomeData } from '@/lib/dashboard/use-home-data';
import type { HomeHolding } from '@/lib/dashboard/home-model';
import {
  AlertsCard,
  AttentionCard,
  ConcentrationCard,
  LeadershipCard,
  MarketHero,
  PortfolioHealthCard,
  PortfolioWatchCard,
  RegimeCard,
  UniverseCard,
  WatchlistRadarCard,
} from './home-cards';

const html = (node: ReactElement): string => renderToStaticMarkup(node);

function holding(overrides: Partial<HomeHolding> = {}): HomeHolding {
  return {
    symbol: 'AAPL',
    name: 'Apple Inc.',
    valueUsd: 1000,
    valueNative: 1000,
    currency: 'USD',
    marketId: 'US',
    sector: 'Technology',
    changePercent: 1.2,
    closes: [],
    weightPct: 50,
    trend: 'uptrend',
    momentum20: 3,
    ...overrides,
  };
}

function fixture(overrides: Partial<HomeData> = {}): HomeData {
  const uptrend = holding({ symbol: 'AAPL', name: 'Apple Inc.', weightPct: 40 });
  const stable = holding({ symbol: 'KO', name: 'Coca-Cola', trend: 'weak_uptrend', weightPct: 35, sector: 'Consumer Staples' });
  const review = holding({ symbol: 'XOM', name: 'Exxon Mobil', trend: 'downtrend', weightPct: 25, sector: 'Energy', changePercent: -1.4 });
  return {
    market: 'GLOBAL',
    setMarket: () => undefined,
    marketOptions: [{ id: 'GLOBAL', label: 'Global markets' }],
    marketLabel: 'Global markets',
    active: true,
    loading: false,
    loadError: false,
    updatedAt: new Date('2026-10-21T10:00:00Z'),
    refresh: () => undefined,
    regime: {
      scope: 'global',
      market: 'GLOBAL',
      regime: 'mixed',
      label: 'Mixed / uncertain',
      score: 0.12,
      confidence: 0.6,
      coverage: 0.6,
      components: [
        { id: 'price_breadth', label: 'Price & breadth', score: 0.4, weight: 0.4, usedWeight: 0.4, available: true, asOf: Date.now(), maxAgeMs: 600000, stale: false, source: 'JDDS', detail: 'Breadth positive', confidence: 0.8 },
        { id: 'news_narrative', label: 'News / narrative', score: 0.1, weight: 0.2, usedWeight: 0.2, available: true, asOf: Date.now(), maxAgeMs: 86400000, stale: false, source: 'JDDS', detail: 'Neutral tape', confidence: 0.6 },
      ],
      drivers: [],
      benchmarkSymbol: '^GSPC',
      asOf: Date.now(),
      builtAt: Date.now(),
      source: 'jdds',
      coreAvailable: true,
    },
    tone: 'neutral',
    regimeTone: 'neutral',
    weatherSource: 'regime',
    needle: 56,
    benchmark: {
      symbol: '^GSPC',
      label: 'S&P 500',
      market: 'US',
      dates: ['2026-08-01', '2026-08-15', '2026-09-01', '2026-10-01'],
      closes: [100, 104, 101, 108],
      stale: false,
    },
    signals: [
      { name: 'Brazil', change: 1.55, weight: 10, stocks: 10, relative: 1.2, tone: 'leading', topSymbol: 'PBR', topChange: 3 },
      { name: 'Japan', change: 0.69, weight: 10, stocks: 10, relative: 0.3, tone: 'leading', topSymbol: 'TM', topChange: 1.5 },
    ],
    leading: { name: 'Brazil', change: 1.55, weight: 10, stocks: 10, relative: 1.2, tone: 'leading', topSymbol: 'PBR' },
    breadth: { tracked: 11, advancing: 7, beating: 6 },
    marketChange: 0.3,
    trackedLabel: 'markets',
    holdings: [uptrend, stable, review],
    trendMix: { uptrend: 40, weakUptrend: 35, downtrend: 25, unknown: 0, knownPct: 100 },
    health: { score: 62, label: 'Mixed', coveragePct: 100, topWeightPct: 40, penalty: 2.5 },
    review: [review],
    best: [uptrend],
    stable: [stable],
    concentration: { slices: [{ name: 'Technology', valueUsd: 1000, weightPct: 40 }, { name: 'Consumer Staples', valueUsd: 875, weightPct: 35 }, { name: 'Energy', valueUsd: 625, weightPct: 25 }], sectorCount: 3, topSharePct: 40, topSector: 'Technology', diversified: false },
    radar: [
      { symbol: 'TSLA', name: 'Tesla', price: 250.5, changePercent: 3.2, currency: 'USD', marketId: 'US' },
    ],
    brief: { headline: 'Markets are constructive', detail: 'Brazil leads at +1.55%. Trend health is mixed at 62/100.', tone: 'neutral' },
    alerts: [{ id: 'a1', name: 'AAPL breakout', symbols: ['AAPL'], active: true, status: 'watching', lastFiredAt: '2026-10-21T09:00:00Z' }],
    activeAlerts: 1,
    recentAlerts: [{ id: 'a1', name: 'AAPL breakout', symbols: ['AAPL'], active: true, status: 'watching', lastFiredAt: '2026-10-21T09:00:00Z' }],
    portfolioValue: 2500,
    portfolioChangePct: 0.4,
    portfolioChangeValue: 10,
    displayCurrency: 'USD',
    holdingsCount: 3,
    fxMissingCount: 0,
    positionsLoading: false,
    historyLoading: false,
    demoOnly: true,
    includesDemo: true,
    universe: { markets: 28, instruments: 280, advancing: 7, tracked: 11 },
    fundsCount: 4,
    portfolioSeries: [],
    portfolioReturnPct: 12,
    portfolioCostBasis: 2200,
    holdingsHealth: {
      rows: [],
      counts: { healthy: 0, sideways: 0, broken: 0, falling: 0, unknown: 0 },
      weight: { healthy: 0, sideways: 0, broken: 0, falling: 0, unknown: 0 },
      total: 0,
      healthyWeightPct: 0,
      turningWeak: null,
    },
    feed: [],
    feedNewCount: 0,
    feedLoading: false,
    markFeedSeen: () => undefined,
    weekEvents: [],
    pulse: { scopeLabel: 'Global markets', indexChange: 0, advancing: 0, declining: 0, tracked: 0, leading: null, sectors: [], movers: [] },
    resultsSeason: { upcoming: 0, next7: 0, windows: [], source: 'unavailable' },
    earningsSource: 'unavailable',
    leaders: [],
    research: [],
    record: { hasData: false, totalTrades: 0, winRate: 0, netPnl: 0, profitFactor: 0, closedTheses: 0, activeTheses: 0 },
    attribution: { gainers: [], losers: [], net: 0 },
    actionList: [],
    sessions: [],
    risk: { volatilityPct: null, maxDrawdownPct: null, beta: null, concentrationPct: 0, sample: 0 },
    fxExposure: [],
    rotation: [],
    earningsDates: {},
    ...overrides,
  };
}

describe('dashboard cards', () => {
  it('renders the populated dashboard cards from the model', () => {
    const data = fixture();
    const markup = html(
      <>
        <MarketHero data={data} />
        <PortfolioHealthCard data={data} />
        <LeadershipCard data={data} />
        <RegimeCard data={data} />
        <AttentionCard data={data} />
        <PortfolioWatchCard data={data} />
        <WatchlistRadarCard data={data} />
        <ConcentrationCard data={data} />
        <UniverseCard data={data} />
        <AlertsCard data={data} />
      </>,
    );
    expect(markup).toContain('Markets are constructive');
    expect(markup).toContain('Demo book');
    expect(markup).toContain('Brazil');
    expect(markup).toContain('Mixed / uncertain');
    expect(markup).toContain('Review candidates');
    expect(markup).toContain('AAPL breakout');
    expect(markup).toContain('Explore. Filter. Rank. Decide.');
    expect(markup).toContain('Uptrend');
  });

  it('renders honest empty states instead of invented values', () => {
    const data = fixture({
      holdings: [],
      review: [],
      best: [],
      stable: [],
      holdingsCount: 0,
      health: { score: null, label: 'Unavailable', coveragePct: 0, topWeightPct: 0, penalty: 0 },
      trendMix: { uptrend: 0, weakUptrend: 0, downtrend: 0, unknown: 0, knownPct: 0 },
      radar: [],
      signals: [],
      leading: null,
      breadth: { tracked: 0, advancing: 0, beating: 0 },
      concentration: { slices: [], sectorCount: 0, topSharePct: 0, topSector: null, diversified: false },
      alerts: [],
      recentAlerts: [],
      activeAlerts: 0,
      portfolioValue: 0,
      portfolioChangePct: 0,
      universe: { markets: 0, instruments: 0, advancing: 0, tracked: 0 },
    });
    const markup = html(
      <>
        <PortfolioHealthCard data={data} />
        <LeadershipCard data={data} />
        <AttentionCard data={data} />
        <PortfolioWatchCard data={data} />
        <WatchlistRadarCard data={data} />
        <ConcentrationCard data={data} />
        <AlertsCard data={data} />
      </>,
    );
    expect(markup).toContain('No open holdings');
    expect(markup).toContain('leadership is unavailable');
    expect(markup).toContain('No holdings need review');
    expect(markup).toContain('No watchlist setups');
    expect(markup).toContain('No alerts have fired yet');
  });
});

