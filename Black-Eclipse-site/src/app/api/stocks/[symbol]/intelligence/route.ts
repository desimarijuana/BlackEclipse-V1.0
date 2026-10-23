import { NextResponse } from 'next/server';
import { prisma } from '@/lib/db';
import { getFundamentals } from '@/lib/fundamentals';
import { PROVIDER_LABELS, type MetricSource } from '@/lib/fundamentals/types';
import { INDEX_DEFS } from '@/lib/indices';
import { fetchYahooChartSeries, yahooChartCandidates, type Bar } from '@/lib/scraper/yahoo-chart';
import { fetchStooqDailySeries } from '@/lib/scraper/stooq-chart';
import { rateLimit, clientKey } from '@/lib/api-guard';
import {
  buildDrawdown,
  buildEarningsSurprise,
  buildPriceTrend,
  buildRelativePerformance,
  buildValuationBand,
  type BenchmarkRef,
  type PriceClosePoint,
} from '@/lib/stock-intelligence/charts';
import type {
  StockChart,
  StockIntelligenceResponse,
  StockSourceRef,
  StockSourceTier,
} from '@/lib/stock-intelligence/types';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;

interface CachedResponse {
  at: number;
  payload: StockIntelligenceResponse;
}

const CACHE_TTL_MS = 5 * 60 * 1000;
const cache = new Map<string, CachedResponse>();
const inFlight = new Map<string, Promise<StockIntelligenceResponse>>();

function benchmarkFor(market: string): BenchmarkRef | null {
  if (market === 'CRYPTO') return { symbol: 'BTC-USD', label: 'Bitcoin' };
  if (market === 'GLOBAL') return { symbol: '^GSPC', label: 'S&P 500' };
  const def = INDEX_DEFS.find((entry) => entry.market === market && entry.provider === 'yahoo');
  return def ? { symbol: def.symbol, label: def.name } : null;
}

function toPoints(bars: Bar[]): PriceClosePoint[] {
  return bars.map((bar) => ({ date: bar.date, close: bar.close }));
}

interface PriceBars {
  bars: Bar[];
  source: StockSourceRef;
}

function unavailableSource(label: string): StockSourceRef {
  return { id: 'price-history', label, tier: 'none' };
}

async function fetchBars(symbol: string, market: string, range: string): Promise<PriceBars> {
  for (const ticker of yahooChartCandidates(symbol, market)) {
    try {
      const chart = await fetchYahooChartSeries(ticker, range, '1d');
      if (chart && chart.bars.length >= 2) {
        return {
          bars: chart.bars,
          source: {
            id: 'yahoo',
            label: `Yahoo Finance · ${ticker}`,
            tier: 'provider',
            asOf: chart.bars.at(-1)?.date ?? null,
          },
        };
      }
    } catch {
      // Try the next candidate/provider. The empty result is reported below.
    }
  }

  const stooq = await fetchStooqDailySeries(symbol, market, range);
  if (stooq.length >= 2) {
    return {
      bars: stooq,
      source: {
        id: 'stooq',
        label: 'Stooq daily closes',
        tier: 'provider',
        asOf: stooq.at(-1)?.date ?? null,
      },
    };
  }

  return { bars: [], source: unavailableSource('No daily price provider returned a series') };
}

/**
 * The screener row sometimes omits the country (notably ADX/DFM rows), which
 * made the overlay request US data for a UAE ticker. Resolve the listing market
 * from JDdS before asking any provider for bars.
 */
async function resolveMarket(symbol: string, hinted: string): Promise<string> {
  try {
    const rows = await prisma.asset.findMany({
      where: { symbol, isActive: true },
      select: { marketId: true, securityType: true },
      take: 40,
    });
    if (rows.length === 0) return hinted;
    const present = [...new Set(rows.map((row) => row.marketId))];
    if (present.includes(hinted)) return hinted;
    const stocks = present.filter((market) => {
      const row = rows.find((entry) => entry.marketId === market);
      return row?.securityType ? /stock/i.test(row.securityType) : false;
    });
    return stocks[0] ?? present[0] ?? hinted;
  } catch {
    return hinted;
  }
}

function fundamentalsSource(source: MetricSource): { label: string; tier: StockSourceTier } {
  if (source === 'derived') return { label: 'Derived from reported statements', tier: 'derived' };
  return {
    label: PROVIDER_LABELS[source] ?? source,
    tier: source === 'sec-edgar' || source === 'eclipse-filings' ? 'filing' : 'provider',
  };
}

function unavailableChart(
  id: StockChart['id'],
  title: string,
  subtitle: string,
  unit: StockChart['unit'],
  reason: string,
): StockChart {
  return {
    id,
    title,
    subtitle,
    unit,
    state: 'UNAVAILABLE',
    labels: [],
    series: [],
    provenance: { state: 'UNAVAILABLE', sources: [] },
    reason,
  };
}

async function buildIntelligence(symbol: string, requestedMarket: string): Promise<StockIntelligenceResponse> {
  const market = await resolveMarket(symbol, requestedMarket);
  const benchmark = benchmarkFor(market);
  const warnings: string[] = [];

  const [fund, stockHistory, benchmarkHistory] = await Promise.all([
    getFundamentals(symbol, market).catch(() => null),
    fetchBars(symbol, market, '5y'),
    benchmark
      ? fetchBars(benchmark.symbol, market, '1y')
      : Promise.resolve({ bars: [] as Bar[], source: unavailableSource('No benchmark') }),
  ]);

  if (!fund) warnings.push('Fundamentals are unavailable for this symbol.');
  if (stockHistory.bars.length < 2) warnings.push('Daily price history is unavailable for this symbol.');
  if (benchmark && benchmarkHistory.bars.length < 2) {
    warnings.push(`Benchmark history is unavailable for ${benchmark.label}.`);
  }
  if (!benchmark) warnings.push(`No benchmark is registered for the ${market} market.`);
  if (market !== requestedMarket) {
    warnings.push(`Listing market resolved from JDdS: ${requestedMarket || 'unknown'} -> ${market}.`);
  }

  const source = fund ? fundamentalsSource(fund.primarySource) : { label: 'Unavailable', tier: 'none' as const };
  const stockPoints = toPoints(stockHistory.bars);
  const benchmarkPoints = toPoints(benchmarkHistory.bars);

  const charts: StockChart[] = [
    buildPriceTrend(stockPoints, stockHistory.source, symbol, fund?.currency ?? null),
    buildDrawdown(stockPoints, stockHistory.source),
    benchmark
      ? buildRelativePerformance(
          stockPoints,
          benchmarkPoints,
          benchmark,
          6,
          symbol,
          stockHistory.source,
          benchmarkHistory.source,
        )
      : unavailableChart(
          'relative-performance',
          'Relative performance',
          '6M total return vs the home-market benchmark',
          'percent',
          `No benchmark is registered for the ${market} market.`,
        ),
    fund
      ? buildValuationBand(fund.periods, stockPoints, source.label, source.tier, stockHistory.source)
      : unavailableChart(
          'valuation-band',
          'Historical P/E',
          'Price at fiscal year-end ÷ reported EPS',
          'ratio',
          'Fundamentals are unavailable for this symbol.',
        ),
    fund
      ? buildEarningsSurprise(fund.earnings.history, source.label, source.tier)
      : unavailableChart(
          'earnings-surprise',
          'Earnings surprise',
          'Actual EPS vs consensus estimate',
          'percent',
          'Fundamentals are unavailable for this symbol.',
        ),
  ];

  const currency = fund?.currency ?? null;

  return {
    available: charts.some((chart) => chart.state === 'READY') || fund !== null,
    symbol,
    market,
    currency,
    generatedAt: new Date().toISOString(),
    charts,
    warnings,
  };
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ symbol: string }> },
) {
  const { symbol: rawSymbol } = await params;
  const symbol = rawSymbol.trim().toUpperCase();
  const url = new URL(request.url);
  const market = (url.searchParams.get('market') ?? 'US').trim().toUpperCase();

  if (!symbol) {
    return NextResponse.json({ available: false, reason: 'A symbol is required.' }, { status: 400 });
  }

  const rl = rateLimit(`stock-intelligence:${clientKey(request)}`, { limit: 30, windowMs: 60_000 });
  if (!rl.ok) {
    return NextResponse.json(
      { available: false, symbol, market, reason: 'Too many requests — slow down.' },
      { status: 429, headers: { 'Retry-After': String(rl.retryAfterSec) } },
    );
  }

  const key = `${symbol}|${market}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < CACHE_TTL_MS) {
    return NextResponse.json(hit.payload);
  }

  try {
    let pending = inFlight.get(key);
    if (!pending) {
      pending = buildIntelligence(symbol, market);
      inFlight.set(key, pending);
      void pending.then(
        () => inFlight.delete(key),
        () => inFlight.delete(key),
      );
    }
    const payload = await pending;
    cache.set(key, { at: Date.now(), payload });
    return NextResponse.json(payload);
  } catch (error) {
    console.error('[api/stocks/intelligence] error:', error);
    return NextResponse.json(
      {
        available: false,
        symbol,
        market,
        currency: null,
        generatedAt: new Date().toISOString(),
        charts: [],
        warnings: [],
        reason: 'Stock intelligence fetch failed.',
      } satisfies StockIntelligenceResponse,
      { status: 200 },
    );
  }
}
