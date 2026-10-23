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
import { quoteEligibility } from "./provider-eligibility";

/** How far a capability is implemented, independent of observed health. */
export type CapabilityLevel =
  | "configured"        // a code path exists AND its credential/base is present
  | "unconfigured"      // a code path exists but needs a key/base URL that is absent
  | "not_implemented"   // no route exists for this market/asset class
  | "recognized_only";  // the market is known but has no data path

/**
 * A matrix row that cannot be reconciled (Phase 3): a non-`unknown` observation
 * exists at an axis whose LEVEL says the route is not implemented. This is a
 * REPRESENTED failure, never silently smoothed over — the caller sees the
 * contradiction and its reason.
 */
export type MatrixInconsistency = "matrixInconsistent";

/** An observed overlay from recorded runs. Never guesses. */
export type ObservedHealth = "working" | "degraded" | "failing" | "unknown";

export interface CapabilityAxis {
  level: CapabilityLevel;
  /** Which route/provider implements it (implementation detail, for the operator). */
  via?: string;
  observed: ObservedHealth;
  /** ISO timestamp of the last successful retrieval, when one was recorded. */
  lastSuccess?: string | null;
  /**
   * Set when the axis is internally contradictory (Phase 3): a non-unknown
   * observation against a `not_implemented` level. When present, `level` is
   * forced to `not_implemented` and the inconsistency + reason are recorded.
   */
  inconsistent?: MatrixInconsistency | null;
  inconsistencyReason?: string | null;
  /**
   * D7: an explicit, machine-readable mismatch block. Emitted whenever the
   * DECLARED level and the OBSERVED run-ledger health disagree, naming both
   * values and the config key that owns the declaration. A CI check fails on an
   * unexplained block (see `capability-mismatch-allowlist.json`).
   */
  mismatch?: {
    declared: CapabilityLevel;
    observed: ObservedHealth;
    configKey: string;
    explanationRequired: boolean;
  } | null;
  /**
   * For a route that is not the primary venue route (Phase 4.3): "primary" or
   * "secondary". A secondary route is never presented as primary.
   */
  tier?: "primary" | "secondary" | null;
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
 * Official filing/regulator routes by market.
 *
 * `configured` = a direct structured/bridge route exists for this market.
 * `unconfigured` = the local regulator/exchange filing system is a RECOGNISED
 *   route (the market's real filing authority) but has no direct structured
 *   adapter here; it is reachable only through bounded web research into that
 *   regulator, and — for the credential-gated ones (Korea DART API) — needs an
 *   operator-supplied key that is currently absent. The matrix names the actual
 *   system rather than pretending SEC or a search engine stands in for it.
 *
 * A missing credential disables ONLY that route; issuer IR / structured vendors
 * / bounded secondary web remain eligible (WS4). `not_implemented` is reserved
 * for markets with no known filing authority at all.
 */
/**
 * Markets whose structured data route is DECLARED SECONDARY (Harness closeout
 * Phase 4.3): the primary venue route is bot-walled or the documents are scanned
 * images with no extractable text, so the working route is a non-primary one.
 * A secondary route is labelled as such and never presented as primary.
 */
export const SECONDARY_TIER_MARKETS: Record<string, string> = {
  PK: "PSX is bot-walled and primary filings are scanned images; served via the secondary structured/web route",
};

export const FILING_ROUTES: Record<string, { level: CapabilityLevel; via?: string }> = {
  US: { level: "configured", via: "SEC EDGAR (data.sec.gov XBRL + filing index)" },
  TW: { level: "unconfigured", via: "Taiwan MOPS (公開資訊觀測站) — web research route; no direct adapter" },
  KR: { level: "unconfigured", via: "Korea DART — web route; direct API needs a DART key (absent)" },
  IN: { level: "unconfigured", via: "India BSE/NSE — web research route; no direct adapter" },
  PK: { level: "unconfigured", via: "Pakistan PSX — web research route; no direct adapter" },
  BR: { level: "unconfigured", via: "Brazil CVM/B3 — web research route; no direct adapter" },
  JP: { level: "unconfigured", via: "Japan TDnet/EDINET — web research route; no direct adapter" },
  UK: { level: "unconfigured", via: "UK Companies House — web research route; no direct adapter" },
  DE: { level: "unconfigured", via: "Germany Bundesanzeiger — web research route; no direct adapter" },
  FR: { level: "unconfigured", via: "France AMF — web research route; no direct adapter" },
  HK: { level: "unconfigured", via: "HKEXnews — web research route; no direct adapter" },
  CN: { level: "unconfigured", via: "SSE/SZSE — web research route; no direct adapter" },
  CA: { level: "unconfigured", via: "Canada SEDAR+ — web research route (bot-walled); no direct adapter" },
  AU: { level: "unconfigured", via: "Australia ASX — web research route; no direct adapter" },
  SG: { level: "unconfigured", via: "Singapore SGX — web research route; no direct adapter" },
  MY: { level: "unconfigured", via: "Bursa Malaysia — web research route; no direct adapter" },
  TH: { level: "unconfigured", via: "Thailand SET — web research route; no direct adapter" },
  ID: { level: "unconfigured", via: "Indonesia IDX — web research route; no direct adapter" },
  SA: { level: "unconfigured", via: "Saudi Tadawul — web research route; no direct adapter" },
  AE: { level: "unconfigured", via: "UAE ADX/DFM — web research route; no direct adapter" },
  ZA: { level: "unconfigured", via: "South Africa JSE — web research route; no direct adapter" },
  TR: { level: "unconfigured", via: "Borsa Istanbul — web research route; no direct adapter" },
  MX: { level: "unconfigured", via: "Mexico BMV — web research route; no direct adapter" },
  // EU issuers with US cross-listings can appear in SEC; that is issuer-specific,
  // not a market-level guarantee, so it is not advertised per-market here.
};

export interface CapabilityInputs {
  /** Vault instrument count per market, when the caller could read it. */
  universeCounts?: Record<string, number>;
  /** Markets with at least one recorded live success (from SourceHealth). */
  observedByMarket?: Record<string, ObservedHealth>;
  /**
   * Observed health PER capability, keyed `<market>|<capability>` where
   * capability ∈ quote/history/fundamentals/filings/web. When present this is
   * authoritative for the matching axis: a working quote never lends its health
   * to the statement or filings axes (WS3). Missing keys fall back to
   * `observedByMarket` for backwards compatibility.
   */
  observedByCapability?: Record<string, ObservedHealth>;
  /** Markets with a recorded live smoke check. */
  liveCheckedMarkets?: string[];
  /** Fundamentals providers usable right now. */
  fundamentalsAvailability?: {
    /** US-filings route (SEC) usable. */
    usFilings: boolean;
    /** A keyless multi-market vendor (yfinance bridge) is usable. */
    keylessVendor: boolean;
    /** A keyed multi-market vendor (FMP) is configured. */
    multiMarketVendor: boolean;
  };
  /** Whether the web search/fetch/document routes are usable. */
  webAvailable?: boolean;
}

/**
 * Build the capability matrix. Pure w.r.t. its inputs — the bridge supplies the
 * observed counts/health; this function only assembles and classifies.
 */
/**
 * Reconcile a declared LEVEL with its OBSERVED health (Phase 3 invariant).
 *
 * A non-`unknown` observation REQUIRES an implemented route. If the declared
 * level says the axis is not implemented but a recorded run observed it working
 * (or failing), that is a CONTRADICTION — represented explicitly as
 * `matrixInconsistent` (level forced to `not_implemented`, reason recorded),
 * never smoothed over.
 */
export const CAPABILITY_CONFIG_KEYS: Record<string, string> = {
  quote: "harness.capability.quote",
  history: "harness.capability.history",
  fundamentals: "harness.capability.fundamentals",
  filings: "harness.capability.filings",
  web: "harness.capability.web",
};

function reconcileAxis(
  axis: CapabilityAxis, market: string, axisName: string,
): CapabilityAxis {
  const implemented = axis.level === "configured" || axis.level === "unconfigured";
  const configKey = `${CAPABILITY_CONFIG_KEYS[axisName] ?? `harness.capability.${axisName}`}.${market}`;
  if (!implemented && axis.observed !== "unknown") {
    return {
      ...axis,
      level: axis.level === "recognized_only" ? "recognized_only" : "not_implemented",
      inconsistent: "matrixInconsistent",
      inconsistencyReason:
        `${market} ${axisName}: observed "${axis.observed}" but the declared level is ` +
        `"${axis.level}" — a non-unknown observation requires an implemented route`,
      mismatch: {
        declared: axis.level,
        observed: axis.observed,
        configKey,
        explanationRequired: true,
      },
    };
  }
  // The reverse contradiction: declared runnable but recorded as failing.
  if (implemented && (axis.observed === "failing" || axis.observed === "degraded")) {
    return {
      ...axis,
      mismatch: {
        declared: axis.level,
        observed: axis.observed,
        configKey,
        explanationRequired: true,
      },
    };
  }
  return axis;
}

export function buildCapabilityMatrix(inputs: CapabilityInputs = {}): MarketCapabilities[] {
  const counts = inputs.universeCounts ?? {};
  const observed = inputs.observedByMarket ?? {};
  const observedByCapability = inputs.observedByCapability ?? {};
  const hasCapabilityHealth = Object.keys(observedByCapability).length > 0;
  const liveChecked = new Set(inputs.liveCheckedMarkets ?? []);
  const fa = inputs.fundamentalsAvailability ?? { usFilings: false, keylessVendor: false, multiMarketVendor: false };
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
    const obs = observed[market] ?? "unknown";
    // Per-axis observed health (WS3). When capability-keyed health is supplied
    // it is authoritative for that axis; otherwise fall back to the market-level
    // overlay for backwards compatibility.
    const obsFor = (capability: string): ObservedHealth =>
      observedByCapability[`${market}|${capability}`] ?? (hasCapabilityHealth ? "unknown" : obs);
    // A market is quote-configured only when it has a live route AND the
    // provider eligibility registry declares it eligible (Phase 3.3). A declared
    // `not_eligible` market (e.g. `.NG`, `AE`) is not configured; an `unknown`
    // market is configured-but-unverified (the sample has not been proven).
    const elig = quoteEligibility(market);
    const isLiveRoute = LIVE_QUOTE_MARKETS.has(market);
    const quoteReachable = isLiveRoute && elig.eligible !== "not_eligible";
    const isStatementMarket = (entry?.dataTypes ?? []).includes("financial_statements");

    // Quote/history: implemented for live-quote markets; recognized-only when the
    // registry lists the market but no live route covers it.
    const quoteLevel: CapabilityLevel = quoteReachable
      ? "configured"
      : isLiveRoute
        ? "not_implemented" // a live route exists but the provider is not eligible
        : assetClasses.length ? "not_implemented" : "recognized_only";
    const quoteVia =
      market === "US" ? "yfinance bridge"
        : market === "CRYPTO" ? "public crypto endpoint"
        : market === "FX" ? "FX provider"
        : TRADINGVIEW_QUOTE_MARKETS.has(market) ? "TradingView market scan"
        : undefined;
    // A declared-secondary market (Phase 4.3, e.g. PK: bot-walled venue) carries
    // the secondary tier so a caller never treats it as the primary venue route.
    const quoteTier: "primary" | "secondary" | null =
      elig.eligible === "not_eligible" || market in SECONDARY_TIER_MARKETS
        ? "secondary"
        : "primary";
    const historyLevel: CapabilityLevel = quoteReachable ? "configured" : "not_implemented";

    // Fundamentals: SEC is US-only; a keyless multi-market vendor (yfinance) or a
    // configured keyed vendor widens coverage. Never implied by quote coverage.
    let fundLevel: CapabilityLevel = "not_implemented";
    let fundVia: string | undefined;
    if (market === "US" && fa.usFilings) {
      fundLevel = "configured";
      fundVia = "SEC EDGAR filings/XBRL";
    } else if (isStatementMarket && fa.keylessVendor) {
      fundLevel = "configured";
      fundVia = "yfinance bridge (keyless, multi-market)";
    } else if (isStatementMarket && fa.multiMarketVendor) {
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

    // A recognised-but-UNCOVERED venue (no asset classes AND no data types, e.g.
    // DERIV) must never claim `configured` on ANY axis — not even web/documents,
    // because there is no priced instrument for a document route to serve
    // (Harness closeout Phase 4.2). The market-independent web transport being
    // built in does not make DERIV covered.
    const isUncoveredVenture = assetClasses.length === 0 && (entry?.dataTypes ?? []).length === 0;
    const marketWebAxis: CapabilityAxis = isUncoveredVenture
      ? { level: "not_implemented", observed: "unknown", via: "no priced instrument in an uncovered venue" }
      : { ...webAxis };

    const quote = reconcileAxis(
      { level: quoteLevel, via: quoteVia, observed: obsFor("quote"), tier: quoteTier }, market, "quote",
    );
    const history = reconcileAxis(
      {
        level: historyLevel,
        via: quoteReachable ? (quoteVia ?? "structured history") : undefined,
        observed: obsFor("history"),
        tier: quoteTier,
      },
      market, "history",
    );
    const fundamentals = reconcileAxis(
      { level: fundLevel, via: fundVia, observed: isStatementMarket ? obsFor("fundamentals") : "unknown" },
      market, "fundamentals",
    );
    const filingsAxis = reconcileAxis({ ...filings, observed: obsFor("filings") }, market, "filings");
    const webAxisReconciled = reconcileAxis({ ...marketWebAxis, observed: obsFor("web") }, market, "web");

    out.push({
      market,
      name: MARKET_FULL_NAME[market] ?? market,
      // A real ISO currency, never the USD fallback for a known market. The
      // registry carries CH/KW/QA; an unknown market keeps MARKET_CURRENCY_ISO's
      // explicit value or the honest "N/A" for an uncovered venue.
      currency: MARKET_CURRENCY_ISO[market] ?? (market === "DERIV" ? "N/A" : "USD"),
      assetClasses,
      universe: market in counts ? counts[market] : null,
      quote,
      history,
      fundamentals,
      filings: filingsAxis,
      web: webAxisReconciled,
      liveChecked: liveChecked.has(market),
    });
  }

  // Recognised-but-uncovered pseudo-markets (e.g. DERIV) stay in the list so a
  // caller reading them sees an explicit "recognized only"/"not covered", never
  // a silent gap. They never claim `configured` on any axis (Phase 4.2).
  for (const market of markets) {
    if (out.some((c) => c.market === market)) continue;
    out.push({
      market,
      name: MARKET_FULL_NAME[market] ?? market,
      currency: MARKET_CURRENCY_ISO[market] ?? "USD",
      assetClasses: [],
      universe: null,
      quote: reconcileAxis({ level: "recognized_only", observed: "unknown" }, market, "quote"),
      history: reconcileAxis({ level: "not_implemented", observed: "unknown" }, market, "history"),
      fundamentals: reconcileAxis({ level: "not_implemented", observed: "unknown" }, market, "fundamentals"),
      filings: reconcileAxis({ level: "not_implemented", observed: "unknown" }, market, "filings"),
      web: reconcileAxis({ ...webAxis }, market, "web"),
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
