// ── Investor Eye — country gazetteer ─────────────────────────────────────────
// Canonical country entities plus the aliases/signals used to resolve country
// mentions in unstructured text (GDELT titles, RSS headlines) and to anchor
// country-level events on the map.
//
// This is deliberately self-contained: it must work with zero configuration
// and no external geocoding API. The Natural Earth GeoJSON supplies geometry;
// this table supplies identity, region, centroid and market linkage.
//
// `mapName` matches the `properties.mapName` written by
// `scripts/fetch-world-geo.mjs` (Natural Earth ADMIN name) so a normalized
// event can be joined to the right map feature.

import type { NormalizedEvent } from './types';

export interface CountryDef {
  iso2: string;
  iso3: string;
  name: string;
  region: string;
  lon: number;
  lat: number;
  /** Existing JDDS market id, when this country has one. */
  marketId?: string;
  currency?: string;
  /** Natural Earth ADMIN name, when it differs from `name`. */
  mapName?: string;
  /** Extra name signals for text resolution (lower-case). */
  aliases?: string[];
}

// Region labels group countries for the UI and risk decomposition.
export const REGIONS = [
  'North America',
  'South America',
  'Europe',
  'Middle East',
  'Africa',
  'South Asia',
  'East Asia',
  'Southeast Asia',
  'Oceania',
  'Central Asia',
] as const;

export const COUNTRIES: CountryDef[] = [
  // ── North America ──────────────────────────────────────────────────────────
  { iso2: 'US', iso3: 'USA', name: 'United States', region: 'North America', lon: -98.5, lat: 39.8, marketId: 'US', currency: 'USD', mapName: 'United States of America', aliases: ['usa', 'u.s.', 'us', 'america', 'washington', 'united states of america'] },
  { iso2: 'CA', iso3: 'CAN', name: 'Canada', region: 'North America', lon: -106.3, lat: 56.1, marketId: 'CA', currency: 'CAD', aliases: ['ottawa', 'canadian'] },
  { iso2: 'MX', iso3: 'MEX', name: 'Mexico', region: 'North America', lon: -102.6, lat: 23.6, marketId: 'MX', currency: 'MXN', mapName: 'Mexico', aliases: ['mexican', 'mexico city'] },
  // ── South America ──────────────────────────────────────────────────────────
  { iso2: 'BR', iso3: 'BRA', name: 'Brazil', region: 'South America', lon: -51.9, lat: -14.2, marketId: 'BR', currency: 'BRL', aliases: ['brasil', 'brasilia', 'brazilian'] },
  { iso2: 'AR', iso3: 'ARG', name: 'Argentina', region: 'South America', lon: -63.6, lat: -38.4, currency: 'ARS', aliases: ['buenos aires', 'argentine'] },
  { iso2: 'CL', iso3: 'CHL', name: 'Chile', region: 'South America', lon: -71.5, lat: -35.7, currency: 'CLP', aliases: ['santiago'] },
  { iso2: 'CO', iso3: 'COL', name: 'Colombia', region: 'South America', lon: -74.3, lat: 4.6, currency: 'COP', aliases: ['bogota'] },
  { iso2: 'PE', iso3: 'PER', name: 'Peru', region: 'South America', lon: -75.0, lat: -9.2, currency: 'PEN', aliases: ['lima'] },
  { iso2: 'VE', iso3: 'VEN', name: 'Venezuela', region: 'South America', lon: -66.6, lat: 6.4, currency: 'VES', aliases: ['caracas'] },
  // ── Europe ─────────────────────────────────────────────────────────────────
  { iso2: 'GB', iso3: 'GBR', name: 'United Kingdom', region: 'Europe', lon: -3.4, lat: 55.4, marketId: 'UK', currency: 'GBP', mapName: 'United Kingdom', aliases: ['uk', 'u.k.', 'britain', 'england', 'london', 'british', 'scotland', 'wales'] },
  { iso2: 'DE', iso3: 'DEU', name: 'Germany', region: 'Europe', lon: 10.5, lat: 51.2, marketId: 'DE', currency: 'EUR', aliases: ['berlin', 'german', 'deutschland'] },
  { iso2: 'FR', iso3: 'FRA', name: 'France', region: 'Europe', lon: 2.2, lat: 46.2, marketId: 'FR', currency: 'EUR', aliases: ['paris', 'french'] },
  { iso2: 'IT', iso3: 'ITA', name: 'Italy', region: 'Europe', lon: 12.6, lat: 41.9, currency: 'EUR', aliases: ['rome', 'milan', 'italian'] },
  { iso2: 'ES', iso3: 'ESP', name: 'Spain', region: 'Europe', lon: -3.7, lat: 40.5, currency: 'EUR', aliases: ['madrid', 'spanish'] },
  { iso2: 'NL', iso3: 'NLD', name: 'Netherlands', region: 'Europe', lon: 5.3, lat: 52.1, marketId: 'NL', currency: 'EUR', aliases: ['amsterdam', 'dutch', 'holland'] },
  { iso2: 'BE', iso3: 'BEL', name: 'Belgium', region: 'Europe', lon: 4.5, lat: 50.5, currency: 'EUR', aliases: ['brussels'] },
  { iso2: 'CH', iso3: 'CHE', name: 'Switzerland', region: 'Europe', lon: 8.2, lat: 46.8, currency: 'CHF', aliases: ['zurich', 'geneva', 'swiss'] },
  { iso2: 'SE', iso3: 'SWE', name: 'Sweden', region: 'Europe', lon: 15.0, lat: 62.0, currency: 'SEK', aliases: ['stockholm'] },
  { iso2: 'NO', iso3: 'NOR', name: 'Norway', region: 'Europe', lon: 8.5, lat: 61.0, currency: 'NOK', aliases: ['oslo'] },
  { iso2: 'PL', iso3: 'POL', name: 'Poland', region: 'Europe', lon: 19.1, lat: 52.1, currency: 'PLN', aliases: ['warsaw'] },
  { iso2: 'UA', iso3: 'UKR', name: 'Ukraine', region: 'Europe', lon: 31.2, lat: 48.4, currency: 'UAH', aliases: ['kyiv', 'kiev', 'ukrainian'] },
  { iso2: 'RU', iso3: 'RUS', name: 'Russia', region: 'Europe', lon: 90.0, lat: 61.5, marketId: 'RU', currency: 'RUB', mapName: 'Russia', aliases: ['moscow', 'russian federation', 'russian', 'kremlin'] },
  { iso2: 'TR', iso3: 'TUR', name: 'Turkey', region: 'Europe', lon: 35.2, lat: 39.0, marketId: 'TR', currency: 'TRY', mapName: 'Turkey', aliases: ['turkiye', 'ankara', 'istanbul', 'turkish'] },
  { iso2: 'GR', iso3: 'GRC', name: 'Greece', region: 'Europe', lon: 22.0, lat: 39.0, currency: 'EUR', aliases: ['athens'] },
  { iso2: 'IE', iso3: 'IRL', name: 'Ireland', region: 'Europe', lon: -8.2, lat: 53.4, currency: 'EUR', aliases: ['dublin'] },
  { iso2: 'PT', iso3: 'PRT', name: 'Portugal', region: 'Europe', lon: -8.2, lat: 39.4, currency: 'EUR', aliases: ['lisbon'] },
  { iso2: 'CZ', iso3: 'CZE', name: 'Czechia', region: 'Europe', lon: 15.5, lat: 49.8, currency: 'CZK', aliases: ['czech republic', 'prague'] },
  { iso2: 'AT', iso3: 'AUT', name: 'Austria', region: 'Europe', lon: 14.6, lat: 47.5, currency: 'EUR', aliases: ['vienna'] },
  { iso2: 'HU', iso3: 'HUN', name: 'Hungary', region: 'Europe', lon: 19.5, lat: 47.2, currency: 'HUF', aliases: ['budapest'] },
  { iso2: 'RO', iso3: 'ROU', name: 'Romania', region: 'Europe', lon: 24.9, lat: 45.9, currency: 'RON', aliases: ['bucharest'] },
  { iso2: 'FI', iso3: 'FIN', name: 'Finland', region: 'Europe', lon: 25.7, lat: 61.9, currency: 'EUR', aliases: ['helsinki'] },
  { iso2: 'DK', iso3: 'DNK', name: 'Denmark', region: 'Europe', lon: 9.5, lat: 56.3, currency: 'DKK', aliases: ['copenhagen'] },
  // ── Middle East ────────────────────────────────────────────────────────────
  { iso2: 'SA', iso3: 'SAU', name: 'Saudi Arabia', region: 'Middle East', lon: 45.1, lat: 23.9, marketId: 'SA', currency: 'SAR', aliases: ['riyadh', 'saudi', 'ksa'] },
  { iso2: 'AE', iso3: 'ARE', name: 'United Arab Emirates', region: 'Middle East', lon: 53.8, lat: 23.4, marketId: 'AE', currency: 'AED', mapName: 'United Arab Emirates', aliases: ['uae', 'dubai', 'abu dhabi', 'emirates'] },
  { iso2: 'IL', iso3: 'ISR', name: 'Israel', region: 'Middle East', lon: 34.9, lat: 31.0, currency: 'ILS', aliases: ['jerusalem', 'tel aviv', 'israeli'] },
  { iso2: 'IR', iso3: 'IRN', name: 'Iran', region: 'Middle East', lon: 53.7, lat: 32.4, currency: 'IRR', aliases: ['tehran', 'iranian'] },
  { iso2: 'IQ', iso3: 'IRQ', name: 'Iraq', region: 'Middle East', lon: 43.7, lat: 33.2, currency: 'IQD', aliases: ['baghdad', 'iraqi'] },
  { iso2: 'QA', iso3: 'QAT', name: 'Qatar', region: 'Middle East', lon: 51.2, lat: 25.3, currency: 'QAR', aliases: ['doha'] },
  { iso2: 'KW', iso3: 'KWT', name: 'Kuwait', region: 'Middle East', lon: 47.5, lat: 29.3, currency: 'KWD' },
  { iso2: 'OM', iso3: 'OMN', name: 'Oman', region: 'Middle East', lon: 56.1, lat: 21.5, currency: 'OMR', aliases: ['muscat'] },
  { iso2: 'JO', iso3: 'JOR', name: 'Jordan', region: 'Middle East', lon: 36.2, lat: 31.3, currency: 'JOD', aliases: ['amman'] },
  { iso2: 'LB', iso3: 'LBN', name: 'Lebanon', region: 'Middle East', lon: 35.9, lat: 33.9, currency: 'LBP', aliases: ['beirut'] },
  { iso2: 'YE', iso3: 'YEM', name: 'Yemen', region: 'Middle East', lon: 47.6, lat: 15.6, currency: 'YER', aliases: ['sanaa', 'houthi', 'houthis', 'red sea'] },
  { iso2: 'SY', iso3: 'SYR', name: 'Syria', region: 'Middle East', lon: 39.0, lat: 34.8, currency: 'SYP', aliases: ['damascus', 'syrian'] },
  { iso2: 'EG', iso3: 'EGY', name: 'Egypt', region: 'Middle East', lon: 30.8, lat: 26.8, marketId: 'EG', currency: 'EGP', aliases: ['cairo', 'suez', 'egyptian'] },
  // ── Africa ─────────────────────────────────────────────────────────────────
  { iso2: 'ZA', iso3: 'ZAF', name: 'South Africa', region: 'Africa', lon: 22.9, lat: -30.6, marketId: 'ZA', currency: 'ZAR', aliases: ['johannesburg', 'cape town'] },
  { iso2: 'NG', iso3: 'NGA', name: 'Nigeria', region: 'Africa', lon: 8.7, lat: 9.1, marketId: 'NG', currency: 'NGN', aliases: ['lagos', 'abuja', 'nigerian'] },
  { iso2: 'KE', iso3: 'KEN', name: 'Kenya', region: 'Africa', lon: 38.0, lat: -0.02, currency: 'KES', aliases: ['nairobi'] },
  { iso2: 'GH', iso3: 'GHA', name: 'Ghana', region: 'Africa', lon: -1.0, lat: 7.9, currency: 'GHS', aliases: ['accra'] },
  { iso2: 'ET', iso3: 'ETH', name: 'Ethiopia', region: 'Africa', lon: 40.5, lat: 9.1, currency: 'ETB', aliases: ['addis ababa'] },
  { iso2: 'DZ', iso3: 'DZA', name: 'Algeria', region: 'Africa', lon: 1.7, lat: 28.0, currency: 'DZD', aliases: ['algiers'] },
  { iso2: 'LY', iso3: 'LBY', name: 'Libya', region: 'Africa', lon: 17.2, lat: 26.3, currency: 'LYD', aliases: ['tripoli'] },
  { iso2: 'MA', iso3: 'MAR', name: 'Morocco', region: 'Africa', lon: -7.1, lat: 31.8, currency: 'MAD', aliases: ['rabat', 'casablanca'] },
  { iso2: 'TZ', iso3: 'TZA', name: 'Tanzania', region: 'Africa', lon: 34.9, lat: -6.4, currency: 'TZS', aliases: ['dar es salaam'] },
  { iso2: 'CD', iso3: 'COD', name: 'DR Congo', region: 'Africa', lon: 21.8, lat: -4.0, currency: 'CDF', aliases: ['congo', 'kinshasa', 'democratic republic of the congo'] },
  { iso2: 'SD', iso3: 'SDN', name: 'Sudan', region: 'Africa', lon: 30.2, lat: 15.6, currency: 'SDG', aliases: ['khartoum'] },
  // ── South Asia ─────────────────────────────────────────────────────────────
  { iso2: 'PK', iso3: 'PAK', name: 'Pakistan', region: 'South Asia', lon: 69.3, lat: 30.4, marketId: 'PK', currency: 'PKR', aliases: ['karachi', 'islamabad', 'lahore', 'pakistani', 'psx'] },
  { iso2: 'IN', iso3: 'IND', name: 'India', region: 'South Asia', lon: 78.9, lat: 20.6, marketId: 'IN', currency: 'INR', aliases: ['delhi', 'new delhi', 'mumbai', 'indian', 'nifty', 'sensex'] },
  { iso2: 'BD', iso3: 'BGD', name: 'Bangladesh', region: 'South Asia', lon: 90.4, lat: 23.7, currency: 'BDT', aliases: ['dhaka'] },
  { iso2: 'LK', iso3: 'LKA', name: 'Sri Lanka', region: 'South Asia', lon: 80.8, lat: 7.9, currency: 'LKR', aliases: ['colombo'] },
  { iso2: 'AF', iso3: 'AFG', name: 'Afghanistan', region: 'South Asia', lon: 67.7, lat: 33.9, currency: 'AFN', aliases: ['kabul', 'afghan'] },
  { iso2: 'NP', iso3: 'NPL', name: 'Nepal', region: 'South Asia', lon: 84.1, lat: 28.4, currency: 'NPR', aliases: ['kathmandu'] },
  // ── East Asia ──────────────────────────────────────────────────────────────
  { iso2: 'CN', iso3: 'CHN', name: 'China', region: 'East Asia', lon: 104.2, lat: 35.9, marketId: 'CN', currency: 'CNY', mapName: 'China', aliases: ['beijing', 'shanghai', 'shenzhen', 'chinese', 'prc', 'mainland china'] },
  { iso2: 'JP', iso3: 'JPN', name: 'Japan', region: 'East Asia', lon: 138.3, lat: 36.2, marketId: 'JP', currency: 'JPY', aliases: ['tokyo', 'japanese', 'nikkei'] },
  { iso2: 'KR', iso3: 'KOR', name: 'South Korea', region: 'East Asia', lon: 127.8, lat: 35.9, marketId: 'KR', currency: 'KRW', mapName: 'South Korea', aliases: ['korea', 'seoul', 'korean', 'kospi'] },
  { iso2: 'KP', iso3: 'PRK', name: 'North Korea', region: 'East Asia', lon: 127.5, lat: 40.3, currency: 'KPW', mapName: 'North Korea', aliases: ['pyongyang', 'dprk'] },
  { iso2: 'TW', iso3: 'TWN', name: 'Taiwan', region: 'East Asia', lon: 120.96, lat: 23.7, marketId: 'TW', currency: 'TWD', mapName: 'Taiwan', aliases: ['taipei', 'taiwanese', 'tsmc'] },
  { iso2: 'HK', iso3: 'HKG', name: 'Hong Kong', region: 'East Asia', lon: 114.1, lat: 22.3, marketId: 'HK', currency: 'HKD', aliases: ['hongkong'] },
  { iso2: 'MN', iso3: 'MNG', name: 'Mongolia', region: 'East Asia', lon: 103.8, lat: 46.9, currency: 'MNT', aliases: ['ulaanbaatar'] },
  // ── Southeast Asia ─────────────────────────────────────────────────────────
  { iso2: 'SG', iso3: 'SGP', name: 'Singapore', region: 'Southeast Asia', lon: 103.8, lat: 1.35, marketId: 'SG', currency: 'SGD', aliases: ['singaporean'] },
  { iso2: 'MY', iso3: 'MYS', name: 'Malaysia', region: 'Southeast Asia', lon: 101.98, lat: 4.2, marketId: 'MY', currency: 'MYR', aliases: ['kuala lumpur'] },
  { iso2: 'ID', iso3: 'IDN', name: 'Indonesia', region: 'Southeast Asia', lon: 113.9, lat: -0.8, marketId: 'ID', currency: 'IDR', aliases: ['jakarta', 'indonesian'] },
  { iso2: 'TH', iso3: 'THA', name: 'Thailand', region: 'Southeast Asia', lon: 100.99, lat: 15.9, marketId: 'TH', currency: 'THB', aliases: ['bangkok', 'thai'] },
  { iso2: 'VN', iso3: 'VNM', name: 'Vietnam', region: 'Southeast Asia', lon: 108.3, lat: 14.1, marketId: 'VN', currency: 'VND', mapName: 'Vietnam', aliases: ['hanoi', 'vietnamese'] },
  { iso2: 'PH', iso3: 'PHL', name: 'Philippines', region: 'Southeast Asia', lon: 121.8, lat: 12.9, currency: 'PHP', aliases: ['manila'] },
  // ── Oceania ────────────────────────────────────────────────────────────────
  { iso2: 'AU', iso3: 'AUS', name: 'Australia', region: 'Oceania', lon: 133.8, lat: -25.3, marketId: 'AU', currency: 'AUD', aliases: ['sydney', 'melbourne', 'australian'] },
  { iso2: 'NZ', iso3: 'NZL', name: 'New Zealand', region: 'Oceania', lon: 174.9, lat: -40.9, currency: 'NZD', aliases: ['wellington', 'auckland'] },
  // ── Central Asia ───────────────────────────────────────────────────────────
  { iso2: 'KZ', iso3: 'KAZ', name: 'Kazakhstan', region: 'Central Asia', lon: 66.9, lat: 48.0, currency: 'KZT', aliases: ['astana', 'almaty'] },
  { iso2: 'UZ', iso3: 'UZB', name: 'Uzbekistan', region: 'Central Asia', lon: 64.6, lat: 41.4, currency: 'UZS', aliases: ['tashkent'] },
];

// ── Lookups ──────────────────────────────────────────────────────────────────

const BY_ISO2 = new Map<string, CountryDef>();
const BY_ISO3 = new Map<string, CountryDef>();
const BY_MAP_NAME = new Map<string, CountryDef>();
const BY_ALIAS = new Map<string, CountryDef>();

function normaliseKey(s: string): string {
  return s
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '') // strip accents
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

for (const c of COUNTRIES) {
  BY_ISO2.set(c.iso2.toUpperCase(), c);
  BY_ISO3.set(c.iso3.toUpperCase(), c);
  if (c.mapName) BY_MAP_NAME.set(normaliseKey(c.mapName), c);
  BY_ALIAS.set(normaliseKey(c.name), c);
  for (const a of c.aliases ?? []) {
    // First alias wins so a curated mapping is never overwritten by a later one.
    if (!BY_ALIAS.has(normaliseKey(a))) BY_ALIAS.set(normaliseKey(a), c);
  }
}

export function countryByIso2(iso2: string | null | undefined): CountryDef | undefined {
  if (!iso2) return undefined;
  return BY_ISO2.get(iso2.trim().toUpperCase());
}

export function countryByIso3(iso3: string | null | undefined): CountryDef | undefined {
  if (!iso3) return undefined;
  return BY_ISO3.get(iso3.trim().toUpperCase());
}

export function countryByMapName(mapName: string | null | undefined): CountryDef | undefined {
  if (!mapName) return undefined;
  return BY_MAP_NAME.get(normaliseKey(mapName));
}

/**
 * Resolve a free-text name/alias to a country. Exact (normalized) matches win;
 * a trailing containment pass catches "Pakistan's" / "U.S. officials".
 */
export function resolveCountry(text: string | null | undefined): CountryDef | undefined {
  if (!text) return undefined;
  const key = normaliseKey(text);
  if (!key) return undefined;
  const exact = BY_ALIAS.get(key);
  if (exact) return exact;
  // Containment: only accept reasonably long alias keys to avoid "us"/"in".
  for (const [alias, def] of BY_ALIAS) {
    if (alias.length < 4) continue;
    if (key === alias || key.startsWith(`${alias} `) || key.endsWith(` ${alias}`) || key.includes(` ${alias} `)) {
      return def;
    }
  }
  return undefined;
}

/**
 * Extract every country plausibly named in a text. Scans word-boundary aliases
 * (length ≥ 4 to avoid false positives) plus a special-case list of short but
 * high-signal aliases.
 */
// Short, high-signal aliases that containment matching would otherwise miss
// ("US", "U.K.", "UAE"). Keys are post-normalization forms.
const SHORT_SIGNALS = ['us', 'u s', 'uk', 'u k', 'uae'];
export function extractCountries(text: string | null | undefined): CountryDef[] {
  if (!text) return [];
  const haystack = ` ${normaliseKey(text)} `;
  const found = new Map<string, CountryDef>();
  for (const [alias, def] of BY_ALIAS) {
    if (alias.length >= 4 && haystack.includes(` ${alias} `)) {
      found.set(def.iso2, def);
    }
  }
  for (const s of SHORT_SIGNALS) {
    const def = BY_ALIAS.get(s);
    if (def && haystack.includes(` ${s} `)) found.set(def.iso2, def);
  }
  return [...found.values()];
}

/** Map a Natural Earth ADMIN/NAME string to a country (for click resolution). */
export function resolveMapFeatureName(name: string | null | undefined): CountryDef | undefined {
  return countryByMapName(name) ?? resolveCountry(name);
}

/**
 * Approximate the country nearest a coordinate using gazetteer centroids.
 * Deliberately crude (nearest centroid) — it is only used to tag point events
 * (e.g. earthquakes) with a country for filtering, never to claim a border.
 * Returns undefined when the point is implausibly far from any centroid.
 */
export function nearestCountry(lon: number, lat: number): CountryDef | undefined {
  let best: CountryDef | undefined;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const c of COUNTRIES) {
    const dx = (c.lon - lon) * Math.cos((((c.lat + lat) / 2) * Math.PI) / 180);
    const dy = c.lat - lat;
    const d = dx * dx + dy * dy;
    if (d < bestDistance) {
      bestDistance = d;
      best = c;
    }
  }
  // ~30 degrees of arc is already very generous; beyond that the point is at
  // sea or in a region this gazetteer does not represent.
  return bestDistance <= 30 * 30 ? best : undefined;
}

/** Build a default `NormalizedEvent` country reference list. */
export function countryRefs(event: Pick<NormalizedEvent, 'countries'>): CountryDef[] {
  return event.countries
    .map((iso2) => countryByIso2(iso2))
    .filter((c): c is CountryDef => Boolean(c));
}
