// ── Fundamentals provider registry ──────────────────────────────────────────
// Precedence is explicit and separate from the connector-layer resolver: for
// fundamentals the goal is to MERGE complementary sources (SEC = authoritative
// filings, FMP/Yahoo = market-derived multiples and estimates), not to pick one.
//
// `PROVIDER_ORDER` is the statement/authority order. The service treats the
// first provider that returns periods as the primary statement source and fills
// quote/valuation/ownership gaps from whichever provider has them.

import type { FundamentalProviderId, FundamentalsProvider } from '../types';
import { secFundamentalsProvider } from './sec-edgar';
import { fmpFundamentalsProvider } from './fmp';
import { yahooFundamentalsProvider } from './yahoo';

/** Statement authority: SEC filings first, then normalized vendors, then Yahoo. */
export const PROVIDER_ORDER: FundamentalProviderId[] = [
  'sec-edgar',
  'financialmodelingprep',
  'yahoo',
];

export const FUNDAMENTALS_PROVIDERS: Record<FundamentalProviderId, FundamentalsProvider> = {
  'sec-edgar': secFundamentalsProvider,
  financialmodelingprep: fmpFundamentalsProvider,
  yahoo: yahooFundamentalsProvider,
};

/** Providers in precedence order, filtered to those usable right now. */
export async function configuredProviders(
  symbol: string,
  market: string
): Promise<FundamentalsProvider[]> {
  const checks = await Promise.all(
    PROVIDER_ORDER.map(async (id) => {
      const provider = FUNDAMENTALS_PROVIDERS[id];
      if (!provider.supports(symbol, market)) return null;
      const ok = await Promise.resolve(provider.isConfigured()).catch(() => false);
      return ok ? provider : null;
    })
  );
  return checks.filter((p): p is FundamentalsProvider => p !== null);
}
