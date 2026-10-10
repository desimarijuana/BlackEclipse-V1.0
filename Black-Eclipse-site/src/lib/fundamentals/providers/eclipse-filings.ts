// ── Eclipse Filings provider (first-party, official exchange data) ───────────
// When SEC/FMP/Yahoo have nothing (or only a thin quote) for a market, Eclipse
// reads the OFFICIAL exchange disclosure directly through a market adapter
// (`../filings/registry`). First adapter: PSX (Pakistan). No key, no third-party
// vendor — the exchange's own numbers.
//
// Extensible by design: add a market adapter under `../filings/` and register it
// in the adapter list. Provenance stays explicit (`eclipse-filings`) so the UI
// never presents exchange data as a vendor snapshot or vice-versa.

import type { FundamentalsProvider, ProviderFundamentals } from '../types';
import { adapterFor, FILINGS_ADAPTERS } from '../filings/registry';

/** Upper-case market ids any registered adapter can serve. */
export const FILINGS_MARKETS: string[] = FILINGS_ADAPTERS.flatMap((a) => a.markets);

export const eclipseFilingsProvider: FundamentalsProvider = {
  id: 'eclipse-filings',
  label: 'Eclipse Filings (exchange)',

  // Keyless and always available — it reads public exchange pages.
  isConfigured: () => true,

  supports: (_symbol: string, market: string) => Boolean(adapterFor(market)),

  async fetch(symbol: string, market: string): Promise<ProviderFundamentals | null> {
    const adapter = adapterFor(market);
    if (!adapter) return null;
    const result = await adapter.fetch(symbol);
    if (!result || result.periods.length === 0) return null;
    return {
      provider: 'eclipse-filings',
      symbol: symbol.trim().toUpperCase(),
      currency: result.currency,
      company: result.company ?? {},
      periods: result.periods,
      timeline: [{ date: result.periods[result.periods.length - 1]?.endDate ?? '', label: `Source: ${result.source}` }],
      retrievedAt: new Date().toISOString(),
    };
  },
};
