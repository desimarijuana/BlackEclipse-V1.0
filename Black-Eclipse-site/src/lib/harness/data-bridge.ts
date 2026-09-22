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
  missingContractTerms,
  classifyIdentifier,
  type ContractTerms,
  type IdentityFailure,
  type IdentityFailureReason,
  type InstrumentIdentity,
} from "@/lib/instrument-identity";
import { makeFailure, statusForFailure, type FailureClass } from "@/lib/harness/failure";
import { coverageSummary } from "@/lib/harness/coverage";
import { resolveMacroSeries } from "@/lib/harness/macro-identity";
import { MARKET_FULL_NAME } from "@/lib/markets";
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
// ── Shared instrument resolution (the ONE gate every tool routes through) ───
// Defects #1/#2 existed because resolution was patched per tool. This resolver
// is the single place a symbol becomes a verified identity; `market_snapshot`,
// `fundamentals`, `live_quote` and `price_history` all call it. No US default:
// an unqualified multi-listed ticker is AMBIGUOUS, an unknown venue is
// NOT_COVERED, FX/crypto resolve as their own asset classes.

interface VaultAsset {
  symbol: string;
  name: string;
  sector: string | null;
  industry: string | null;
  securityType: string | null;
  assetClass: string | null;
  market: { country: string; exchange: string };
  price?: {
    price: number;
    changePct: number;
    marketCap: number | null;
    volume: number | null;
    peRatio: number | null;
    source: string;
    updatedAt: Date;
  } | null;
}

type VaultResolution =
  | { ok: true; identity: InstrumentIdentity; asset: VaultAsset }
  | { ok: false; failure: IdentityFailure };

/** Resolve a symbol to a vault-backed instrument identity (equities, funds…). */
async function resolveVaultInstrument(
  symbol: string,
  rawMarketInput: unknown,
  requireRow = true,
): Promise<VaultResolution> {
  const sym = symbol.trim().toUpperCase();
  const rawMarket =
    typeof rawMarketInput === "string" && rawMarketInput.trim() ? rawMarketInput.trim() : null;

  const rows = await prisma.asset.findMany({
    where: { symbol: sym },
    include: { price: true, market: true },
  });

  const candidates = rows.map((r) => ({
    symbol: r.symbol,
    name: r.name,
    securityType: r.securityType,
    assetClass: r.assetClass,
    market: r.market.country,
    exchange: r.market.exchange,
  }));

  const result = resolveInstrument(sym, { raw: rawMarket }, candidates);
  if (!result.ok) {
    // A miss in the vault is only a hard failure when a row was required; some
    // callers (live_quote) can still try a live provider for a known market.
    return { ok: false, failure: result };
  }
  const row = rows.find(
    (r) => r.symbol === result.identity.symbol && r.market.country === result.identity.market,
  );
  if (!row && requireRow) {
    return {
      ok: false,
      failure: { ok: false, reason: "not_found", message: `${sym} not found in JDdS.` },
    };
  }
  // Enrich the identity with venue + MIC + name from the vault row.
  const identity: InstrumentIdentity = {
    ...result.identity,
    name: result.identity.name ?? row?.name ?? null,
    exchange: row?.market.exchange ?? null,
    mic: micForExchange(row?.market.exchange) ?? null,
  };
  return { ok: true, identity, asset: row as VaultAsset };
}

/**
 * Resolve ANY identifier — equity, FX pair, or crypto — to a full identity.
 * This is the entry point the live/quote paths use, so an FX or crypto symbol
 * never reaches an equity vault lookup and never inherits a country universe.
 */
async function resolveAnyInstrument(
  symbol: string,
  rawMarketInput: unknown,
  terms?: ContractTerms,
): Promise<
  | { ok: true; identity: InstrumentIdentity; asset: VaultAsset | null }
  | { ok: false; failure: IdentityFailure }
> {
  const kind = classifyIdentifier(symbol);
  const rawMarket =
    typeof rawMarketInput === "string" && rawMarketInput.trim() ? rawMarketInput.trim() : null;

  // FX pair: a self-identifying instrument. The venue is the FX market; the
  // identity carries base/quote so direction can never be confused.
  if (kind.kind === "fx") {
    return {
      ok: true,
      asset: null,
      identity: {
        market: "FX",
        symbol: kind.canonical,
        currency: kind.quote,
        assetClass: "fx",
        securityType: "Currency Pair",
        name: `${kind.base}/${kind.quote}`,
        quoteDirection: { base: kind.base, quote: kind.quote },
      },
    };
  }

  // Crypto pair (spot): its own asset class; carries the quote currency.
  if (kind.kind === "crypto") {
    return {
      ok: true,
      asset: null,
      identity: {
        market: "CRYPTO",
        symbol: kind.canonical,
        currency: kind.quote === "USDT" || kind.quote === "USDC" ? "USD" : kind.quote,
        assetClass: "crypto",
        securityType: "Crypto",
        name: `${kind.base}/${kind.quote} spot`,
        quoteDirection: { base: kind.base, quote: kind.quote },
        contract: "spot",
      },
    };
  }

  // Equity/fund: resolve through the vault master (the shared gate).
  const resolved = await resolveVaultInstrument(symbol, rawMarket, false);
  if (!resolved.ok) return resolved;
  // Enforce contract terms for derivatives / fixed income.
  const missing = missingContractTerms(resolved.identity.assetClass, terms);
  if (missing.length > 0) {
    return {
      ok: false,
      failure: {
        ok: false,
        reason: "terms_missing",
        message:
          `${resolved.identity.symbol} is a ${resolved.identity.assetClass} instrument; ` +
          `its value is undefined without ${missing.join(", ")}.`,
      },
    };
  }
  return resolved;
}

/** Best-effort ISO 10383 MIC for a JDdS exchange label (may cover several). */
function micForExchange(exchange?: string | null): string | null {
  if (!exchange) return null;
  const e = exchange.toUpperCase();
  if (e.includes("NYSE/NASDAQ")) return null; // multi-venue label: no single MIC
  if (e === "PSX") return "XPSX";
  if (e === "ASX") return "XASX";
  if (e === "LSE") return "XLON";
  if (e === "XETRA") return "XETR";
  if (e.includes("TOKYO")) return "XTKS";
  if (e === "HKEX") return "XHKG";
  if (e === "TSX") return "XTSE";
  if (e.includes("EURONEXT PARIS")) return "XPAR";
  if (e.includes("EURONEXT AMSTERDAM")) return "XAMS";
  if (e === "B3") return "BVMF";
  if (e === "SGX") return "XSES";
  if (e === "KRX") return "XKRX";
  if (e.includes("NSE/BSE")) return null;
  if (e === "TWSE") return "XTAI";
  if (e === "IDX") return "XIDX";
  if (e === "SET") return "XBKK";
  if (e === "BIST") return "XIST";
  if (e === "JSE") return "XJSE";
  if (e === "TADAWUL") return "XSAU";
  if (e === "BURSA MALAYSIA") return "XKLS";
  return null;
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
  // An unknown venue is a COVERAGE gap ("we don't support CME"), not an
  // ambiguity — the caller already named the venue. #4.
  market_unknown: "not_covered",
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

/**
 * Record a live-provider outcome into SourceHealth, so `get_source_health` is
 * populated (C3/#7). Health is keyed per (source × market × asset-class) using
 * the `symbol` column for the asset-class label and the wildcard for the rest —
 * no schema change to the committed DB. Best-effort: a health write never
 * affects the answer.
 */
async function recordHealth(
  source: string,
  market: string,
  assetClass: string,
  ok: boolean,
  error?: string,
): Promise<void> {
  try {
    const id = `${source}:${market}:${assetClass}`;
    await prisma.sourceHealth.upsert({
      where: { id },
      create: {
        id,
        source,
        market,
        symbol: assetClass,
        successCount: ok ? 1 : 0,
        failCount: ok ? 0 : 1,
        lastStatus: ok ? "ok" : "fail",
        lastError: ok ? null : error ?? null,
      },
      update: {
        successCount: { increment: ok ? 1 : 0 },
        failCount: { increment: ok ? 0 : 1 },
        lastStatus: ok ? "ok" : "fail",
        lastError: ok ? null : error ?? null,
      },
    });
  } catch {
    /* health is best-effort */
  }
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
    case "financial_statements":
      return financialStatements(params);
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
  if (!symbol) return unavailableClass("invalid_request", "symbol is required");

  // Shared identity gate — the SAME one live_quote uses. No US default; an
  // unqualified multi-listed ticker is AMBIGUOUS, never silently US.
  const resolved = await resolveVaultInstrument(symbol, params.market, true);
  if (!resolved.ok) return identityFailureResult(resolved.failure);
  const { identity, asset } = resolved;

  return {
    status: "OK",
    symbol: identity.symbol,
    name: asset.name,
    sector: asset.sector,
    industry: asset.industry,
    securityType: asset.securityType,
    assetClass: asset.assetClass,
    country: identity.market,
    market: identity.market,
    exchange: identity.exchange ?? asset.market.exchange,
    mic: identity.mic ?? null,
    currency: identity.currency,
    instrumentId: `${identity.market}:${identity.symbol}`,
    priceSource: asset.price?.source ?? null,
    updatedAt: asset.price?.updatedAt?.toISOString() ?? null,
    price: asset.price
      ? {
          price: asset.price.price,
          changePct: asset.price.changePct,
          marketCap: asset.price.marketCap,
          volume: asset.price.volume,
          peRatio: asset.price.peRatio,
          currency: identity.currency,
          units: "per-share",
        }
      : null,
  };
}

async function fundamentals(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const symbol = String(params.symbol ?? "").trim().toUpperCase();
  if (!symbol) return unavailableClass("invalid_request", "symbol is required");

  // Same shared identity gate as market_snapshot/live_quote. Previously this
  // tool had NO gate, so `fundamentals("BHP")` silently returned the US ADR.
  const resolved = await resolveVaultInstrument(symbol, params.market, true);
  if (!resolved.ok) return identityFailureResult(resolved.failure);
  const { identity, asset } = resolved;

  return {
    status: "OK",
    symbol: identity.symbol,
    name: asset.name,
    sector: asset.sector,
    industry: asset.industry,
    securityType: asset.securityType,
    assetClass: asset.assetClass,
    market: identity.market,
    country: identity.market,
    exchange: identity.exchange ?? asset.market.exchange,
    mic: identity.mic ?? null,
    currency: identity.currency,
    instrumentId: `${identity.market}:${identity.symbol}`,
    price: asset.price?.price ?? null,
  };
}

/**
 * Financial statements (#8). Served from the PERSISTED FundamentalsCache
 * snapshot — parsed once, keyed by (symbol, market), with its source +
 * retrieval timestamp. No read-time scrape, so repeat queries are
 * deterministic. When the vault has no persisted statements, UNAVAILABLE.
 */
async function financialStatements(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const symbol = String(params.symbol ?? "").trim().toUpperCase();
  if (!symbol) return unavailableClass("invalid_request", "symbol is required");

  const resolved = await resolveVaultInstrument(symbol, params.market, false);
  if (!resolved.ok) return identityFailureResult(resolved.failure);
  const { identity } = resolved;

  const cached = await prisma.fundamentalsCache.findUnique({
    where: { symbol_market: { symbol: identity.symbol, market: identity.market } },
  });
  if (!cached) {
    return unavailableClass(
      "not_found",
      `no persisted financial statements for ${identity.symbol} (${identity.market})`,
    );
  }
  let snapshot: Record<string, unknown>;
  try {
    snapshot = JSON.parse(cached.payload) as Record<string, unknown>;
  } catch {
    return unavailableClass("incomplete", "persisted statements could not be parsed");
  }
  const periods = Array.isArray(snapshot.periods) ? snapshot.periods : [];
  if (periods.length === 0) {
    // An empty shell is typed "absent", not returned as a value-shaped object.
    return unavailableClass("no_data", `persisted statements for ${identity.symbol} are empty`);
  }
  return {
    status: "OK",
    symbol: identity.symbol,
    market: identity.market,
    currency: identity.currency,
    instrumentId: `${identity.market}:${identity.symbol}`,
    provider: cached.primarySource,
    retrievedAt: cached.fetchedAt.toISOString(),
    statementSource: snapshot.primarySource ?? cached.primarySource,
    periods,
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
    by: ["source", "market", "symbol"],
    _sum: { successCount: true, failCount: true },
    _max: { lastStatus: true, updatedAt: true },
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
    const updated = r._max.updatedAt ? new Date(r._max.updatedAt).toISOString() : null;
    const ageSeconds = updated ? (Date.now() - Date.parse(updated)) / 1000 : null;
    return {
      source: r.source,
      market: r.market,
      // `*` is the legacy whole-market wildcard; a concrete label is the
      // asset class the health applies to.
      assetClass: r.symbol === "*" ? "*" : r.symbol,
      success,
      fail,
      total,
      lastStatus: r._max.lastStatus,
      health,
      successRate: total === 0 ? null : Math.round((success / total) * 100) / 100,
      updatedAt: updated,
      staleSeconds: ageSeconds,
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

  const resolved = await resolveAnyInstrument(symbol, rawMarket, termsFromParams(params));
  if (!resolved.ok) return identityFailureResult(resolved.failure);
  const { identity } = resolved;

  try {
    // FX/crypto are self-routing Yahoo tickers (`EURUSD=X`, `BTC-USD`); the
    // equity fallback chain (TradingView whole-market scans) does not cover
    // them, so quote them through the batched Yahoo bridge directly.
    let result: Awaited<ReturnType<typeof fetchQuoteWithFallback>>;
    if (identity.assetClass === "fx" || identity.assetClass === "crypto") {
      try {
        // The canonical ticker already encodes the pair (`EURUSD=X`, `BTC-USD`),
        // so route with a suffix-free market ("US") — passing "CRYPTO" would
        // append "-USD" again and double-suffix the symbol.
        const data = await fetchYahooBatchRaw([identity.symbol], "US");
        const ticker = Object.keys(data.quotes ?? {})[0];
        const q = ticker ? data.quotes?.[ticker] : undefined;
        result = q && q.price > 0
          ? {
              status: "ok",
              source: "yfinance",
              quote: {
                symbol: identity.symbol,
                price: q.price,
                changePct: q.changePct ?? 0,
                volume: q.volume ?? undefined,
                market: identity.market,
                currency: identity.currency,
              },
            }
          : { status: "empty", error: "no quote", source: "yfinance" };
      } catch (err) {
        result = {
          status: "network_error",
          error: err instanceof Error ? err.message : "fx/crypto quote failed",
          source: "yfinance",
        };
      }
    } else {
      result = await fetchQuoteWithFallback(identity.symbol, identity.market);
    }
    if (result.status !== "ok" || !result.quote) {
      // A provider that ran but returned nothing is `no_data`; a transport
      // failure is `source_failure`. Never conflate the two (B2).
      const cls: FailureClass =
        result.status === "network_error" || result.status === "timeout"
          ? "source_failure"
          : "no_data";
      void recordHealth(result.source ?? "scraper", identity.market, identity.assetClass, false, result.error);
      return unavailableClass(cls, result.error);
    }
    void recordHealth(result.source ?? "scraper", identity.market, identity.assetClass, true);

    // The provider must have answered for the SAME instrument. A currency or
    // venue disagreement means it priced something else — discard it rather
    // than return a confidently wrong number (A1/A2/A7). FX/crypto carry no
    // vault row, so identity verification is currency-based for them.
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
      exchange: identity.exchange ?? null,
      mic: identity.mic ?? null,
      currency: identity.currency,
      assetClass: identity.assetClass,
      securityType: identity.securityType ?? null,
      quoteDirection: identity.quoteDirection ?? null,
      contract: identity.contract ?? null,
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
  if (!symbol) return unavailableClass("invalid_request", "symbol is required");
  const rawMarket = params.market;
  const range = String(params.range ?? "1y").trim().toLowerCase();
  const interval = String(params.period ?? params.interval ?? "1d").trim().toLowerCase();

  // Identity first: history for an unresolvable market must not silently fetch a
  // bare ticker either.
  const resolved = await resolveAnyInstrument(symbol, rawMarket, termsFromParams(params));
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
    const ascending = sortByDate(normalizeEconomicSeries(raw, effectiveSource));
    if (ascending.length === 0) return unavailableClass("no_data", `macro source ${effectiveSource} returned no observations`);
    // Newest-first: a caller reading row 0 as "current" must get the LATEST
    // observation, not a 17-year-old first point (#3).
    const rows = [...ascending].reverse();
    return {
      status: "OK",
      source: effectiveSource,
      seriesKey: identity.id,
      seriesIdentity: identity,
      // A rate/level without a unit is not a number (#3).
      units: identity.unit ?? null,
      currency: identity.currency ?? null,
      // Explicit as_of distinct from the series, so "current" is unambiguous.
      asOf: rows[0]?.date ?? null,
      oldest: rows[rows.length - 1]?.date ?? null,
      observations: rows.length,
      rows,
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
