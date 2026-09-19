// Market constants — SINGLE SOURCE OF TRUTH.
//
// These maps were previously duplicated across /api/stocks, /api/refresh,
// /api/indices and two fetcher modules, and had already drifted (the refresh
// route knew about more markets than the screener). Import from here only.

/** UI country code → JDDS market id. Accepts aliases like USA/CN/China. */
export const MARKET_ID_MAP: Record<string, string> = {
  US: "US",
  USA: "US",
  PK: "PK",
  IN: "IN",
  CRYPTO: "CRYPTO",
  China: "CN",
  CN: "CN",
  Taiwan: "TW",
  TW: "TW",
  HK: "HK",
  JP: "JP",
  KR: "KR",
  SG: "SG",
  MY: "MY",
  AU: "AU",
  UK: "UK",
  DE: "DE",
  FR: "FR",
  NL: "NL",
  CA: "CA",
  BR: "BR",
  MX: "MX",
  SA: "SA",
  AE: "AE",
  ZA: "ZA",
  EG: "EG",
  NG: "NG",
  RU: "RU",
  TR: "TR",
  ID: "ID",
  TH: "TH",
  VN: "VN",
};

/** Normalize any user/UI market code into its canonical JDDS market id. */
export function toMarketId(raw: string | null | undefined): string {
  if (!raw) return "US";
  const key = raw.trim();
  return MARKET_ID_MAP[key] || key;
}

// Currency that belongs to each market's instruments. US + crypto are
// dollar-denominated; every other market quotes in its native currency.
// Shared by /api/indices, /api/quote, and client-side display helpers.
export const MARKET_CURRENCY: Record<string, string> = {
  US: "$", CRYPTO: "$", PK: "PKR", IN: "INR", CN: "CNY", TW: "TWD", HK: "HKD",
  JP: "JPY", KR: "KRW", SG: "SGD", MY: "MYR", AU: "AUD", UK: "GBP", DE: "EUR",
  FR: "EUR", NL: "EUR", CA: "CAD", BR: "BRL", MX: "MXN", SA: "SAR", AE: "AED",
  ZA: "ZAR", EG: "EGP", NG: "NGN", RU: "RUB", TR: "TRY", ID: "IDR", TH: "THB",
  VN: "VND",
};

/** Display currency symbol for a market id (defaults to USD "$"). */
export function currencyFor(marketId: string): string {
  return MARKET_CURRENCY[marketId] || "$";
}

// Full, human-readable country/market names keyed by market id. Used across the
// screener cards and global search so users see "Pakistan" / "United States"
// instead of bare codes. SINGLE SOURCE OF TRUTH — import from here only.
export const MARKET_FULL_NAME: Record<string, string> = {
  US: "United States",
  CRYPTO: "Global Crypto",
  PK: "Pakistan",
  IN: "India",
  CN: "China",
  TW: "Taiwan",
  HK: "Hong Kong",
  JP: "Japan",
  KR: "South Korea",
  SG: "Singapore",
  MY: "Malaysia",
  AU: "Australia",
  UK: "United Kingdom",
  DE: "Germany",
  FR: "France",
  NL: "Netherlands",
  CA: "Canada",
  BR: "Brazil",
  MX: "Mexico",
  SA: "Saudi Arabia",
  AE: "United Arab Emirates",
  ZA: "South Africa",
  EG: "Egypt",
  NG: "Nigeria",
  RU: "Russia",
  TR: "Turkey",
  ID: "Indonesia",
  TH: "Thailand",
  VN: "Vietnam",
  FOREX: "Forex",
  COMMODITIES: "Commodities",
};

/** Human-readable country/market name for a market id (falls back to the code). */
export function marketDisplayName(marketId: string): string {
  return MARKET_FULL_NAME[marketId] || marketId;
}

// Reverse index: full country name / display name / id → canonical market id.
// JDDS `Asset.country` is inconsistent (both "US" and "United States" appear),
// so any country-bearing surface (fundamentals, asset details) must normalize
// through here rather than string-matching on its own.
const COUNTRY_TO_MARKET_ID: Record<string, string> = (() => {
  const map: Record<string, string> = {};
  for (const [id, name] of Object.entries(MARKET_FULL_NAME)) {
    map[name.toLowerCase()] = id;
  }
  for (const key of Object.keys(MARKET_ID_MAP)) {
    map[key.toLowerCase()] = MARKET_ID_MAP[key];
  }
  return map;
})();

/**
 * Resolve a country name, display name, or market code to a canonical market id
 * ("United States" → "US", "Pakistan" → "PK"). Unknown values pass through
 * upper-cased so a caller never silently falls back to the wrong market.
 */
export function countryToMarketId(raw: string | null | undefined): string {
  if (!raw) return "US";
  const key = raw.trim().toLowerCase();
  return COUNTRY_TO_MARKET_ID[key] || raw.trim().toUpperCase();
}
