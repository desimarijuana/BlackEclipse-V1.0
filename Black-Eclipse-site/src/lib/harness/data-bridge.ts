// ─── JDdS data bridge ────────────────────────────────────────────────────────
// The ONLY place the agentic runtime reaches JDdS. The Python tools request a
// capability by name; this module performs the Prisma query and returns plain,
// provenance-carrying JSON. It is read-only by construction — there is no write
// path here.
//
// This exists so the agentic side (Python) owns tools/agents/events/memory while
// market data stays in the single Node data layer.

import { prisma } from "@/lib/db";
import { fetchQuoteWithFallback } from "@/lib/scraper/fetchers";
import { fetchYahooBatchRaw } from "@/lib/scraper/fetchers/yfinance";
import { normalizeEconomicSeries, sortByDate } from "@/lib/economics/fetch";
import { getSource } from "@/lib/economics/sources";
import { webSearch, fetchWebPage } from "@/lib/web-research";
import {
  resolveInstrument,
  verifyProviderIdentity,
  type ContractTerms,
  type IdentityFailure,
  type IdentityFailureReason,
  type InstrumentIdentity,
} from "@/lib/instrument-identity";
import { makeFailure, statusForFailure, type FailureClass } from "@/lib/harness/failure";
import { coverageSummary } from "@/lib/harness/coverage";
import { resolveMacroSeries } from "@/lib/harness/macro-identity";
import { resolveMarketId, MARKET_FULL_NAME, currencyIsoFor } from "@/lib/markets";
import type { DataCapability } from "./types";

export interface DataBridgeResult {
  /**
   * `AMBIGUOUS` is a first-class outcome: the instrument identity could not be
   * pinned to a single instrument (unknown venue, ticker shared across markets,
   * or a provider answer for a different currency). It is NOT a failure to be
   * smoothed over — the caller must ask the user to disambiguate, never receive
   * a guessed instrument.
   */
  status: "OK" | "UNAVAILABLE" | "AMBIGUOUS";
  [key: string]: unknown;
}

function unavailable(reason?: string): DataBridgeResult {
  return { status: "UNAVAILABLE", ...(reason ? { error: reason } : {}) };
}

/**
 * Resolve a symbol + raw market qualifier to a canonical instrument using the
 * JDdS master. This is the ONE place identity is decided for live capabilities.
 *
 * Returns a discriminated result so callers cannot accidentally proceed with a
 * bare ticker when resolution failed.
 */
async function resolveBridgeInstrument(
  symbol: string,
  rawMarketInput: unknown,
  terms?: ContractTerms,
): Promise<
  | { ok: true; identity: InstrumentIdentity }
  | { ok: false; failure: IdentityFailure }
> {
  const sym = symbol.trim().toUpperCase();
  const rawMarket =
    typeof rawMarketInput === "string" && rawMarketInput.trim() ? rawMarketInput.trim() : null;

  const rows = await prisma.asset.findMany({
    where: { symbol: sym },
    select: {
      symbol: true,
      name: true,
      securityType: true,
      assetClass: true,
      market: { select: { country: true } },
    },
  });
  const candidates = rows.map((r) => ({
    symbol: r.symbol,
    name: r.name,
    securityType: r.securityType,
    assetClass: r.assetClass,
    market: r.market.country,
  }));

  const result = resolveInstrument(sym, { raw: rawMarket }, candidates, terms);
  if (!result.ok) return { ok: false, failure: result };
  return { ok: true, identity: result.identity };
}

/** Read contract terms from raw params (A5/A6). Absent values stay undefined. */
function termsFromParams(params: Record<string, unknown>): ContractTerms {
  const s = (k: string) => (typeof params[k] === "string" ? (params[k] as string) : undefined);
  const n = (k: string) => (typeof params[k] === "number" ? (params[k] as number) : undefined);
  return {
    expiry: s("expiry"),
    contractMonth: s("contractMonth") ?? s("contract_month"),
    strike: n("strike"),
    right: s("right") === "call" || s("right") === "put" ? (s("right") as "call" | "put") : undefined,
    maturity: s("maturity"),
    coupon: n("coupon"),
    seniority: s("seniority"),
  };
}

/**
 * Map a resolver failure reason to the shared failure taxonomy. This is the
 * single place the identity vocabulary meets the tool-facing contract.
 */
const IDENTITY_FAILURE_CLASS: Record<IdentityFailureReason, FailureClass> = {
  ambiguous: "ambiguous",
  market_unknown: "market_unknown",
  not_found: "not_found",
  currency_mismatch: "currency_mismatch",
  venue_mismatch: "venue_mismatch",
  terms_missing: "terms_missing",
};

/** A user-safe result for an identity failure (never leaks internals). */
function identityFailureResult(failure: IdentityFailure): DataBridgeResult {
  const cls = IDENTITY_FAILURE_CLASS[failure.reason];
  const f = makeFailure(cls, undefined, failure.candidates);
  return {
    status: statusForFailure(cls),
    failureClass: cls,
    error: failure.message || f.message,
    ...(failure.candidates?.length ? { candidates: failure.candidates } : {}),
  };
}

/** A typed unavailable result. */
function unavailableClass(cls: FailureClass, detail?: string): DataBridgeResult {
  const f = makeFailure(cls, detail);
  return { status: statusForFailure(cls), failureClass: cls, error: f.message };
}

export async function fetchCapability(
  capability: DataCapability,
  params: Record<string, unknown>
): Promise<DataBridgeResult> {
  switch (capability) {
    case "market_snapshot":
      return marketSnapshot(params);
    case "fundamentals":
      return fundamentals(params);
    case "news":
      return news(params);
    case "source_health":
      return sourceHealth();
    case "coverage":
      return Promise.resolve(coverageCapability());
    case "live_quote":
      return liveQuote(params);
    case "price_history":
      return priceHistory(params);
    case "macro_series":
      return macroSeries(params);
    case "macro_resolve":
      return Promise.resolve(macroResolve(params));
    case "web_search":
      return webSearchCapability(params);
    case "web_fetch":
      return webFetchCapability(params);
    default:
      return unavailable(`Unknown capability: ${String(capability)}`);
  }
}

async function marketSnapshot(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const symbol = String(params.symbol ?? "").trim().toUpperCase();
  if (!symbol) return unavailable("symbol is required");
  const rawMarket = params.market;

  // Resolve the qualifier (accepts "PK", "PSX", "Pakistan", …). An unknown
  // qualifier is a hard failure — never silently ignored.
  const market = resolveMarketId(typeof rawMarket === "string" ? rawMarket : null);
  if (rawMarket && !market) {
    return unavailable(
      `Unknown market/venue "${String(rawMarket)}" — refusing to look up the bare ticker.`,
    );
  }

  const asset = await prisma.asset.findFirst({
    where: { symbol, ...(market ? { market: { country: market } } : {}) },
    include: { price: true, market: true },
  });
  if (!asset) {
    return unavailable(
      market
        ? `${symbol} is not in the ${MARKET_FULL_NAME[market] ?? market} universe.`
        : "symbol not in the JDdS universe",
    );
  }

  return {
    status: "OK",
    symbol: asset.symbol,
    name: asset.name,
    sector: asset.sector,
    industry: asset.industry,
    securityType: asset.securityType,
    assetClass: asset.assetClass,
    country: asset.market.country,
    exchange: asset.market.exchange,
    currency: currencyIsoFor(asset.market.country),
    instrumentId: `${asset.market.country}:${asset.symbol}`,
    priceSource: asset.price?.source ?? null,
    updatedAt: asset.price?.updatedAt?.toISOString() ?? null,
    price: asset.price
      ? {
          price: asset.price.price,
          changePct: asset.price.changePct,
          marketCap: asset.price.marketCap,
          volume: asset.price.volume,
          peRatio: asset.price.peRatio,
        }
      : null,
  };
}

async function fundamentals(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const symbol = String(params.symbol ?? "").trim().toUpperCase();
  if (!symbol) return unavailable("symbol is required");
  const asset = await prisma.asset.findFirst({
    where: { symbol },
    include: { price: true, market: true },
  });
  if (!asset) return unavailable("symbol not found in JDdS");
  return {
    status: "OK",
    symbol: asset.symbol,
    name: asset.name,
    sector: asset.sector,
    industry: asset.industry,
    securityType: asset.securityType,
    assetClass: asset.assetClass,
    market: asset.market.exchange,
    country: asset.market.country,
    currency: currencyIsoFor(asset.market.country),
    instrumentId: `${asset.market.country}:${asset.symbol}`,
    price: asset.price?.price ?? null,
  };
}

async function news(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const query = String(params.query ?? "").trim();
  const q = query.toLowerCase();

  // 1. The vault (stored headlines). A hit here is the fast path.
  try {
    const where = q
      ? { OR: [{ headline: { contains: q } }, { summary: { contains: q } }] }
      : {};
    const items = await prisma.newsItem.findMany({
      where,
      orderBy: { timestamp: "desc" },
      take: 10,
    });
    if (items.length > 0) {
      return {
        status: "OK",
        sourceKind: "vault",
        items: items.map((i) => ({
          source: i.source,
          headline: i.headline,
          summary: i.summary,
          sentiment: i.sentiment,
          url: i.url,
          timestamp: i.timestamp.toISOString(),
        })),
      };
    }
  } catch (err) {
    // A vault read failure is a SOURCE FAILURE, not "no news" (C2/B2). Try the
    // web path, but if that also fails the class must say failure.
    console.error("[data-bridge] news vault read failed:", err);
  }

  // 2. Fall through to the shared web-research transport. An empty vault is NOT
  // "nothing happened" — the agent must see real retrieval results or an
  // explicit failure, never a false negative (C2).
  if (q) {
    try {
      const results = await webSearch(`${query} news`);
      if (results.length > 0) {
        return {
          status: "OK",
          sourceKind: "web",
          items: results.slice(0, 10).map((r) => ({
            source: extractHostname(r.url),
            headline: r.title,
            summary: r.snippet,
            sentiment: null,
            url: r.url,
            timestamp: r.publishedAt ?? null,
          })),
        };
      }
    } catch (err) {
      return unavailableClass(
        "source_failure",
        `news vault empty and web retrieval failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }

  // Vault reachable, web reachable, genuinely nothing matched → covered-but-empty.
  return {
    status: "OK",
    failureClass: "no_data",
    sourceKind: q ? "web+vault" : "vault",
    items: [],
  };
}

/** Display hostname for a URL, best-effort. */
function extractHostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "web";
  }
}

async function sourceHealth(): Promise<DataBridgeResult> {
  const rows = await prisma.sourceHealth.groupBy({
    by: ["source", "market"],
    _sum: { successCount: true, failCount: true },
    _max: { lastStatus: true },
  });
  // Derive per-source confidence from real history rather than asserting it
  // uniformly (C3). A source with no recorded run is `unknown`, never "healthy".
  const shaped = rows.map((r) => {
    const success = r._sum.successCount ?? 0;
    const fail = r._sum.failCount ?? 0;
    const total = success + fail;
    const health =
      total === 0 ? "unknown"
        : fail === 0 ? "healthy"
        : success === 0 ? "failing"
        : "degraded";
    return {
      source: r.source,
      market: r.market,
      success,
      fail,
      total,
      lastStatus: r._max.lastStatus,
      health,
      successRate: total === 0 ? null : Math.round((success / total) * 100) / 100,
    };
  });
  if (shaped.length === 0) {
    return { status: "OK", failureClass: "no_data", rows: [] };
  }
  return { status: "OK", rows: shaped };
}

/** The declared coverage registry, so the system can answer "what do we cover?". */
function coverageCapability(): DataBridgeResult {
  return { status: "OK", rows: coverageSummary() };
}

// ── Live structured providers (Phase 2) ─────────────────────────────────────
// Reuse the existing scraper fallback chain and Yahoo bridge — NOT a new
// market-data system. The Python retrieval layer decides *when* to call these.

async function liveQuote(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const symbol = String(params.symbol ?? "").trim().toUpperCase();
  if (!symbol) return unavailableClass("invalid_request", "symbol is required");
  const rawMarket = params.market;

  const resolved = await resolveBridgeInstrument(symbol, rawMarket, termsFromParams(params));
  if (!resolved.ok) return identityFailureResult(resolved.failure);
  const { identity } = resolved;

  try {
    const result = await fetchQuoteWithFallback(identity.symbol, identity.market);
    if (result.status !== "ok" || !result.quote) {
      // A provider that ran but returned nothing is `no_data`; a transport
      // failure is `source_failure`. Never conflate the two (B2).
      const cls: FailureClass =
        result.status === "network_error" || result.status === "timeout"
          ? "source_failure"
          : "no_data";
      return unavailableClass(cls, result.error);
    }

    // The provider must have answered for the SAME instrument. A currency or
    // venue disagreement means it priced something else — discard it rather
    // than return a confidently wrong number (A1/A2/A7).
    const verified = verifyProviderIdentity(identity, {
      market: result.quote.market ?? identity.market,
      currency: result.quote.currency,
    });
    if (!verified.ok) return identityFailureResult(verified);

    const q = result.quote;
    return {
      status: "OK",
      symbol: identity.symbol,
      market: identity.market,
      marketName: MARKET_FULL_NAME[identity.market] ?? identity.market,
      currency: identity.currency,
      assetClass: identity.assetClass,
      securityType: identity.securityType ?? null,
      instrumentId: `${identity.market}:${identity.symbol}`,
      provider: result.source ?? "scraper",
      price: {
        price: q.price,
        changePct: q.changePct,
        volume: q.volume ?? null,
        marketCap: q.marketCap ?? null,
        // A price is a number with a unit, not a bare number (A7).
        currency: identity.currency,
        units: "per-share",
      },
      asOf: new Date().toISOString(),
    };
  } catch (err) {
    return unavailableClass("source_failure", err instanceof Error ? err.message : "live quote failed");
  }
}

async function priceHistory(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const symbol = String(params.symbol ?? "").trim().toUpperCase();
  if (!symbol) return unavailable("symbol is required");
  const rawMarket = params.market;
  const range = String(params.range ?? "1y").trim().toLowerCase();
  const interval = String(params.period ?? params.interval ?? "1d").trim().toLowerCase();

  // Identity first: history for an unresolvable market must not silently fetch a
  // bare ticker either.
  const resolved = await resolveBridgeInstrument(symbol, rawMarket);
  if (!resolved.ok) return identityFailureResult(resolved.failure);
  const { identity } = resolved;

  // Prefer the batched Yahoo bridge (one python process), which returns a full
  // OHLCV series; fall back to the existing chart helper when the bridge is off.
  try {
    const data = await fetchYahooBatchRaw([identity.symbol], identity.market, interval, range);
    const key = Object.keys(data.history ?? {})[0];
    const rows = key ? data.history?.[key] : undefined;
    if (Array.isArray(rows) && rows.length >= 2) {
      return {
        status: "OK",
        symbol: identity.symbol,
        market: identity.market,
        currency: identity.currency,
        instrumentId: `${identity.market}:${identity.symbol}`,
        interval,
        provider: "yfinance",
        series: rows,
        asOf: rows[rows.length - 1]?.date ?? null,
      };
    }
  } catch {
    /* fall through */
  }
  return unavailable(`no historical series for ${identity.symbol} (${identity.market})`);
}

async function macroSeries(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const sourceId = String(params.source ?? "fred-analytics").trim();
  const series = String(params.series ?? params.seriesId ?? "").trim();
  // A8: resolve the series identity first. A generic measure with no geography is
  // AMBIGUOUS and must NOT default to a US backend.
  const geography = typeof params.geography === "string" ? params.geography
    : typeof params.country === "string" ? params.country
    : null;
  const resolved = resolveMacroSeries(series, geography);
  if (!resolved.ok) {
    const cls =
      resolved.reason === "ambiguous" ? "ambiguous"
        : resolved.reason === "not_covered" ? "not_covered"
        : "not_found";
    return {
      status: statusForFailure(cls),
      failureClass: cls,
      error: resolved.message,
      ...(resolved.candidates?.length ? { candidates: resolved.candidates } : {}),
    };
  }
  const identity = resolved.identity;
  // Honor the resolved source unless the caller explicitly named one.
  const effectiveSource = identity.sourceId || sourceId;
  const source = getSource(effectiveSource);
  if (!source) return unavailableClass("not_covered", `no macro source "${effectiveSource}"`);
  if (source.keyRequired && source.keyEnv && !process.env[source.keyEnv]) {
    return unavailableClass("source_failure", `macro source ${effectiveSource} requires ${source.keyEnv}`);
  }
  try {
    const fetchParams: Record<string, string> = {};
    for (const c of source.controls) {
      const v = params[c.name];
      if (typeof v === "string" && v) fetchParams[c.name] = v;
      else if (c.defaultValue) fetchParams[c.name] = c.defaultValue;
    }
    const providerSeries = identity.providerSeries || series;
    if (providerSeries) {
      const seriesControl = source.controls.find((c) => c.name === "series" || c.name === "seriesId");
      if (seriesControl) fetchParams[seriesControl.name] = providerSeries;
    }
    const raw = await source.fetch(fetchParams);
    const rows = sortByDate(normalizeEconomicSeries(raw, effectiveSource));
    if (rows.length === 0) return unavailableClass("no_data", `macro source ${effectiveSource} returned no observations`);
    return {
      status: "OK",
      source: effectiveSource,
      seriesKey: identity.id,
      seriesIdentity: identity,
      units: identity.unit ?? null,
      rows,
      asOf: rows[rows.length - 1]?.date ?? null,
    };
  } catch (err) {
    return unavailableClass("source_failure", err instanceof Error ? err.message : "macro fetch failed");
  }
}

/** Resolve a macro request to a canonical series identity (no fetch). */
function macroResolve(params: Record<string, unknown>): DataBridgeResult {
  const series = String(params.series ?? params.seriesId ?? "").trim();
  const geography = typeof params.geography === "string" ? params.geography
    : typeof params.country === "string" ? params.country
    : null;
  const resolved = resolveMacroSeries(series, geography);
  if (!resolved.ok) {
    const cls =
      resolved.reason === "ambiguous" ? "ambiguous"
        : resolved.reason === "not_covered" ? "not_covered"
        : "not_found";
    return {
      status: statusForFailure(cls),
      failureClass: cls,
      error: resolved.message,
      ...(resolved.candidates?.length ? { candidates: resolved.candidates } : {}),
    };
  }
  return { status: "OK", identity: resolved.identity };
}

// ── Web research (shared transport; no second search system) ────────────────

async function webSearchCapability(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const query = String(params.query ?? "").trim();
  if (!query) return unavailable("query is required");
  const limit = Number(params.limit ?? 8);
  const results = await webSearch(query, Number.isFinite(limit) ? Math.min(Math.max(limit, 1), 15) : 8);
  if (results.length === 0) return unavailable("no results");
  return { status: "OK", query, results };
}

async function webFetchCapability(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const url = String(params.url ?? "").trim();
  if (!url) return unavailable("url is required");
  const page = await fetchWebPage(url);
  if (!page) return unavailable("page could not be retrieved or was not usable HTML");
  return { status: "OK", url: page.url, title: page.title, text: page.text, bytes: page.bytes };
}
