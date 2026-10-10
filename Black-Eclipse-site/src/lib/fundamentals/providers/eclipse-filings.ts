// ── Eclipse Filings provider (first-party, official exchange data) ───────────
// When SEC/FMP/Yahoo have nothing (or only a thin quote) for a market, Eclipse
// reads the OFFICIAL exchange disclosure directly. First adapter: PSX
// (Pakistan). No key, no third-party vendor — the exchange's own numbers.
//
// Extensible by design: add a market adapter under `../filings/` and one branch
// here. Provenance stays explicit (`eclipse-filings`) so the UI never presents
// exchange data as a vendor snapshot or vice-versa.

import type { FundamentalsProvider, ProviderFundamentals } from '../types';
import { fetchPsxFinancials, psxYearsToPeriods } from '../filings/psx';

/** Markets this provider can serve today. */
export const FILINGS_MARKETS = ['PK'] as const;

export const eclipseFilingsProvider: FundamentalsProvider = {
  id: 'eclipse-filings',
  label: 'Eclipse Filings (exchange)',

  // Keyless and always available — it reads public exchange pages.
  isConfigured: () => true,

  supports: (_symbol: string, market: string) =>
    (FILINGS_MARKETS as readonly string[]).includes(market.trim().toUpperCase()),

  async fetch(symbol: string, market: string): Promise<ProviderFundamentals | null> {
    const m = market.trim().toUpperCase();
    if (m === 'PK') {
      const years = await fetchPsxFinancials(symbol);
      if (years.length === 0) return null;
      return {
        provider: 'eclipse-filings',
        symbol: symbol.trim().toUpperCase(),
        currency: 'PKR',
        company: { exchange: 'PSX' },
        periods: psxYearsToPeriods(years),
        retrievedAt: new Date().toISOString(),
      };
    }
    return null;
  },
};
