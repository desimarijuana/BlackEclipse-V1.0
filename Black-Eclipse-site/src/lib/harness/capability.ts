// ─── Global capability matrix ───────────────────────────────────────────────
// The honest answer to "what can Eclipse actually do for this market?".
//
// Before this, `get_coverage` returned a flat list of countries with the same
// three asset classes and the same four data types for every one of them — which
// implied that financial statements were retrievable anywhere quotes were. That
// is false: a market can be RECOGNISED (its instruments are in the universe)
// while having no working statement route, and the reverse. The matrix separates
// the axes so a caller never reads "the country is listed" as "every capability
// works here".
//
// Axes, per market × asset class:
//   1. recognised   — the market id/currency/exchange are known to the app.
//   2. universe     — instruments are searchable in the vault (observed count).
//   3. quote        — a live/precise price route exists and is configured.
//   4. history      — a historical-price route exists and is configured.
//   5. fundamentals — a statement/profile route exists (NOT implied by quotes).
//   6. filings      — an official filing/regulator route exists for issuers here.
//   7. web          — search / fetch / document routes (market-independent).
//
// Each axis carries a LEVEL (implemented+configured / implemented but
// unconfigured / not implemented / recognised only) and, separately, an
// OBSERVED health overlay from recorded runs (working / failing / unknown — never
// conflating "no attempts yet" with healthy or failing).

import { COVERAGE } from "./coverage";
import { MARKET_SLUG } from "@/lib/scraper/fetchers/tradingview";
import { MARKET_CURRENCY_ISO, MARKET_FULL_NAME } from "@/lib/markets";

/** How far a capability is implemented, independent of observed health. */
export type CapabilityLevel =
  | "configured"        // a code path exists AND its credential/base is present
  | "unconfigured"      // a code path exists but needs a key/base URL that is absent
  | "not_implemented"   // no route exists for this market/asset class
  | "recognized_only";  // the market is known but has no data path

/** An observed overlay from recorded runs. Never guesses. */
export type ObservedHealth = "working" | "degraded" | "failing" | "unknown";

export interface CapabilityAxis {
  level: CapabilityLevel;
  /** Which route/provider implements it (implementation detail, for the operator). */
  via?: string;
  observed: ObservedHealth;
  /** ISO timestamp of the last successful retrieval, when one was recorded. */
  lastSuccess?: string | null;
  lastError?: string | null;
}

export interface MarketCapabilities {
  market: string;
  name: string;
  currency: string;
  assetClasses: string[];
  /** Observed instrument-universe size from the vault, or null when unknown. */
  universe: number | null;
  quote: CapabilityAxis;
  history: CapabilityAxis;
  fundamentals: CapabilityAxis;
  filings: CapabilityAxis;
  web: CapabilityAxis;
  /** True when a live smoke check has been recorded for this market (opt-in). */
  liveChecked: boolean;
}

/**
 * Markets with a working LIVE structured quote route. TradingView's whole-market
 * scan covers these; US uses the yfinance bridge; crypto/FX have dedicated
 * endpoints. This is an implementation fact, mirrored from the fetcher chain —
 * it is NOT "every market in the coverage registry".
 */
const TRADINGVIEW_QUOTE_MARKETS = new Set(Object.keys(MARKET_SLUG));
const LIVE_QUOTE_MARKETS = new Set([...TRADINGVIEW_QUOTE_MARKETS, "US", "CRYPTO", "FX"]);

/**
 * Official filing/regulator routes by market. SEC covers US issuers. For every
 * other market the route is NOT IMPLEMENTED here (local regulator/exchange
 * filing systems are a future adapter), which the matrix states rather than
 * implying SEC or a search engine stands in for it. `web` research may still
 * find a filing; that is a different (bounded, snippet-caveated) route.
 */
const FILING_ROUTES: Record<string, { level: CapabilityLevel; via?: string }> = {
  US: { level: "configured", via: "SEC EDGAR (data.sec.gov XBRL + filing index)" },
  // EU issuers with US cross-listings can appear in SEC; that is issuer-specific,
  // not a market-level guarantee, so it is not advertised per-market here.
};

export interface CapabilityInputs {
  /** Vault instrument count per market, when the caller could read it. */
  universeCounts?: Record<string, number>;
  /** Markets with at least one recorded live success (from SourceHealth). */
  observedByMarket?: Record<string, ObservedHealth>;
  /** Markets with a recorded live smoke check. */
  liveCheckedMarkets?: string[];
  /** Fundamentals providers usable right now, keyed by whether they need a key. */
  fundamentalsAvailability?: {
    /** US-filings route (SEC) usable. */
    usFilings: boolean;
    /** A keyed multi-market vendor (FMP/Yahoo) is configured. */
    multiMarketVendor: boolean;
  };
  /** Whether the web search/fetch/document routes are usable. */
  webAvailable?: boolean;
}

/**
 * Build the capability matrix. Pure w.r.t. its inputs — the bridge supplies the
 * observed counts/health; this function only assembles and classifies.
 */
export function buildCapabilityMatrix(inputs: CapabilityInputs = {}): MarketCapabilities[] {
  const counts = inputs.universeCounts ?? {};
  const observed = inputs.observedByMarket ?? {};
  const liveChecked = new Set(inputs.liveCheckedMarkets ?? []);
  const fa = inputs.fundamentalsAvailability ?? { usFilings: false, multiMarketVendor: false };
  const web = inputs.webAvailable ?? true;

  const webAxis: CapabilityAxis = {
    level: web ? "configured" : "unconfigured",
    via: "web search + SSRF-safe fetch (HTML/JSON/XML/PDF)",
    observed: "unknown",
  };

  const markets = new Set<string>(Object.keys(COVERAGE));
  for (const m of LIVE_QUOTE_MARKETS) markets.add(m);

  const out: MarketCapabilities[] = [];
  for (const market of markets) {
    const entry = COVERAGE[market];
    const assetClasses = entry?.assetClasses ?? [];
    const hasUniverse = (counts[market] ?? 0) > 0;
    const obs = observed[market] ?? "unknown";
    const isLiveQuote = LIVE_QUOTE_MARKETS.has(market);
    const isStatementMarket = (entry?.dataTypes ?? []).includes("financial_statements");

    // Quote/history: implemented for live-quote markets; recognized-only when the
    // registry lists the market but no live route covers it.
    const quoteLevel: CapabilityLevel = isLiveQuote ? "configured" : assetClasses.length ? "not_implemented" : "recognized_only";
    const quoteVia = market === "US" ? "yfinance bridge" : market === "CRYPTO" ? "public crypto endpoint" : market === "FX" ? "FX provider" : TRADINGVIEW_QUOTE_MARKETS.has(market) ? "TradingView market scan" : undefined;
    const historyLevel: CapabilityLevel = isLiveQuote ? "configured" : "not_implemented";

    // Fundamentals: SEC is US-only; a keyed multi-market vendor widens it, but
    // only if actually configured. Never implied by quote coverage.
    let fundLevel: CapabilityLevel = "not_implemented";
    let fundVia: string | undefined;
    if (market === "US" && fa.usFilings) {
      fundLevel = "configured";
      fundVia = "SEC EDGAR filings/XBRL";
    } else if (fa.multiMarketVendor && isStatementMarket) {
      fundLevel = "configured";
      fundVia = "configured fundamentals vendor";
    } else if (isStatementMarket) {
      fundLevel = "unconfigured";
      fundVia = "needs a configured fundamentals provider (e.g. FMP key)";
    }

    const filingRoute = FILING_ROUTES[market];
    const filings: CapabilityAxis = filingRoute
      ? { level: filingRoute.level, via: filingRoute.via, observed: "unknown" }
      : { level: "not_implemented", observed: "unknown" };

    out.push({
      market,
      name: MARKET_FULL_NAME[market] ?? market,
      currency: MARKET_CURRENCY_ISO[market] ?? "USD",
      assetClasses,
      universe: market in counts ? counts[market] : null,
      quote: { level: quoteLevel, via: quoteVia, observed: obs },
      history: { level: historyLevel, via: isLiveQuote ? (quoteVia ?? "structured history") : undefined, observed: obs },
      fundamentals: { level: fundLevel, via: fundVia, observed: isStatementMarket ? obs : "unknown" },
      filings,
      web: webAxis,
      liveChecked: liveChecked.has(market),
    });
  }

  // Recognised-but-uncovered pseudo-markets (e.g. DERIV) stay in the list so a
  // caller reading them sees an explicit "recognized only", never a silent gap.
  for (const market of markets) {
    if (out.some((c) => c.market === market)) continue;
    out.push({
      market,
      name: MARKET_FULL_NAME[market] ?? market,
      currency: MARKET_CURRENCY_ISO[market] ?? "USD",
      assetClasses: [],
      universe: null,
      quote: { level: "recognized_only", observed: "unknown" },
      history: { level: "not_implemented", observed: "unknown" },
      fundamentals: { level: "not_implemented", observed: "unknown" },
      filings: { level: "not_implemented", observed: "unknown" },
      web: webAxis,
      liveChecked: false,
    });
  }

  return out.sort((a, b) => a.market.localeCompare(b.market));
}

/** A compact, one-line capability verdict for the coverage tool's summary. */
export function capabilityLine(c: MarketCapabilities): string {
  const lvl = (axis: CapabilityAxis) => axis.level.replace("_", " ");
  return (
    `${c.market} (${c.currency}) — ` +
    `universe:${c.universe ?? "unknown"} · ` +
    `quote:${lvl(c.quote)} · history:${lvl(c.history)} · ` +
    `fundamentals:${lvl(c.fundamentals)} · filings:${lvl(c.filings)} · ` +
    `web:${lvl(c.web)}` +
    (c.liveChecked ? " · live-checked" : "")
  );
}
