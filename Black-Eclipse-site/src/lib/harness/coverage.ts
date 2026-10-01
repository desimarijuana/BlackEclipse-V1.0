// ─── Declared coverage registry (C1) ────────────────────────────────────────
// Coverage is DATA, not implicit code paths. Before this, a non-US macro series
// was routed to a US-only backend and the routing was hidden in control flow.
// Now the system can answer "which venues / currencies / asset classes do we
// cover, and by what source?" — and an unregistered request returns
// `not_covered` instead of guessing a source.
//
// This registry is the single place coverage is declared. Adding a source or a
// market is a data change here, mirrored by the actual provider capabilities.

import { MARKET_CURRENCY_ISO } from "../markets";
import type { AssetClass } from "../instrument-identity";

export interface CoverageEntry {
  /** Canonical market id. */
  market: string;
  /** ISO 4217 currency of instruments in this market. */
  currency: string;
  /** Asset classes this system has a data path for in this market. */
  assetClasses: AssetClass[];
  /** The source ids that can serve structured data here. */
  sources: string[];
  /**
   * Data types the structured path can serve. Web/news research is separate and
   * applies wherever a web path exists (it does not make a market "covered" for
   * precise quantitative data — see the retrieval layer's WEB exclusion rules).
   */
  dataTypes: string[];
  /**
   * A declared limitation, when one exists (e.g. thin upstream data, or a
   * recognised-but-not-covered venue). Surfaced so a reader sees the blocker
   * rather than inferring a capability. Never a fabricated capability.
   */
  blocker?: string;
}

/** Asset classes every covered equity market supports by default. */
const EQUITY_CLASSES: AssetClass[] = ["equity", "etf", "fund"];
/** Crypto markets support crypto + derivatives on crypto. */
const CRYPTO_CLASSES: AssetClass[] = ["crypto"];

/**
 * The declared registry. `sources` names the retrieval-layer source ids
 * (`JDDS`, `LIVE_STRUCTURED`) — never a provider (yfinance/TradingView), which
 * are implementation details behind `LIVE_STRUCTURED`.
 */
const STRUCTURED_DEFAULT = ["JDDS", "LIVE_STRUCTURED"];
const STRUCTURED_TYPES = ["current_quote", "historical_prices", "company_profile", "financial_statements"];
const MACRO_TYPES = ["macro_series"];

function entry(
  market: string,
  assetClasses: AssetClass[],
  dataTypes: string[],
  extra: { blocker?: string; sources?: string[] } = {},
): CoverageEntry {
  return {
    market,
    currency: MARKET_CURRENCY_ISO[market] ?? "USD",
    assetClasses,
    sources: extra.sources ?? STRUCTURED_DEFAULT,
    dataTypes,
    ...(extra.blocker ? { blocker: extra.blocker } : {}),
  };
}

export const COVERAGE: Record<string, CoverageEntry> = {
  US: entry("US", [...EQUITY_CLASSES, "debt", "index", "derivative"], [...STRUCTURED_TYPES, ...MACRO_TYPES]),
  PK: entry("PK", [...EQUITY_CLASSES, "debt"], STRUCTURED_TYPES),
  IN: entry("IN", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  CN: entry("CN", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  TW: entry("TW", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  HK: entry("HK", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  JP: entry("JP", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  KR: entry("KR", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  SG: entry("SG", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  MY: entry("MY", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  AU: entry("AU", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  UK: entry("UK", [...EQUITY_CLASSES, "index"], STRUCTURED_TYPES),
  DE: entry("DE", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  FR: entry("FR", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  NL: entry("NL", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  CA: entry("CA", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  BR: entry("BR", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  MX: entry("MX", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  SA: entry("SA", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  AE: entry("AE", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  ZA: entry("ZA", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  EG: entry("EG", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  NG: entry("NG", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  RU: entry("RU", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  TR: entry("TR", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  ID: entry("ID", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  TH: entry("TH", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  VN: entry("VN", [...EQUITY_CLASSES], STRUCTURED_TYPES),
  // Gulf/Swiss venues reached by the TradingView scan. They are declared here so
  // the matrix reports their real currency and a declared blocker rather than
  // inventing a MARKET_CURRENCY_ISO fallback of USD (Harness closeout Phase 3.2).
  // `blocker` records the known data-quality limitation honestly.
  CH: entry("CH", [...EQUITY_CLASSES], STRUCTURED_TYPES, {
    blocker: "quotes via TradingView scan; statement/filing route unconfigured",
  }),
  KW: entry("KW", [...EQUITY_CLASSES], STRUCTURED_TYPES, {
    blocker: "thin quote data upstream; statement route unconfigured",
  }),
  QA: entry("QA", [...EQUITY_CLASSES], STRUCTURED_TYPES, {
    blocker: "thin quote data upstream; statement route unconfigured",
  }),
  CRYPTO: entry("CRYPTO", CRYPTO_CLASSES, ["current_quote", "historical_prices"]),
  // FX is a global OTC market; base/quote direction is the identity.
  FX: entry("FX", ["fx"], ["current_quote", "historical_prices"]),
  // Derivative venues are RECOGNISED but NOT COVERED — no precise price source.
  // Listing them lets an `ES`/`CME` request be NOT_COVERED (the caller named a
  // real venue) rather than "unknown venue". They carry NO asset classes and NO
  // data types, so they must never yield a `configured` claim on any axis
  // (Harness closeout Phase 4.2). `blocker` states this explicitly.
  DERIV: entry("DERIV", [], [], {
    blocker: "precise price source unavailable; recognised venue only (not_covered)",
  }),
};

/** Is there declared coverage for this market + asset class? */
export function isCovered(market: string, assetClass: AssetClass): boolean {
  const c = COVERAGE[market];
  return Boolean(c && c.assetClasses.includes(assetClass));
}

/**
 * The full set of (source, market, assetClass) combinations the system *can*
 * serve — whether or not any has recorded a run. `get_source_health` merges this
 * with recorded runs so "no data" (a known source with no runs yet) is
 * distinguishable from "no source" (a combination we do not support).
 */
export interface HealthTarget {
  source: string;
  market: string;
  assetClass: AssetClass;
  /**
   * The data capability this health row is about. A route is only meaningful
   * per-capability: `yfinance · US · equity · live_quote` succeeding says
   * NOTHING about `yfinance · US · equity · financial_statements`. Before this,
   * health was keyed by (source × market × assetClass) only, so a working quote
   * was indistinguishable from a working statement route. `quote` is the
   * legacy default for pre-existing rows.
   */
  capability: string;
  /**
   * How the health was observed. `fixture` rows come from deterministic offline
   * tests; `live` rows come from real provider smoke/production runs. A fixture
   * must never be presented as live-provider health.
   */
  probeKind: "live" | "fixture";
}

/**
 * The capabilities that require their OWN health record. A capability is listed
 * with the source ids that may serve it; each becomes a declared target that
 * reports `unknown` until it has recorded runs.
 */
const CAPABILITY_TARGETS: Array<{ capability: string; sources: string[] }> = [
  { capability: "live_quote", sources: ["LIVE_STRUCTURED"] },
  { capability: "price_history", sources: ["LIVE_STRUCTURED"] },
  { capability: "fundamentals", sources: ["JDDS", "LIVE_STRUCTURED"] },
  { capability: "financial_statements", sources: ["JDDS", "LIVE_STRUCTURED", "SEC"] },
  { capability: "sec_filings", sources: ["SEC"] },
  { capability: "news", sources: ["WEB"] },
  { capability: "web_search", sources: ["WEB"] },
  { capability: "web_fetch", sources: ["WEB"] },
];

/** The declared source registry per market × asset class (legacy quote axis). */
export function healthTargets(): HealthTarget[] {
  const out: HealthTarget[] = [];
  for (const entry of Object.values(COVERAGE)) {
    for (const assetClass of entry.assetClasses) {
      for (const source of entry.sources) {
        out.push({ source, market: entry.market, assetClass, capability: "quote", probeKind: "live" });
      }
    }
  }
  // FX and crypto live on the live structured path.
  for (const [market, assetClass] of [["FX", "fx"], ["CRYPTO", "crypto"]] as const) {
    out.push({ source: "LIVE_STRUCTURED", market, assetClass, capability: "live_quote", probeKind: "live" });
  }
  return out;
}

/**
 * The declared capability-specific health targets: one row per
 * (source × market × assetClass × capability). This is what lets the UI say
 * "quote works, statements untested" instead of one blended verdict. Equity
 * markets get the full capability set; every declared target with zero runs
 * stays `unknown`.
 */
export function capabilityHealthTargets(): HealthTarget[] {
  const out: HealthTarget[] = [];
  for (const entry of Object.values(COVERAGE)) {
    for (const assetClass of entry.assetClasses) {
      for (const { capability, sources } of CAPABILITY_TARGETS) {
        for (const source of sources) {
          out.push({ source, market: entry.market, assetClass, capability, probeKind: "live" });
        }
      }
    }
  }
  return out;
}

/**
 * The SINGLE declared-target builder: the legacy quote axis plus the
 * capability-specific axis, deduplicated by canonical route key. Both axes are
 * one vocabulary (a "quote" target IS a `live_quote` capability); this is the
 * one function a reader calls, so there is no second builder to drift from.
 */
export function allHealthTargets(): HealthTarget[] {
  const seen = new Set<string>();
  const out: HealthTarget[] = [];
  for (const t of [...healthTargets(), ...capabilityHealthTargets()]) {
    const key = `${t.source}|${t.market}|${t.assetClass}|${t.capability}|${t.probeKind}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(t);
  }
  return out;
}

/** The declared coverage entry for a market, or null when none. */
export function coverageFor(market: string): CoverageEntry | null {
  return COVERAGE[market] ?? null;
}

/** A queryable summary of what the system covers (for a coverage tool/surface). */
export function coverageSummary(): { market: string; currency: string; assetClasses: AssetClass[]; sources: string[] }[] {
  return Object.values(COVERAGE).map((c) => ({
    market: c.market,
    currency: c.currency,
    assetClasses: c.assetClasses,
    sources: c.sources,
  }));
}
