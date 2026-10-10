// ── Official-filings adapter registry (multi-market framework) ───────────────
// Adding a market = one adapter with a `fetch` and its market codes. The
// `eclipse-filings` provider dispatches through this registry, so a new exchange
// never touches the provider or the UI. Adapters return ALREADY-NORMALIZED
// Eclipse periods (never a vendor shape) and MUST return null when the source
// has nothing — they never invent data.

import type { CompanyProfile, FundamentalPeriod } from '../types';
import { fetchPsxFinancials, psxYearsToPeriods } from './psx';

export interface FilingsResult {
  currency: string | null;
  periods: FundamentalPeriod[];
  company?: Partial<CompanyProfile>;
  /** Human source label for provenance (e.g. "PSX"). */
  source: string;
}

export interface FilingsAdapter {
  id: string;
  /** Upper-case market ids this adapter serves. */
  markets: string[];
  fetch(symbol: string): Promise<FilingsResult | null>;
}

const psxAdapter: FilingsAdapter = {
  id: 'psx',
  markets: ['PK'],
  async fetch(symbol: string): Promise<FilingsResult | null> {
    const years = await fetchPsxFinancials(symbol);
    if (years.length === 0) return null;
    return {
      currency: 'PKR',
      periods: psxYearsToPeriods(years),
      company: { exchange: 'PSX' },
      source: 'PSX',
    };
  },
};

/** All registered official-filings adapters. Add new markets here. */
export const FILINGS_ADAPTERS: FilingsAdapter[] = [psxAdapter];

/** The adapter serving a market, or undefined when none is implemented yet. */
export function adapterFor(market: string): FilingsAdapter | undefined {
  const m = market.trim().toUpperCase();
  return FILINGS_ADAPTERS.find((a) => a.markets.includes(m));
}
