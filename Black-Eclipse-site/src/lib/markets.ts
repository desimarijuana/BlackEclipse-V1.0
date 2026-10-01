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

// Exchange / venue / regulator codes → canonical JDDS market id. A caller
// frequently qualifies an instrument by its VENUE ("PSX", "LSE", "NYSE") rather
// than by JDDS's country-based market id ("PK", "UK", "US"). Without this map
// such a qualifier was silently discarded and a bare ticker fetched — which is
// how a US fund's price came back under a Pakistan ticker.
//
// Multi-venue markets list every venue they host. This is deliberately broad:
// resolving a venue the system does not recognise must FAIL LOUDLY, never fall
// back to a bare US ticker.
export const MARKET_EXCHANGE_ALIASES: Record<string, string> = {
  // United States
  NYSE: "US", NASDAQ: "US", AMEX: "US", ARCA: "US", BATS: "US", NYSEARCA: "US",
  "NYSE AMERICAN": "US", OTC: "US", OTCQB: "US", OTCQX: "US", MIAX: "US",
  // Pakistan
  PSX: "PK", KSE: "PK", "PSX/KSE": "PK", LSEPK: "PK",
  // India
  NSE: "IN", BSE: "IN", "NSE/BSE": "IN", NSEI: "IN", BSESN: "IN",
  // China
  SSE: "CN", SZSE: "CN", "SSE/SZSE": "CN", SHSE: "CN", SHSZ: "CN",
  // Hong Kong
  HKEX: "HK", SEHK: "HK", HKSE: "HK",
  // Japan
  TSE: "JP", TYO: "JP", JPX: "JP", OSE: "JP", "TOKYO STOCK EXCHANGE": "JP",
  // Taiwan
  TWSE: "TW", TPEX: "TW", OTC_TW: "TW",
  // Korea
  KRX: "KR", KSEKR: "KR", KOSPI: "KR", KOSDAQ: "KR",
  // Singapore
  SGX: "SG",
  // Malaysia
  KLSE: "MY", BURSA: "MY", "BURSA MALAYSIA": "MY",
  // Australia
  ASX: "AU", AX: "AU",
  // United Kingdom
  LSE: "UK", LON: "UK", LSEG: "UK", AIM: "UK",
  // Germany
  XETRA: "DE", FRA: "DE", FWB: "DE", ETR: "DE", XETR: "DE", "FRANKFURT": "DE",
  // France
  EPA: "FR", ENXTPA: "FR", "EURONEXT PARIS": "FR", PAR: "FR",
  // Netherlands
  AMS: "NL", "EURONEXT AMSTERDAM": "NL",
  // Canada
  TSX: "CA", TSXV: "CA", CVE: "CA", NEO: "CA", TSE_CA: "CA",
  // Brazil
  B3: "BR", BVMF: "BR",
  // Mexico
  BMV: "MX",
  // Saudi Arabia
  TADAWUL: "SA", SAU: "SA",
  // UAE
  ADX: "AE", DFM: "AE", "ADX/DFM": "AE",
  // South Africa
  JSE: "ZA",
  // Egypt
  EGX: "EG",
  // Nigeria
  NGX: "NG", NSE_NG: "NG",
  // Russia
  MOEX: "RU", MCX: "RU",
  // Turkey
  BIST: "TR", ISE: "TR",
  // Indonesia
  IDX: "ID", JKSE: "ID",
  // Thailand
  SET: "TH", BKK: "TH",
  // Vietnam
  HOSE: "VN", HNX: "VN",
  // Crypto (venue-agnostic; the pseudo-market is its own id)
  BINANCE: "CRYPTO", COINBASE: "CRYPTO", KRAKEN: "CRYPTO", CRYPTO: "CRYPTO",
  // ── Derivatives venues ─────────────────────────────────────────────────────
  // Futures/options exchanges. They are recognised so an `ES`/`CME` request is
  // NOT_COVERED (no precise price source) rather than "unknown venue" — the
  // caller named a real venue, we just do not cover it. Maps to a DERIV pseudo-
  // market so the coverage registry can answer honestly.
  CME: "DERIV", CBOT: "DERIV", NYMEX: "DERIV", COMEX: "DERIV",
  ICE: "DERIV", CBOE: "DERIV", EUREX: "DERIV", "CME GROUP": "DERIV",
  NASDAQ_OMX: "DERIV", HKFE: "DERIV", SGX_DT: "DERIV", TSE_DERIV: "DERIV",
  MONEP: "DERIV", LIFFE: "DERIV",
};

// Exchange SUFFIX → canonical market id. This is the global convention used by
// Yahoo/most aggregators (`.TW` = Taiwan, `.L` = London, `.KS` = Korea KOSPI…).
// It exists because the JDdS instrument master stores instruments under their
// BARE local code (`2330`, `005930`, `PETR4`) while a user very often types the
// suffixed form (`2330.TW`, `005930.KS`, `PETR4.SA`). Before this, the suffixed
// string was looked up verbatim, never matched, and returned `not_found` — so a
// Taiwan/Korea/Brazil instrument was "not in the universe" even though it was.
//
// Only explicit, well-known suffixes are mapped. A suffix we do not recognise is
// NOT guessed: the bare ticker then goes through normal resolution (which fails
// loudly on ambiguity). Keys are lower-case to match the alias index.
export const EXCHANGE_SUFFIX_ALIASES: Record<string, string> = {
  // Americas
  ".us": "US",
  ".to": "CA", ".v": "CA", ".cn": "CA", ".ne": "CA",
  ".sa": "BR", ".mx": "MX",
  // Asia-Pacific
  ".tw": "TW", ".two": "TW",
  ".ks": "KR", ".kq": "KR",
  ".t": "JP", ".jp": "JP",
  ".hk": "HK",
  ".ss": "CN", ".sz": "CN",
  ".in": "IN", ".ns": "IN", ".bo": "IN",
  ".si": "SG", ".kl": "MY",
  ".ax": "AU", ".nz": "AU",
  ".bk": "TH", ".jk": "ID", ".vn": "VN",
  // EMEA
  ".l": "UK", ".lse": "UK",
  ".de": "DE", ".f": "DE", ".etr": "DE",
  ".pa": "FR", ".as": "NL",
  ".sa_ae": "AE", ".sr": "SA", ".jo": "ZA",
  ".is": "TR",
  ".eg": "EG", ".ng": "NG", ".me": "RU",
};

/**
 * Split a well-known exchange suffix off a ticker. Returns the bare symbol and
 * the canonical market implied by the suffix, or `{ symbol: raw }` unchanged when
 * there is no recognised suffix. Never guesses: an unknown suffix is left intact.
 */
export function splitExchangeSuffix(raw: string): { symbol: string; market: string | null } {
  const trimmed = (raw ?? "").trim();
  if (!trimmed) return { symbol: trimmed, market: null };
  const dot = trimmed.lastIndexOf(".");
  if (dot <= 0 || dot === trimmed.length - 1) return { symbol: trimmed, market: null };
  const suffix = trimmed.slice(dot).toLowerCase();
  const market = EXCHANGE_SUFFIX_ALIASES[suffix];
  if (!market) return { symbol: trimmed, market: null };
  return { symbol: trimmed.slice(0, dot), market };
}

// Index of every known market id (the canonical vocabulary). Kept in sync with
// MARKET_CURRENCY — a market is "known" iff it has a currency. Built lazily so
// declaration order in this module is not significant.
let _marketAliasIndex: Record<string, string> | null = null;

function marketAliasIndex(): Record<string, string> {
  if (_marketAliasIndex) return _marketAliasIndex;
  const map: Record<string, string> = {};
  for (const [id, name] of Object.entries(MARKET_FULL_NAME)) map[name.toLowerCase()] = id;
  for (const [key, id] of Object.entries(MARKET_ID_MAP)) map[key.toLowerCase()] = id;
  for (const [key, id] of Object.entries(MARKET_EXCHANGE_ALIASES)) map[key.toLowerCase()] = id;
  // Explicit global exchange suffixes (`.tw` → TW). Kept distinct from the bare
  // venue aliases so `L` is not London while `.L` unambiguously is.
  for (const [key, id] of Object.entries(EXCHANGE_SUFFIX_ALIASES)) map[key.toLowerCase()] = id;
  // A market id always resolves to itself, lower-cased key.
  for (const id of Object.keys(MARKET_CURRENCY)) map[id.toLowerCase()] = id;
  _marketAliasIndex = map;
  return map;
}

/**
 * Resolve a market qualifier — market id ("PK"), country/display name
 * ("Pakistan"), or exchange/venue code ("PSX") — to a canonical JDDS market id.
 *
 * Returns `null` when the qualifier is unrecognised. Callers MUST treat `null`
 * as a hard failure: an unhonoured market qualifier is never dropped in favour
 * of a bare-ticker lookup. (Contrast `toMarketId`, which preserves legacy
 * behaviour and passes unknown values through — do not use it for identity.)
 */
export function resolveMarketId(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const key = raw.trim().toLowerCase();
  if (!key) return null;
  return marketAliasIndex()[key] ?? null;
}

/** True when `raw` names a market this system can honor. */
export function isKnownMarket(raw: string | null | undefined): boolean {
  return resolveMarketId(raw) !== null;
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

// Canonical ISO 4217 currency code per market. `MARKET_CURRENCY` holds DISPLAY
// symbols ("$"), which are not an identity — instrument identity requires the
// ISO code so a US $ and a CAD $ can never be confused. Kept in sync with
// MARKET_CURRENCY (same key set).
export const MARKET_CURRENCY_ISO: Record<string, string> = {
  US: "USD", CRYPTO: "USD", PK: "PKR", IN: "INR", CN: "CNY", TW: "TWD", HK: "HKD",
  JP: "JPY", KR: "KRW", SG: "SGD", MY: "MYR", AU: "AUD", UK: "GBP", DE: "EUR",
  FR: "EUR", NL: "EUR", CA: "CAD", BR: "BRL", MX: "MXN", SA: "SAR", AE: "AED",
  ZA: "ZAR", EG: "EGP", NG: "NGN", RU: "RUB", TR: "TRY", ID: "IDR", TH: "THB",
  VN: "VND",
  // Venues covered by the TradingView scan but historically absent from the ISO
  // table, so the matrix fell back to USD and mis-stated their currency. CH is
  // CHF (NOT USD). KW/QAR are the Gulf venues. (Harness closeout Phase 3.2.)
  CH: "CHF", KW: "KWD", QA: "QAR",
  // FX quotes are denominated in their quote currency, carried on the identity;
  // this is only the registry default. DERIV is uncovered and has no currency.
  FX: "USD", DERIV: "N/A",
};

/** ISO 4217 currency code for a market id (defaults to USD). */
export function currencyIsoFor(marketId: string): string {
  return MARKET_CURRENCY_ISO[marketId] || "USD";
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
  CH: "Switzerland",
  KW: "Kuwait",
  QA: "Qatar",
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
