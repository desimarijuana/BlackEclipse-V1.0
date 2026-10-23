'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { HEATMAP_MARKETS, heatmapMeta, type HeatmapPayload } from '@/lib/heatmap';
import type { RegimeResult } from '@/lib/regime/types';
import { usePriceHistories } from '@/hooks/use-price-histories';
import { useLiveQuotes, marketHintFor } from '@/components/screens/portfolio/use-live-quotes';
import { useAggregatePortfolio } from './portfolio-store';
import { useWatchlist } from './watchlist-store';
import {
  buildConcentration,
  buildActionList,
  buildAttribution,
  buildFxExposure,
  buildMarketSessions,
  buildPortfolioRisk,
  buildSectorRotation,
  buildFeed,
  buildHealth,
  buildHoldingsHealth,
  buildLeaders,
  buildMarketPulse,
  buildPortfolioVsBenchmark,
  buildRecord,
  buildResearch,
  buildResultsSeason,
  buildWeekEvents,
  buildHomeHoldings,
  buildPersonalBrief,
  buildRadar,
  buildTrendMix,
  leadingSignal,
  mean,
  regimeNeedle,
  regimeTone,
  sectorBreadth,
  sectorSignals,
  weatherTone,
  type Brief,
  type Concentration,
  type EarningsLike,
  type EconEventLike,
  type FeedItem,
  type HoldingsHealthSummary,
  type JournalPerformanceLike,
  type LeaderRow,
  type MarketPulseData,
  type NewsLike,
  type OverviewGroupLike,
  type PortfolioBenchmarkPoint,
  type RecordSummary,
  type ResearchRow,
  type ResultsSeason,
  type ThesisLike,
  type WeekEvent,
  type HealthScore,
  type ActionRow,
  type FxSlice,
  type MarketSession,
  type PortfolioRisk,
  type SectorRotationGroup,
  type HomeHolding,
  type RadarRow,
  type SectorBreadth,
  type SectorInput,
  type SectorSignal,
  type Tone,
  type TrendMix,
} from './home-model';

export interface GlobalOverviewIndex {
  symbol: string;
  name: string;
  price: number;
  changePct: number;
}

export interface GlobalOverviewGroup {
  id: string;
  country: string;
  name?: string;
  exchange: string;
  currency: string;
  indexName?: string;
  index?: GlobalOverviewIndex | null;
  stocks: Array<{ symbol: string; name: string; price: number; changePct: number; marketCap: number | null }>;
}

export interface HomeAlert {
  id: string;
  name: string;
  symbols: string[];
  active: boolean;
  status: string;
  lastFiredAt: string | null;
}

export interface BenchmarkSeries {
  symbol: string;
  label: string;
  market: string;
  dates: string[];
  closes: number[];
  stale: boolean;
}

export interface HomeData {
  market: string;
  setMarket: (market: string) => void;
  marketOptions: Array<{ id: string; label: string }>;
  marketLabel: string;
  active: boolean;
  loading: boolean;
  loadError: boolean;
  updatedAt: Date | null;
  refresh: () => void;
  regime: RegimeResult | null;
  tone: Tone;
  regimeTone: Tone;
  weatherSource: 'regime' | 'breadth' | 'unavailable';
  needle: number | null;
  benchmark: BenchmarkSeries | null;
  signals: SectorSignal[];
  leading: SectorSignal | null;
  breadth: SectorBreadth;
  marketChange: number;
  trackedLabel: 'markets' | 'sectors';
  holdings: HomeHolding[];
  trendMix: TrendMix;
  health: HealthScore;
  review: HomeHolding[];
  best: HomeHolding[];
  stable: HomeHolding[];
  concentration: Concentration;
  radar: RadarRow[];
  brief: Brief;
  alerts: HomeAlert[];
  activeAlerts: number;
  recentAlerts: HomeAlert[];
  portfolioValue: number;
  portfolioChangePct: number;
  portfolioChangeValue: number;
  displayCurrency: string;
  holdingsCount: number;
  fxMissingCount: number;
  positionsLoading: boolean;
  historyLoading: boolean;
  demoOnly: boolean;
  includesDemo: boolean;
  universe: { markets: number; instruments: number; advancing: number; tracked: number };
  fundsCount: number;
  attribution: ReturnType<typeof buildAttribution>;
  actionList: ActionRow[];
  sessions: MarketSession[];
  risk: PortfolioRisk;
  fxExposure: FxSlice[];
  rotation: SectorRotationGroup[];
  earningsDates: Record<string, string>;
  portfolioSeries: PortfolioBenchmarkPoint[];
  portfolioReturnPct: number;
  portfolioCostBasis: number;
  holdingsHealth: HoldingsHealthSummary;
  feed: FeedItem[];
  feedNewCount: number;
  feedLoading: boolean;
  markFeedSeen: () => void;
  weekEvents: WeekEvent[];
  pulse: MarketPulseData;
  resultsSeason: ResultsSeason;
  earningsSource: string;
  leaders: LeaderRow[];
  research: ResearchRow[];
  record: RecordSummary;
}

const MARKET_KEY = 'be_home_dashboard_market_v1';
const KNOWN_MARKETS = new Set(['GLOBAL', ...HEATMAP_MARKETS.map((market) => market.id)]);

const FALLBACK_BENCHMARK: Record<string, { symbol: string; market: string; label: string }> = {
  GLOBAL: { symbol: '^GSPC', market: 'US', label: 'S&P 500' },
  CRYPTO: { symbol: 'BTC-USD', market: 'CRYPTO', label: 'Bitcoin' },
  FOREX: { symbol: 'EURUSD=X', market: 'FOREX', label: 'EUR/USD' },
  COMMODITIES: { symbol: 'GC=F', market: 'COMMODITIES', label: 'Gold' },
};

export const HOME_MARKETS: Array<{ id: string; label: string }> = [
  { id: 'GLOBAL', label: 'Global markets' },
  { id: 'US', label: 'United States' },
  { id: 'PK', label: 'Pakistan (PSX)' },
  { id: 'CRYPTO', label: 'Global crypto' },
  { id: 'IN', label: 'India' },
  { id: 'UK', label: 'United Kingdom' },
  { id: 'JP', label: 'Japan' },
  { id: 'CN', label: 'China' },
  { id: 'DE', label: 'Germany' },
  ...HEATMAP_MARKETS
    .filter((market) => !['US', 'PK', 'CRYPTO', 'IN', 'UK', 'JP', 'CN', 'DE', 'FOREX', 'COMMODITIES'].includes(market.id))
    .map((market) => ({ id: market.id, label: market.country })),
];

export function marketLabelFor(market: string): string {
  const hit = HOME_MARKETS.find((option) => option.id === market);
  if (hit) return hit.label;
  return heatmapMeta(market).country || market;
}

function readMarket(): string {
  if (typeof window === 'undefined') return 'GLOBAL';
  try {
    const stored = window.localStorage.getItem(MARKET_KEY)?.toUpperCase() ?? '';
    return KNOWN_MARKETS.has(stored) ? stored : 'GLOBAL';
  } catch {
    return 'GLOBAL';
  }
}

function writeMarket(market: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(MARKET_KEY, market);
  } catch {
    /* ignore */
  }
}

function benchmarkFor(market: string): { symbol: string; market: string; label: string } | null {
  if (FALLBACK_BENCHMARK[market]) return FALLBACK_BENCHMARK[market];
  const meta = heatmapMeta(market);
  if (!meta.indexSymbol) return null;
  return { symbol: meta.indexSymbol, market, label: meta.index };
}

interface Fetched<T> {
  data: T | null;
  error: boolean;
}

interface NewsResponse { news?: NewsLike[] }
interface EarningsResponse { rows?: EarningsLike[]; source?: string }
interface EconResponse { events?: EconEventLike[] }
interface ThesesResponse { theses?: ThesisLike[] }
interface JournalResponse { analytics?: { performance?: JournalPerformanceLike } }

const FEED_SEEN_KEY = 'be_home_feed_seen_v1';

async function fetchJson<T>(url: string, signal: AbortSignal): Promise<Fetched<T>> {
  try {
    const response = await fetch(url, { signal, cache: 'no-store' });
    if (!response.ok) return { data: null, error: true };
    return { data: (await response.json()) as T, error: false };
  } catch (error) {
    if ((error as Error)?.name === 'AbortError') return { data: null, error: false };
    return { data: null, error: true };
  }
}

function parseAlerts(payload: unknown): HomeAlert[] {
  const rows = payload && typeof payload === 'object' && Array.isArray((payload as { alerts?: unknown }).alerts)
    ? (payload as { alerts: unknown[] }).alerts
    : [];
  return rows
    .map((row): HomeAlert | null => {
      if (!row || typeof row !== 'object') return null;
      const value = row as Record<string, unknown>;
      if (typeof value.id !== 'string') return null;
      return {
        id: value.id,
        name: typeof value.name === 'string' ? value.name : 'Alert',
        symbols: Array.isArray(value.symbols) ? value.symbols.filter((symbol): symbol is string => typeof symbol === 'string') : [],
        active: value.active !== false,
        status: typeof value.status === 'string' ? value.status : 'idle',
        lastFiredAt: typeof value.lastFiredAt === 'string' ? value.lastFiredAt : null,
      };
    })
    .filter((alert): alert is HomeAlert => alert !== null);
}

function parseBenchmark(payload: unknown, meta: { symbol: string; market: string; label: string }): BenchmarkSeries | null {
  if (!payload || typeof payload !== 'object') return null;
  const value = payload as { series?: unknown; stale?: unknown };
  const rows = Array.isArray(value.series) ? value.series : [];
  const dates: string[] = [];
  const closes: number[] = [];
  for (const row of rows) {
    if (!row || typeof row !== 'object') continue;
    const bar = row as { date?: unknown; close?: unknown };
    const date = typeof bar.date === 'string' ? bar.date : '';
    const close = Number(bar.close);
    if (!date || !Number.isFinite(close) || close <= 0) continue;
    dates.push(date);
    closes.push(close);
  }
  if (dates.length < 2) return null;
  return { ...meta, dates, closes, stale: value.stale === true };
}

function toSignalRows(market: string, heatmap: HeatmapPayload | null, overview: GlobalOverviewGroup[]): { rows: SectorInput[]; marketChange: number; trackedLabel: 'markets' | 'sectors' } {
  if (market === 'GLOBAL') {
    const rows = overview.flatMap((group) => {
      const change = group.index?.changePct;
      if (!Number.isFinite(change)) return [];
      const top = group.stocks.reduce<GlobalOverviewGroup['stocks'][number] | null>(
        (best, stock) => (best === null || stock.changePct > best.changePct ? stock : best),
        null,
      );
      return [{
        name: group.name || group.country,
        change: change as number,
        weight: group.stocks.length || 1,
        stocks: group.stocks.length,
        topSymbol: top?.symbol,
        topName: top?.name,
        topChange: top?.changePct,
      }];
    });
    return { rows, marketChange: mean(rows.map((row) => row.change)) ?? 0, trackedLabel: 'markets' };
  }
  const rows = (heatmap?.sectors ?? []).map((sector) => {
    const top = sector.stocks.reduce<(typeof sector.stocks)[number] | null>(
      (best, stock) => (best === null || stock.changePct > best.changePct ? stock : best),
      null,
    );
    return {
      name: sector.name,
      change: sector.change,
      weight: sector.marketCap,
      stocks: sector.stocks.length,
      topSymbol: top?.symbol,
      topName: top?.name,
      topChange: top?.changePct,
    };
  });
  return { rows, marketChange: heatmap?.change ?? 0, trackedLabel: 'sectors' };
}

export function useHomeData(active: boolean): HomeData {
  const [market, setMarketState] = useState('GLOBAL');
  const [reload, setReload] = useState(0);
  const [regime, setRegime] = useState<RegimeResult | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapPayload | null>(null);
  const [overview, setOverview] = useState<GlobalOverviewGroup[]>([]);
  const [benchmark, setBenchmark] = useState<BenchmarkSeries | null>(null);
  const [alerts, setAlerts] = useState<HomeAlert[]>([]);
  const [newsItems, setNewsItems] = useState<NewsLike[]>([]);
  const [earningsRows, setEarningsRows] = useState<EarningsLike[]>([]);
  const [econEvents, setEconEvents] = useState<EconEventLike[]>([]);
  const [theses, setTheses] = useState<ThesisLike[]>([]);
  const [journalPerf, setJournalPerf] = useState<JournalPerformanceLike | null>(null);
  const [earningsSource, setEarningsSource] = useState('unavailable');
  const [feedLoading, setFeedLoading] = useState(true);
  const [feedSeenAt, setFeedSeenAt] = useState(0);
  const [minuteTick, setMinuteTick] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  useEffect(() => {
    try { setFeedSeenAt(Number(window.localStorage.getItem(FEED_SEEN_KEY)) || 0); } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    setMarketState(readMarket());
  }, []);

  const setMarket = useCallback((next: string) => {
    const normalized = next.toUpperCase();
    if (!KNOWN_MARKETS.has(normalized)) return;
    setMarketState(normalized);
    writeMarket(normalized);
  }, []);

  const refresh = useCallback(() => setReload((value) => value + 1), []);

  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setReload((value) => value + 1), 120_000);
    return () => window.clearInterval(id);
  }, [active]);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    setLoading(true);
    setLoadError(false);

    const regimeUrl = market === 'GLOBAL'
      ? '/api/regime?scope=global'
      : `/api/regime?scope=selected&market=${encodeURIComponent(market)}`;
    const marketUrl = market === 'GLOBAL' ? null : `/api/heatmap?market=${encodeURIComponent(market)}`;
    const overviewUrl = market === 'GLOBAL' ? '/api/global-overview' : null;
    const meta = benchmarkFor(market);
    const benchmarkUrl = meta
      ? `/api/price-history?symbol=${encodeURIComponent(meta.symbol)}&market=${encodeURIComponent(meta.market)}&range=6mo`
      : null;

    void (async () => {
      const [regimeResult, marketResult, overviewResult, benchmarkResult, alertResult] = await Promise.all([
        fetchJson<RegimeResult>(regimeUrl, controller.signal),
        marketUrl ? fetchJson<HeatmapPayload>(marketUrl, controller.signal) : Promise.resolve<Fetched<HeatmapPayload>>({ data: null, error: false }),
        overviewUrl ? fetchJson<{ groups?: GlobalOverviewGroup[] }>(overviewUrl, controller.signal) : Promise.resolve<Fetched<{ groups?: GlobalOverviewGroup[] }>>({ data: null, error: false }),
        benchmarkUrl && meta ? fetchJson<unknown>(benchmarkUrl, controller.signal) : Promise.resolve<Fetched<unknown>>({ data: null, error: false }),
        fetchJson<unknown>('/api/alerts', controller.signal),
      ]);
      if (cancelled) return;
      setRegime(regimeResult.data);
      setHeatmap(marketResult.data);
      setOverview(Array.isArray(overviewResult.data?.groups) ? overviewResult.data.groups : []);
      setBenchmark(benchmarkResult.data && meta ? parseBenchmark(benchmarkResult.data, meta) : null);
      setAlerts(parseAlerts(alertResult.data));
      const marketFeed = market === 'GLOBAL' ? overviewResult : marketResult;
      setLoadError([regimeResult, marketFeed, benchmarkResult].every((result) => result.error));
      setUpdatedAt(new Date());
      setLoading(false);
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [market, reload]);

  const portfolio = useAggregatePortfolio();
  const quoteBySymbol = useMemo(
    () => new Map(portfolio.quotes.map((quote) => [quote.symbol.toUpperCase(), quote])),
    [portfolio.quotes],
  );
  const heldSymbols = useMemo(
    () => portfolio.stats.holdings.map((holding) => holding.symbol.toUpperCase()),
    [portfolio.stats.holdings],
  );
  const marketsHint = useMemo(() => {
    const map: Record<string, string> = {};
    for (const symbol of heldSymbols) {
      map[symbol] = quoteBySymbol.get(symbol)?.marketId ?? marketHintFor(symbol);
    }
    return map;
  }, [heldSymbols, quoteBySymbol]);
  const histories = usePriceHistories(heldSymbols, marketsHint);

  const holdings = useMemo(() => {
    const raw = portfolio.stats.holdings.map((holding) => {
      const symbol = holding.symbol.toUpperCase();
      const quote = quoteBySymbol.get(symbol);
      return {
        symbol,
        name: holding.name || symbol,
        valueUsd: holding.valueUsd,
        valueNative: holding.value,
        currency: holding.currency || 'USD',
        marketId: quote?.marketId ?? marketHintFor(symbol),
        sector: quote?.sector,
        changePercent: Number.isFinite(holding.dayPct) ? holding.dayPct : 0,
        closes: histories.closes[symbol] ?? [],
        dates: histories.dates[symbol] ?? [],
        avgCost: holding.avgCost,
        quantity: holding.quantity,
        unrealizedPct: holding.avgCost > 0 ? (holding.currentPrice / holding.avgCost - 1) * 100 : null,
        fxMissing: holding.fxMissing,
      };
    });
    return buildHomeHoldings(raw, market);
  }, [portfolio.stats.holdings, quoteBySymbol, histories.closes, histories.dates, market]);

  const trendMix = useMemo(() => buildTrendMix(holdings), [holdings]);
  const health = useMemo(() => buildHealth(holdings), [holdings]);
  const concentration = useMemo(() => buildConcentration(holdings), [holdings]);
  const review = useMemo(
    () => holdings.filter((holding) => holding.trend === 'downtrend').sort((a, b) => b.weightPct - a.weightPct),
    [holdings],
  );
  const best = useMemo(
    () => holdings.filter((holding) => holding.trend === 'uptrend').sort((a, b) => b.weightPct - a.weightPct),
    [holdings],
  );
  const stable = useMemo(
    () => holdings.filter((holding) => holding.trend === 'weak_uptrend').sort((a, b) => b.weightPct - a.weightPct),
    [holdings],
  );

  const { rows: signalRows, marketChange, trackedLabel } = useMemo(
    () => toSignalRows(market, heatmap, overview),
    [market, heatmap, overview],
  );
  const signals = useMemo(() => sectorSignals(signalRows, marketChange), [signalRows, marketChange]);
  const breadth = useMemo(() => sectorBreadth(signals), [signals]);
  const leading = useMemo(() => leadingSignal(signals), [signals]);
  const regimeReadingTone = useMemo(() => regimeTone(regime), [regime]);
  const breadthTone = useMemo(
    () => weatherTone(marketChange, breadth.advancing, breadth.tracked),
    [marketChange, breadth.advancing, breadth.tracked],
  );
  const tone = regimeReadingTone === 'unavailable' ? breadthTone : regimeReadingTone;
  const weatherSource: HomeData['weatherSource'] = regimeReadingTone !== 'unavailable'
    ? 'regime'
    : breadthTone !== 'unavailable' ? 'breadth' : 'unavailable';
  const needle = useMemo(() => regimeNeedle(regime), [regime]);

  const { items: watchItems } = useWatchlist();
  const watchSymbols = useMemo(() => watchItems.map((item) => item.symbol), [watchItems]);
  const watchQuotes = useLiveQuotes(watchSymbols);
  const radar = useMemo(() => {
    const quotes = Object.values(watchQuotes.quotes).map((quote) => ({
      symbol: quote.symbol,
      name: quote.name,
      price: quote.price,
      changePercent: quote.changePercent,
      currency: quote.currency,
      marketId: quote.marketId,
    }));
    return buildRadar(quotes, new Set(portfolio.stats.holdings.map((holding) => holding.symbol.toUpperCase())));
  }, [watchQuotes.quotes, portfolio.stats.holdings]);

  const heldSet = useMemo(() => new Set(heldSymbols), [heldSymbols]);
  const watchSet = useMemo(() => new Set(watchSymbols.map((symbol) => symbol.toUpperCase())), [watchSymbols]);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    setFeedLoading(true);
    const newsUrl = '/api/news?limit=30';
    void (async () => {
      const [newsResult, earningsResult, econResult, thesesResult, journalResult] = await Promise.all([
        fetchJson<NewsResponse>(newsUrl, controller.signal),
        fetchJson<EarningsResponse>('/api/earnings', controller.signal),
        fetchJson<EconResponse>('/api/economics/calendar', controller.signal),
        fetchJson<ThesesResponse>('/api/theses', controller.signal),
        fetchJson<JournalResponse>('/api/journal/analytics', controller.signal),
      ]);
      if (cancelled) return;
      setNewsItems(Array.isArray(newsResult.data?.news) ? newsResult.data.news : []);
      setEarningsRows(Array.isArray(earningsResult.data?.rows) ? earningsResult.data.rows : []);
      setEarningsSource(earningsResult.data?.source ?? 'unavailable');
      setEconEvents(Array.isArray(econResult.data?.events) ? econResult.data.events : []);
      setTheses(Array.isArray(thesesResult.data?.theses) ? thesesResult.data.theses : []);
      setJournalPerf(journalResult.data?.analytics?.performance ?? null);
      setFeedLoading(false);
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [reload]);

  const activeAlerts = alerts.filter((alert) => alert.active).length;
  const recentAlerts = useMemo(
    () => alerts
      .filter((alert) => alert.lastFiredAt)
      .sort((a, b) => String(b.lastFiredAt).localeCompare(String(a.lastFiredAt)))
      .slice(0, 3),
    [alerts],
  );

  const marketLabel = useMemo(() => marketLabelFor(market), [market]);
  const holdingsHealth = useMemo(() => buildHoldingsHealth(holdings), [holdings]);
  const portfolioSeries = useMemo(
    () => buildPortfolioVsBenchmark(holdings, benchmark ? { dates: benchmark.dates, closes: benchmark.closes } : null),
    [holdings, benchmark],
  );
  const pulse = useMemo(() => buildMarketPulse({
    market,
    marketLabel,
    overview,
    heatmap,
    signals,
    breadth,
    marketChange,
    leading,
  }), [market, marketLabel, overview, heatmap, signals, breadth, marketChange, leading]);
  const resultsSeason = useMemo(() => buildResultsSeason(earningsRows, earningsSource), [earningsRows, earningsSource]);
  const leaderUniverse = useMemo<OverviewGroupLike[]>(() => {
    if (market === 'GLOBAL') return overview;
    if (!heatmap) return [];
    const stocks = heatmap.sectors.flatMap((sector) => sector.stocks.map((stock) => ({
      symbol: stock.symbol,
      name: stock.name,
      changePct: stock.changePct,
      marketCap: stock.rawMarketCap ?? stock.marketCap,
    })));
    return [{ id: market, country: marketLabel, name: marketLabel, index: { changePct: marketChange }, stocks }];
  }, [market, marketLabel, overview, heatmap, marketChange]);
  const leaders = useMemo(() => buildLeaders(leaderUniverse, heldSet, watchSet), [leaderUniverse, heldSet, watchSet]);
  const research = useMemo(() => buildResearch(theses, heldSet, watchSet), [theses, heldSet, watchSet]);
  useEffect(() => {
    const id = window.setInterval(() => setMinuteTick((value) => value + 1), 60_000);
    return () => window.clearInterval(id);
  }, []);

  const record = useMemo(() => buildRecord(journalPerf, theses), [journalPerf, theses]);
  const weekEvents = useMemo(() => buildWeekEvents(earningsRows, econEvents, heldSet, watchSet), [earningsRows, econEvents, heldSet, watchSet]);
  const feed = useMemo(() => buildFeed({
    news: newsItems,
    alerts,
    earnings: earningsRows,
    held: heldSet,
    watching: watchSet,
    pulse,
  }), [newsItems, alerts, earningsRows, heldSet, watchSet, pulse]);
  const feedNewCount = useMemo(() => feed.filter((item) => item.at > feedSeenAt).length, [feed, feedSeenAt]);
  const attribution = useMemo(() => buildAttribution(holdings, market !== 'GLOBAL'), [holdings, market]);
  const earningsDates = useMemo(() => {
    const map: Record<string, string> = {};
    for (const row of earningsRows) {
      const key = row.symbol.toUpperCase();
      if (!map[key]) map[key] = row.date;
    }
    return map;
  }, [earningsRows]);
  const earningsBySymbol = useMemo(() => {
    const map = new Map<string, number>();
    for (const [symbol, date] of Object.entries(earningsDates)) {
      const ts = Date.parse(date.length === 10 ? `${date}T00:00:00` : date);
      if (Number.isFinite(ts)) map.set(symbol, ts);
    }
    return map;
  }, [earningsDates]);
  const actionList = useMemo(() => buildActionList(holdingsHealth, earningsBySymbol), [holdingsHealth, earningsBySymbol]);
  const sessions = useMemo(() => { void minuteTick; return buildMarketSessions(); }, [minuteTick]);
  const risk = useMemo(
    () => buildPortfolioRisk(holdings, benchmark ? { dates: benchmark.dates, closes: benchmark.closes } : null),
    [holdings, benchmark],
  );
  const fxExposure = useMemo(() => buildFxExposure(holdings), [holdings]);
  const rotation = useMemo(() => buildSectorRotation(signals), [signals]);

  const markFeedSeen = useCallback(() => {
    const now = Date.now();
    try { window.localStorage.setItem(FEED_SEEN_KEY, String(now)); } catch { /* ignore */ }
    setFeedSeenAt(now);
  }, []);
  const displayCurrency = useMemo(() => {
    const currencies = new Set(holdings.map((holding) => holding.currency));
    return market !== 'GLOBAL' && currencies.size === 1 ? [...currencies][0] : 'USD';
  }, [holdings, market]);

  const portfolioValue = useMemo(
    () => holdings.reduce(
      (sum, holding) => sum + (displayCurrency === 'USD' ? holding.valueUsd : holding.valueNative),
      0,
    ),
    [holdings, displayCurrency],
  );
  const portfolioChangePct = useMemo(() => {
    const weight = holdings.reduce((sum, holding) => sum + holding.valueUsd, 0);
    if (weight <= 0) return 0;
    return holdings.reduce((sum, holding) => sum + holding.changePercent * holding.valueUsd, 0) / weight;
  }, [holdings]);
  const portfolioChangeValue = holdings.reduce(
    (sum, holding) => sum + (displayCurrency === 'USD' ? holding.valueUsd : holding.valueNative) * (holding.changePercent / 100),
    0,
  );

  const funds = portfolio.funds;
  const demoCount = funds.filter((fund) => fund.seeded).length;
  const includesDemo = demoCount > 0;
  const demoOnly = demoCount > 0 && demoCount === funds.length;
  const fxMissingCount = holdings.filter((holding) => holding.fxMissing).length;
  const positionsLoading = portfolio.stats.holdings.length > 0 && portfolio.loading && portfolio.quotes.length === 0;
  const historyLoading = heldSymbols.length > 0 && histories.loading;

  const brief = useMemo(() => buildPersonalBrief({
    tone,
    health,
    review,
    leading,
    radar,
    holdings: holdings.length,
    marketLabel: marketLabelFor(market),
    tracked: breadth.tracked,
    trackedLabel,
    advancing: breadth.advancing,
    positionsLoading,
    historyLoading,
  }), [tone, health, review, leading, radar, holdings.length, market, breadth.tracked, breadth.advancing, trackedLabel, positionsLoading, historyLoading]);

  const universe = useMemo(() => {
    if (market === 'GLOBAL') {
      return {
        markets: overview.length,
        instruments: overview.reduce((sum, group) => sum + group.stocks.length, 0),
        advancing: breadth.advancing,
        tracked: breadth.tracked,
      };
    }
    return {
      markets: 1,
      instruments: heatmap?.live ?? 0,
      advancing: breadth.advancing,
      tracked: breadth.tracked,
    };
  }, [market, overview, heatmap, breadth]);

  return {
    market,
    setMarket,
    marketOptions: HOME_MARKETS,
    marketLabel,
    active,
    loading,
    loadError,
    updatedAt,
    refresh,
    regime,
    tone,
    regimeTone: regimeReadingTone,
    weatherSource,
    needle,
    benchmark,
    signals,
    leading,
    breadth,
    marketChange,
    trackedLabel,
    holdings,
    trendMix,
    health,
    review,
    best,
    stable,
    concentration,
    radar,
    brief,
    alerts,
    activeAlerts,
    recentAlerts,
    portfolioValue,
    portfolioChangePct,
    portfolioChangeValue,
    displayCurrency,
    holdingsCount: holdings.length,
    fxMissingCount,
    positionsLoading,
    historyLoading,
    demoOnly,
    includesDemo,
    universe,
    fundsCount: funds.length,
    portfolioSeries,
    portfolioReturnPct: portfolio.stats.roiPercent,
    portfolioCostBasis: portfolio.stats.costBasis,
    holdingsHealth,
    feed,
    feedNewCount,
    feedLoading,
    markFeedSeen,
    weekEvents,
    pulse,
    resultsSeason,
    earningsSource,
    leaders,
    research,
    record,
    attribution,
    actionList,
    sessions,
    risk,
    fxExposure,
    rotation,
    earningsDates,
  };
}
