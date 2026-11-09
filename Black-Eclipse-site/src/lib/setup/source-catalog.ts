// ── Setup source catalog ────────────────────────────────────────────────────
// The ONE data-only registry the onboarding UI, the API validator and the
// fetcher-enforcement layer agree on. Adding a source here is how it becomes
// visible to setup; it does not enable it anywhere by itself.
//
// Honesty rules:
//   - `tier` says who supplies the data: open (included), the user's own
//     account (connected), or a community/scraper source that is off by default.
//   - `commercial` is an informational snapshot of the provider's terms, not a
//     legal opinion. Every non-open entry links upstream.
//   - `defaultOn` is true ONLY for open data that may be redistributed with the
//     stated condition. Nothing in the connected/advanced tiers defaults on.

import type { CommercialStatus, SourceDef, SourceId, SourceTier } from "./types";

export const SOURCES: SourceDef[] = [
  // ── Included: open data, no account ───────────────────────────────────────
  {
    id: "sec",
    label: "SEC EDGAR",
    short: "Company filings",
    tier: "included",
    category: "filings",
    powers: ["Company research", "Filings", "Fundamentals"],
    commercial: "ok",
    note: "US government public domain. Respect the fair-access rate limit.",
    termsUrl: "https://www.sec.gov/os/webmaster-faq",
    defaultOn: true,
  },
  {
    id: "fred",
    label: "FRED public series",
    short: "US macro series",
    tier: "included",
    category: "macro",
    powers: ["US macro", "Rates & inflation"],
    commercial: "attribution",
    note: "Public CSV mirror (no key). The optional keyed FRED API raises limits. Some series carry third-party copyright.",
    termsUrl: "https://fred.stlouisfed.org/legal/",
    attribution: "Courtesy of FRED, Federal Reserve Bank of St. Louis",
    defaultOn: true,
  },
  {
    id: "bea",
    label: "BEA",
    short: "US national accounts",
    tier: "included",
    category: "macro",
    powers: ["GDP", "National accounts"],
    commercial: "ok",
    note: "US government public data.",
    termsUrl: "https://www.bea.gov/help/faq/",
    defaultOn: true,
  },
  {
    id: "bls",
    label: "BLS",
    short: "US employment & inflation",
    tier: "included",
    category: "macro",
    powers: ["Employment", "CPI"],
    commercial: "ok",
    note: "US government public data.",
    termsUrl: "https://www.bls.gov/developers/",
    defaultOn: true,
  },
  {
    id: "worldbank",
    label: "World Bank",
    short: "Global macro",
    tier: "included",
    category: "macro",
    powers: ["Global macro", "Development indicators"],
    commercial: "attribution",
    note: "CC BY 4.0 attribution.",
    termsUrl: "https://datacatalog.worldbank.org/public-licenses",
    attribution: "World Bank Open Data (CC BY 4.0)",
    defaultOn: true,
  },
  {
    id: "eurostat",
    label: "Eurostat / ECB",
    short: "EU macro & FX",
    tier: "included",
    category: "macro",
    powers: ["EU macro", "Reference FX rates"],
    commercial: "attribution",
    note: "Free reuse with attribution.",
    termsUrl: "https://ec.europa.eu/eurostat/about-us/policies/copyright",
    attribution: "Eurostat / European Central Bank",
    defaultOn: true,
  },
  {
    id: "gdelt",
    label: "GDELT",
    short: "World events",
    tier: "included",
    category: "events",
    powers: ["Geopolitical events", "Investor Eye"],
    commercial: "attribution",
    note: "Open event data; attribution.",
    termsUrl: "https://www.gdeltproject.org/about.html",
    attribution: "The GDELT Project",
    defaultOn: true,
  },
  {
    id: "usgs",
    label: "USGS",
    short: "Earthquakes",
    tier: "included",
    category: "events",
    powers: ["Seismic events", "Investor Eye"],
    commercial: "ok",
    note: "US government public domain.",
    termsUrl: "https://www.usgs.gov/information-policies",
    defaultOn: true,
  },
  {
    id: "firms",
    label: "NASA FIRMS",
    short: "Fire & thermal events",
    tier: "included",
    category: "events",
    powers: ["Fire detections", "Investor Eye"],
    commercial: "verify",
    note: "Free with attribution; verify current commercial terms before a paid launch.",
    termsUrl: "https://firms.modaps.eosdis.nasa.gov/",
    attribution: "NASA FIRMS",
    defaultOn: true,
  },
  {
    id: "news-rss",
    label: "Official news feeds",
    short: "Central banks, regulators, wires",
    tier: "included",
    category: "news",
    powers: ["Headlines", "Regulatory news"],
    commercial: "verify",
    note: "Publisher RSS terms vary. Keep the publisher attribution visible.",
    termsUrl: "https://www.sec.gov/news/pressreleases.rss",
    defaultOn: true,
  },

  // ── Connected: user's own market / fundamentals accounts ──────────────────
  {
    id: "polygon",
    label: "Polygon.io",
    short: "US equities & aggregates",
    tier: "connected",
    category: "market",
    powers: ["Live prices", "Charts", "Screener"],
    commercial: "ok",
    note: "Commercial use requires a paid plan.",
    termsUrl: "https://polygon.io/legal/terms",
    envVar: "POLYGON_API_KEY",
    defaultOn: false,
  },
  {
    id: "twelvedata",
    label: "Twelve Data",
    short: "Global equities, FX & crypto",
    tier: "connected",
    category: "market",
    powers: ["Live prices", "Charts"],
    commercial: "ok",
    note: "Commercial use requires a paid plan.",
    termsUrl: "https://twelvedata.com/terms",
    envVar: "TWELVE_DATA_API_KEY",
    defaultOn: false,
  },
  {
    id: "finnhub",
    label: "Finnhub",
    short: "Quotes, news & fundamentals",
    tier: "connected",
    category: "market",
    powers: ["News", "Earnings", "Quotes"],
    commercial: "ok",
    note: "Free tier is personal; commercial needs a paid plan.",
    termsUrl: "https://finnhub.io/terms-of-service",
    envVar: "FINNHUB_API_KEY",
    defaultOn: false,
  },
  {
    id: "alphavantage",
    label: "Alpha Vantage",
    short: "Quotes, FX & technicals",
    tier: "connected",
    category: "market",
    powers: ["Live prices", "FX", "Technicals"],
    commercial: "ok",
    note: "Premium tier for commercial use.",
    termsUrl: "https://www.alphavantage.co/terms_of_service/",
    envVar: "ALPHAVANTAGE_API_KEY",
    defaultOn: false,
  },
  {
    id: "marketstack",
    label: "Marketstack",
    short: "EOD & intraday prices",
    tier: "connected",
    category: "market",
    powers: ["Live prices", "History"],
    commercial: "ok",
    note: "Paid plans for commercial use.",
    termsUrl: "https://marketstack.com/terms",
    envVar: "MARKETSTACK_API_KEY",
    defaultOn: false,
  },
  {
    id: "fmp",
    label: "Financial Modeling Prep",
    short: "Fundamentals & estimates",
    tier: "connected",
    category: "filings",
    powers: ["Fundamentals", "Ratios", "Estimates"],
    commercial: "ok",
    note: "Paid plans for commercial use.",
    termsUrl: "https://site.financialmodelingprep.com/terms-of-service",
    envVar: "FINANCIALMODELINGPREP_API_KEY",
    defaultOn: false,
  },
  {
    id: "coinmarketcap",
    label: "CoinMarketCap",
    short: "Crypto rankings & quotes",
    tier: "connected",
    category: "crypto",
    powers: ["Crypto prices", "Rankings"],
    commercial: "verify",
    note: "Basic tier advertises commercial rights; verify the current plan terms.",
    termsUrl: "https://coinmarketcap.com/api/terms/",
    envVar: "COINMARKETCAP_API_KEY",
    defaultOn: false,
  },
  {
    id: "coingecko-paid",
    label: "CoinGecko (paid)",
    short: "Crypto data",
    tier: "connected",
    category: "crypto",
    powers: ["Crypto prices", "Market data"],
    commercial: "attribution",
    note: "Commercial use requires a paid plan and attribution.",
    termsUrl: "https://www.coingecko.com/en/api_terms",
    envVar: "COINGECKO_API_KEY",
    attribution: "Data provided by CoinGecko",
    defaultOn: false,
  },
  {
    id: "tradingeconomics",
    label: "Trading Economics",
    short: "Global macro & calendars",
    tier: "connected",
    category: "macro",
    powers: ["Global macro", "Economic calendar"],
    commercial: "ok",
    note: "Commercial access is a paid plan.",
    termsUrl: "https://tradingeconomics.com/api/terms-and-conditions.aspx",
    envVar: "TRADING_ECONOMICS_API_KEY",
    defaultOn: false,
  },
  {
    id: "tavily",
    label: "Tavily",
    short: "Research web search",
    tier: "connected",
    category: "research",
    powers: ["Research search"],
    commercial: "ok",
    note: "Commercial use requires the appropriate plan.",
    termsUrl: "https://tavily.com/terms",
    envVar: "TAVILY_API_KEY",
    defaultOn: false,
  },
  {
    id: "brave",
    label: "Brave Search",
    short: "Independent web index",
    tier: "connected",
    category: "research",
    powers: ["Research search"],
    commercial: "ok",
    note: "Check the plan's commercial terms.",
    termsUrl: "https://brave.com/search/api/",
    envVar: "BRAVE_API_KEY",
    defaultOn: false,
  },
  {
    id: "exa",
    label: "Exa",
    short: "Semantic web search",
    tier: "connected",
    category: "research",
    powers: ["Research search"],
    commercial: "ok",
    note: "Paid plans for commercial use.",
    termsUrl: "https://exa.ai/terms",
    envVar: "EXA_API_KEY",
    defaultOn: false,
  },
  {
    id: "serper",
    label: "Serper",
    short: "Google-shaped search",
    tier: "connected",
    category: "research",
    powers: ["Research search"],
    commercial: "ok",
    note: "Check the plan's commercial terms.",
    termsUrl: "https://serper.dev/terms",
    envVar: "SERPER_API_KEY",
    defaultOn: false,
  },

  // ── Advanced: community sources, off unless explicitly accepted ───────────
  {
    id: "tradingview",
    label: "TradingView scanner",
    short: "Whole-market scans",
    tier: "advanced",
    category: "market",
    powers: ["Live prices", "Screener"],
    commercial: "personal-only",
    note: "No public data API; scraping/redistribution is restricted.",
    termsUrl: "https://www.tradingview.com/policies",
    defaultOn: false,
  },
  {
    id: "yfinance",
    label: "Yahoo Finance (yfinance)",
    short: "US quotes & history",
    tier: "advanced",
    category: "market",
    powers: ["Live prices", "History"],
    commercial: "personal-only",
    note: "Commercial use needs Yahoo's written permission.",
    termsUrl: "https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html",
    defaultOn: false,
  },
  {
    id: "http",
    label: "HTTP scraper",
    short: "Static page fallback",
    tier: "advanced",
    category: "market",
    powers: ["Live prices"],
    commercial: "verify",
    note: "Each target site's terms govern the fetch.",
    defaultOn: false,
  },
  {
    id: "browser",
    label: "Browser scraper",
    short: "Playwright escalation",
    tier: "advanced",
    category: "market",
    powers: ["Live prices"],
    commercial: "verify",
    note: "Each target site's terms govern the fetch.",
    defaultOn: false,
  },
  {
    id: "scrapling",
    label: "Scrapling",
    short: "Anti-bot fallback",
    tier: "advanced",
    category: "market",
    powers: ["Live prices"],
    commercial: "verify",
    note: "Each target site's terms govern the fetch.",
    defaultOn: false,
  },
  {
    id: "binance",
    label: "Binance public ticker",
    short: "Crypto prices",
    tier: "advanced",
    category: "crypto",
    powers: ["Crypto prices"],
    commercial: "personal-only",
    note: "Commercial redistribution needs Binance's written consent.",
    termsUrl: "https://www.binance.com/en/terms",
    defaultOn: false,
  },
  {
    id: "kraken",
    label: "Kraken public API",
    short: "Crypto prices",
    tier: "advanced",
    category: "crypto",
    powers: ["Crypto prices"],
    commercial: "verify",
    note: "Verify Kraken's current market-data terms.",
    termsUrl: "https://www.kraken.com/legal",
    defaultOn: false,
  },
  {
    id: "coingecko",
    label: "CoinGecko Demo / keyless",
    short: "Crypto prices",
    tier: "advanced",
    category: "crypto",
    powers: ["Crypto prices"],
    commercial: "personal-only",
    note: "Attribution required; the Demo tier is not a commercial license.",
    termsUrl: "https://www.coingecko.com/en/api_terms",
    attribution: "Data provided by CoinGecko",
    defaultOn: false,
  },
  {
    id: "duckduckgo",
    label: "DuckDuckGo HTML search",
    short: "Keyless research fallback",
    tier: "advanced",
    category: "research",
    powers: ["Research search"],
    commercial: "personal-only",
    note: "Not for commercial redistribution; use a search API key instead.",
    termsUrl: "https://duckduckgo.com/terms",
    defaultOn: false,
  },
];

export const SOURCE_BY_ID: Record<string, SourceDef> = Object.fromEntries(
  SOURCES.map((s) => [s.id, s]),
);

export function sourceById(id: string): SourceDef | undefined {
  return SOURCE_BY_ID[id];
}

export function sourcesByTier(tier: SourceTier): SourceDef[] {
  return SOURCES.filter((s) => s.tier === tier);
}

export function isSourceId(value: unknown): value is SourceId {
  return typeof value === "string" && value in SOURCE_BY_ID;
}

/** Sources whose terms fit a paid/commercial product, in badge terms. */
export const COMMERCIAL_OK: CommercialStatus[] = ["ok", "attribution"];

/** Human label for a commercial badge. */
export function commercialLabel(status: CommercialStatus): string {
  switch (status) {
    case "ok":
      return "COMMERCIAL USE OK";
    case "attribution":
      return "COMMERCIAL + ATTRIBUTION";
    case "personal-only":
      return "PERSONAL USE ONLY";
    case "verify":
      return "CHECK TERMS";
  }
}

/**
 * The straight answer a user actually needs, in one sentence. This is what the
 * setup UI shows under every source; the badge is only a reminder.
 */
export function commercialSentence(status: CommercialStatus): string {
  switch (status) {
    case "ok":
      return "You can use this in a commercial product.";
    case "attribution":
      return "You can use this in a commercial product if you display the attribution.";
    case "personal-only":
      return "Personal use only. Do NOT use this if you are a company charging for this product.";
    case "verify":
      return "Check the provider's current terms before using it commercially.";
  }
}

/** The exact env var a connected/advanced source reads, when it has one. */
export function sourceEnvVar(id: string): string | undefined {
  return SOURCE_BY_ID[id]?.envVar;
}
