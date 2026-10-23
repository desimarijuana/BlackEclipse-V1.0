import { NextResponse } from 'next/server';
import { fetchCapability } from '@/lib/harness/data-bridge';
import { rateLimit, clientKey } from '@/lib/api-guard';
import {
  buildVerificationQueries,
  filingsCheck,
  identityCheck,
  listingCheck,
  officialDomainsForMarket,
  overallState,
  quoteCheck,
  type SearchResultLike,
  type StockVerificationResponse,
  type VerificationCheck,
} from '@/lib/stock-intelligence/verification';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;

const CACHE_TTL_MS = 30 * 60 * 1000;
const cache = new Map<string, { at: number; payload: StockVerificationResponse }>();
const inFlight = new Map<string, Promise<StockVerificationResponse>>();

async function search(query: string): Promise<SearchResultLike[]> {
  try {
    const result = await fetchCapability('web_search', { query, limit: 6 });
    if (result.status !== 'OK') return [];
    const rows = (result as { results?: unknown }).results;
    if (!Array.isArray(rows)) return [];
    return rows
      .filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === 'object')
      .map((row) => ({
        title: typeof row.title === 'string' ? row.title : undefined,
        url: typeof row.url === 'string' ? row.url : undefined,
        snippet: typeof row.snippet === 'string' ? row.snippet : undefined,
      }));
  } catch {
    return [];
  }
}

async function verify(
  symbol: string,
  market: string,
  companyName: string | null,
  price: number | null,
): Promise<StockVerificationResponse> {
  const domains = officialDomainsForMarket(market);
  const queries = buildVerificationQueries(symbol, companyName, market);

  const [identity, listing, filings, quote] = await Promise.all([
    search(queries.identity),
    search(queries.listing),
    search(queries.filings),
    search(queries.quote),
  ]);

  const warnings: string[] = [];
  if (identity.length === 0) warnings.push('Identity search returned no results.');
  if (listing.length === 0) warnings.push('Official listing search returned no results.');
  if (filings.length === 0) warnings.push('Filing search returned no results.');
  if (quote.length === 0) warnings.push('Quote cross-check search returned no results.');

  const checks: VerificationCheck[] = [
    identityCheck(identity, symbol, companyName, domains),
    listingCheck(identity, listing, symbol, market, domains),
    filingsCheck(identity, filings, symbol, domains),
    quoteCheck(quote, symbol, price, domains),
  ];

  return {
    available: checks.some((check) => check.evidence.length > 0),
    symbol,
    market,
    companyName,
    generatedAt: new Date().toISOString(),
    overall: overallState(checks),
    checks,
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
  const companyName = (url.searchParams.get('name') ?? '').trim() || null;
  const rawPrice = Number(url.searchParams.get('price'));
  const price = Number.isFinite(rawPrice) && rawPrice > 0 ? rawPrice : null;

  if (!symbol) {
    return NextResponse.json({ available: false, reason: 'A symbol is required.' }, { status: 400 });
  }

  const rl = rateLimit(`stock-verification:${clientKey(request)}`, { limit: 20, windowMs: 60_000 });
  if (!rl.ok) {
    return NextResponse.json(
      { available: false, symbol, market, reason: 'Too many verification requests — slow down.' },
      { status: 429, headers: { 'Retry-After': String(rl.retryAfterSec) } },
    );
  }

  const key = `${symbol}|${market}|${companyName ?? ''}|${price ?? ''}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < CACHE_TTL_MS) return NextResponse.json(hit.payload);

  try {
    let pending = inFlight.get(key);
    if (!pending) {
      pending = verify(symbol, market, companyName, price);
      inFlight.set(key, pending);
      void pending.finally(() => inFlight.delete(key));
    }
    const payload = await pending;
    cache.set(key, { at: Date.now(), payload });
    return NextResponse.json(payload);
  } catch (error) {
    console.error('[api/stocks/verification] error:', error);
    return NextResponse.json({
      available: false,
      symbol,
      market,
      companyName,
      generatedAt: new Date().toISOString(),
      overall: 'UNAVAILABLE',
      checks: [],
      warnings: [],
      reason: 'Source verification failed.',
    } satisfies StockVerificationResponse);
  }
}
