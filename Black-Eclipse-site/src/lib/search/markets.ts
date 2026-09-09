// ── Markets/countries as searchable entities ────────────────────────────────
// Lets the global search find "Pakistan", "United States", "India" etc. and
// open the screener for that market. Reads from the canonical market constants.

import type { SearchEntity } from './types';
import { MARKET_FULL_NAME } from '@/lib/markets';

// Codes that map to a screener country (excludes special pseudo-markets that
// already have their own pages/tabs).
const SCREENABLE: string[] = [
  'US', 'PK', 'IN', 'CN', 'TW', 'HK', 'JP', 'KR', 'SG', 'MY', 'AU', 'UK', 'DE',
  'FR', 'NL', 'CA', 'BR', 'MX', 'SA', 'AE', 'ZA', 'EG', 'NG', 'RU', 'TR', 'ID',
  'TH', 'VN',
];

export function marketEntities(): SearchEntity[] {
  return SCREENABLE.map((code) => ({
    id: `market-${code}`,
    kind: 'page',
    title: MARKET_FULL_NAME[code] ?? code,
    keywords: ['market', 'screener', 'country', code.toLowerCase()],
    icon: 'globe',
    destination: { tab: 'discovery', params: { market: code } },
    subtitle: `${code} · Market Screener`,
  }));
}
