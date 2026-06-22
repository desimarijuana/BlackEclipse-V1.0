import { NextResponse } from 'next/server';
import YahooFinance from 'yahoo-finance2';

const yahooFinance = new YahooFinance();

export const dynamic = 'force-dynamic';

// Server-side cache
const historicalCache = new Map<string, { timestamp: number; candles: any[] }>();
const CACHE_TTL_MS = 30 * 60 * 1000; 

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const rawSymbol = searchParams.get('symbol') || 'BTC';
    const startParam = searchParams.get('start');
    const endParam = searchParams.get('end');
    const intervalParam = searchParams.get('interval') || '1d';

    let ticker = rawSymbol.toUpperCase().trim();
    
    // Ticker normalization
    if (['BTC', 'ETH', 'SOL', 'ADA', 'XRP', 'DOT', 'DOGE', 'BNB', 'LINK', 'AVAX'].includes(ticker)) {
      ticker = `${ticker}-USD`;
    } else if (ticker.endsWith('USDT') || ticker.endsWith('/USD')) {
      ticker = ticker.replace('USDT', '-USD').replace('/USD', '-USD');
    }

    const now = new Date();
    const startDate = startParam ? new Date(startParam) : new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
    const endDate = endParam ? new Date(endParam) : now;

    if (isNaN(startDate.getTime()) || isNaN(endDate.getTime())) {
      return NextResponse.json({ error: 'Invalid start or end date format.' }, { status: 400 });
    }

    // Interval mappings
    const validIntervals = ['1m', '5m', '15m', '1h', '1d', '1wk', '1mo'];
    const interval = validIntervals.includes(intervalParam) ? intervalParam : '1d';

    // Build unique cache key
    const cacheKey = `${ticker}_${startDate.toISOString().split('T')[0]}_${endDate.toISOString().split('T')[0]}_${interval}`;

    // Inspect server cache
    const cached = historicalCache.get(cacheKey);
    if (cached && (Date.now() - cached.timestamp < CACHE_TTL_MS)) {
      return NextResponse.json({
        symbol: ticker,
        count: cached.candles.length,
        candles: cached.candles,
        cached: true
      });
    }

    // Fetch data using yahooFinance.chart
    const queryOptions = {
      period1: Math.floor(startDate.getTime() / 1000),
      period2: Math.floor(endDate.getTime() / 1000),
      interval: interval as any,
    };

    const chartResult = await yahooFinance.chart(ticker, queryOptions);
    const results = chartResult.quotes || [];

    if (!results || results.length === 0) {
      return NextResponse.json({ error: 'No historical chart data found for this asset.' }, { status: 404 });
    }

    const candles = results
      .filter(bar => 
        bar.close !== null && bar.close !== undefined &&
        bar.open !== null && bar.open !== undefined &&
        bar.high !== null && bar.high !== undefined &&
        bar.low !== null && bar.low !== undefined
      )
      .map(bar => ({
        date: bar.date.toISOString().split('T')[0] + (['1m', '5m', '15m', '1h'].includes(interval) ? ` ${bar.date.toTimeString().split(' ')[0].slice(0, 5)}` : ''),
        open: bar.open!,
        high: bar.high!,
        low: bar.low!,
        close: bar.close!,
        volume: bar.volume || 0,
      }));

    if (candles.length === 0) {
      return NextResponse.json({ error: 'No valid data wicks/quotes after mapping.' }, { status: 404 });
    }

    // Populate server cache
    historicalCache.set(cacheKey, {
      timestamp: Date.now(),
      candles
    });

    return NextResponse.json({
      symbol: ticker,
      count: candles.length,
      candles,
      cached: false
    });
  } catch (error: any) {
    console.error('[Backtest API Error]:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to fetch historical asset data.' },
      { status: 500 }
    );
  }
}
