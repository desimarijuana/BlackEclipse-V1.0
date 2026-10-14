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
import { fetchCryptoQuote } from "@/lib/scraper/fetchers/crypto";
import { normalizeEconomicSeries, sortByDate } from "@/lib/economics/fetch";
import { getSource } from "@/lib/economics/sources";
import { searchWeb, fetchWebPageDetailed } from "@/lib/web-research";
import { imageSearchCapability } from "@/lib/harness/data-bridge-images";
import { resolveCustomSearchProvider, describeDiagnostics } from "@/lib/harness/web-provider-resolve";
import {
  resolveSearchProviders,
} from "@/lib/web-search";
import { resolveMcpSecret } from "@/lib/harness/mcp-secrets";
import { fetchSecCompanyFacts } from "@/lib/fundamentals/providers/sec-edgar";
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
import { isCovered, coverageFor } from "@/lib/harness/coverage";
import {
  NON_DATA_CAPABILITIES,
} from "@/lib/harness/health-key";
import { resolveMacroSeries } from "@/lib/harness/macro-identity";
import { MARKET_FULL_NAME, resolveMarketId, splitExchangeSuffix } from "@/lib/markets";
import { unavailable, unavailableClass } from "@/lib/harness/data-bridge-result";
import { capabilityMatrix, providerKeyStatus, researchHealth } from "@/lib/harness/data-bridge-health";
import {
  videoSearchCapability,
  playlistSearchCapability,
  videoMetadataCapability,
  transcriptFetchCapability,
  courseSearchCapability,
  githubSearchCapability,
  structuredConnectorCapability,
} from "@/lib/harness/data-bridge-education";
import { fetchHistorySeriesFallback } from "@/lib/harness/data-bridge-history";
import {
  liveCompanyProfile,
  readCachedStatements,
  staleStatementsResult,
  type StaleStatements,
} from "@/lib/harness/data-bridge-statements";
import {
  coveringRangeFor,
  timestampWithinWindow,
  windowBounds,
} from "@/lib/scraper/yahoo-chart";
import type { DataCapability } from "./types";

// The result shape lives in `data-bridge-types.ts` (shared with the health
// ledger) and is re-exported here for existing importers.
export type { DataBridgeResult } from "@/lib/harness/data-bridge-types";
import type { DataBridgeResult } from "@/lib/harness/data-bridge-types";
import {
  recordCapabilityHealth,
  sourceHealth,
  coverageCapability,
  routeProbe,
} from "@/lib/harness/health-ledger";

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
    forwardPE: number | null;
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
  const rawSymbol = symbol.trim().toUpperCase();
  // A user very often types the global exchange suffix (`2330.TW`, `005930.KS`)
  // while the vault stores the BARE local code (`2330`). Split a recognised
  // suffix into an implied market, and query the vault for BOTH forms so an
  // instrument stored either way resolves. An unknown suffix is left intact.
  const split = splitExchangeSuffix(rawSymbol);
  const rawMarket =
    typeof rawMarketInput === "string" && rawMarketInput.trim() ? rawMarketInput.trim() : split.market;
  const sym = split.symbol.trim().toUpperCase();

  // A KNOWN venue we have no source for (a recognised derivatives exchange) is
  // NOT_COVERED — the caller named a real venue, so it is neither "unknown" nor
  // ambiguous. Checked before the vault lookup so it never reads as not_found.
  if (rawMarket) {
    const known = resolveMarketId(rawMarket);
    if (known && !isCovered(known, "equity") && coverageFor(known)?.assetClasses.length === 0) {
      return {
        ok: false,
        failure: {
          ok: false,
          reason: "not_covered",
          message: `No data source covers venue "${rawMarket}".`,
        },
      };
    }
  }

  const symbolsToTry = sym === rawSymbol ? [sym] : [sym, rawSymbol];
  const rows = await prisma.asset.findMany({
    where: { symbol: { in: symbolsToTry } },
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

  // Equity/fund: resolve through the vault master (the shared gate). A vault
  // MISS for a KNOWN, covered market is not terminal — the live provider can
  // still quote an instrument outside the committed universe (the vault is a
  // cache, not a precondition; the same rule `financial_statements` follows).
  const resolved = await resolveVaultInstrument(symbol, rawMarket, false);
  if (!resolved.ok) {
    const fallback = statementIdentityFallback(symbol, rawMarket, resolved.failure);
    if (!fallback) return resolved;
    return { ok: true, asset: null, identity: fallback };
  }
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
  not_covered: "not_covered",
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

/**
 * Build a best-effort statement identity when the vault has NO row but the
 * market is known and covered (Harness closeout Phase 4.4). Statements resolve
 * through the provider chain with the vault as a CACHE, so a vault miss is not a
 * hard failure. Returns null for a genuinely unresolvable request (unknown
 * venue, ambiguous bare ticker, uncovered venue) so the honest identity failure
 * still stands.
 */
function statementIdentityFallback(
  symbol: string,
  rawMarket: unknown,
  failure: IdentityFailure,
): InstrumentIdentity | null {
  // Only the "not in the vault" reason is recoverable here; a not_covered venue,
  // an unknown market or an ambiguous bare ticker must stay an identity failure.
  if (failure.reason !== "not_found") return null;
  const market = resolveMarketId(
    typeof rawMarket === "string" && rawMarket.trim() ? rawMarket.trim() : "",
  );
  if (!market) return null;
  if (!isCovered(market, "equity")) return null;
  const entry = coverageFor(market);
  if (!entry) return null;
  return {
    market,
    symbol: symbol.trim().toUpperCase(),
    currency: entry.currency || "USD",
    assetClass: "equity",
    securityType: null,
    name: null,
  };
}

/**
 * Record a live-provider outcome into SourceHealth, so `get_source_health` is
 * populated (C3/#7). Health is keyed per (source × market × asset-class) using
 * the `symbol` column for the asset-class label and the wildcard for the rest —
 * no schema change to the committed DB. Best-effort: a health write never
 * affects the answer.
 */
/**
 * Encode the capability + probe-kind dimensions into the `symbol` column so
 * health can be keyed per-capability WITHOUT a schema change to the committed
 * DB. Format: `<assetClass>#<capability>[!fixture]`. A legacy row with no `#`
 * is treated as the `quote` capability from a live probe. `assetClass` values
 * never contain `#` or `!`, so the split is unambiguous.
 */
export async function fetchCapability(
  capability: DataCapability,
  params: Record<string, unknown>
): Promise<DataBridgeResult> {
  const result = await dispatchCapability(capability, params);
  // ONE instrumentation seam: every data-fetching capability records here, so
  // every route lands in the same ledger via the same canonical key. Best-effort;
  // a health failure never fails a data request. Introspection routes are excluded.
  if (!NON_DATA_CAPABILITIES.has(capability)) {
    void recordCapabilityHealth(capability, params, result);
  }
  return result;
}

async function dispatchCapability(
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
    case "sec_filings":
      return secFilings(params);
    case "news":
      return news(params);
    case "source_health":
      return sourceHealth(params);
    case "research_health":
      return researchHealth();
    case "route_probe":
      return routeProbe(params);
    case "coverage":
      return Promise.resolve(coverageCapability());
    case "capability_matrix":
      return capabilityMatrix();
    case "provider_key_status":
      return providerKeyStatus(params);
    case "live_quote":
      return liveQuote(params);
    case "price_history":
      return priceHistory(params);
    case "crypto_market_data":
      return cryptoMarketData(params);
    case "macro_series":
      return macroSeries(params);
    case "macro_resolve":
      return Promise.resolve(macroResolve(params));
    case "web_search":
      return webSearchCapability(params);
    case "web_fetch":
      return webFetchCapability(params);
    case "academic_search":
      return structuredConnectorCapability("academic", params);
    case "news_search":
      return structuredConnectorCapability("news", params);
    case "image_search":
      return imageSearchCapability(params);
    case "video_search":
      return videoSearchCapability(params);
    case "playlist_search":
      return playlistSearchCapability(params);
    case "video_metadata":
      return videoMetadataCapability(params);
    case "transcript_fetch":
      return transcriptFetchCapability(params);
    case "course_search":
      return courseSearchCapability(params);
    case "github_search":
      return githubSearchCapability(params);
    case "mcp_secret_resolve":
      return mcpSecretResolve(params);
    case "mcp_oauth_token_get":
      return mcpOauthTokenGet(params);
    case "mcp_oauth_token_set":
      return mcpOauthTokenSet(params);
    case "mcp_oauth_token_clear":
      return mcpOauthTokenClear(params);
    case "market_data": // provider adapters; routing/fallback/health live in Python
      return (await import("./market/bridge")).fetchMarketData(params);
    case "market_stream_config":
      return (await import("./market/stream-config")).marketStreamConfig(params);
    case "world_events": return (await import("./world-events")).worldEvents(params);
    case "response_contract": // schema + validation for eclipse-response blocks (model read-back)
      return (await import("./response-bridge")).responseContractCapability(params);
    case "web_collect": // bounded page → records (SSRF-hardened + cheerio; R3-04)
      return (await import("./data-bridge-collect")).webCollectCapability(params);
    default:
      return unavailable(`Unknown capability: ${String(capability)}`);
  }
}

/**
 * Resolve a NAMED MCP secret to its value for the Python runtime — the ONLY
 * consumer of a secret value. This capability is reachable only through the
 * authenticated, read-only bridge (never a browser route); the value is returned
 * to the runtime so it can spawn an MCP child process and is never persisted.
 */
async function mcpSecretResolve(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const name = String(params.name ?? "");
  const value = await resolveMcpSecret(name);
  if (value === null) return unavailable(`unknown or unreadable MCP secret ${name}`);
  return { status: "OK", value };
}

// MCP OAuth tokens live in the SAME encrypted vault tier as secrets, under a
// separate key, referenced by server id. Values never cross to a browser; the
// Python runtime reads/writes them over this authenticated bridge.
async function mcpOauthTokenGet(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const { getOauthToken } = await import("./mcp-oauth-store");
  const token = await getOauthToken(String(params.serverId ?? ""));
  return { status: "OK", token: token ?? null };
}

async function mcpOauthTokenSet(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const { saveOauthToken } = await import("./mcp-oauth-store");
  await saveOauthToken(String(params.serverId ?? ""), {
    accessToken: String(params.accessToken ?? ""),
    tokenType: params.tokenType ? String(params.tokenType) : undefined,
    refreshToken: params.refreshToken ? String(params.refreshToken) : undefined,
    expiresAt: typeof params.expiresAt === "number" ? params.expiresAt : undefined,
    scope: params.scope ? String(params.scope) : undefined,
    clientId: params.clientId ? String(params.clientId) : undefined,
    issuer: params.issuer ? String(params.issuer) : undefined,
  });
  return { status: "OK" };
}

async function mcpOauthTokenClear(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const { clearOauthToken } = await import("./mcp-oauth-store");
  const removed = await clearOauthToken(String(params.serverId ?? ""));
  return { status: "OK", removed };
}

async function marketSnapshot(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const symbol = String(params.symbol ?? "").trim().toUpperCase();
  if (!symbol) return unavailableClass("invalid_request", "symbol is required");

  // Shared identity gate — the SAME one live_quote uses. No US default; an
  // unqualified multi-listed ticker is AMBIGUOUS, never silently US.
  const resolved = await resolveVaultInstrument(symbol, params.market, false);

  // A vault MISS is not a hard failure: the live provider may have the
  // instrument (many symbols are outside the committed universe). Only an
  // AMBIGUOUS or uncovered request is terminal. This is the same rule
  // `financial_statements` already follows — the vault is a cache, not a
  // precondition.
  if (!resolved.ok) {
    const recoverable = resolved.failure.reason === "not_found";
    if (!recoverable) return identityFailureResult(resolved.failure);
    const live = await liveQuote(params);
    if (live.status !== "OK") return identityFailureResult(resolved.failure);
    // The live quote carries a verified identity + price; expose it as a
    // snapshot with no stored profile and an explicit live observation time.
    return {
      status: "OK",
      symbol: live.symbol ?? symbol,
      name: null,
      sector: null,
      industry: null,
      securityType: live.securityType ?? null,
      assetClass: live.assetClass ?? null,
      country: live.market ?? null,
      market: live.market ?? null,
      exchange: live.exchange ?? null,
      mic: live.mic ?? null,
      currency: live.currency ?? null,
      instrumentId: live.instrumentId ?? null,
      priceSource: live.provider ?? null,
      updatedAt: live.observationTime ?? null,
      observationTime: live.observationTime ?? null,
      observationSource: live.observationSource ?? "unknown",
      price: live.price ?? null,
      profileSource: "none",
      served: "live",
    };
  }

  const { identity, asset } = resolved;

  // The vault may resolve the identity but hold no row (a symbol outside the
  // committed universe), or hold a row with no stored price. Either way a live
  // quote can still answer, so the snapshot is not vault-only.
  if (!asset || !asset.price) {
    const live = await liveQuote(params);
    if (live.status === "OK") {
      return {
        status: "OK",
        symbol: identity.symbol,
        name: asset?.name ?? null,
        sector: asset?.sector ?? null,
        industry: asset?.industry ?? null,
        securityType: asset?.securityType ?? live.securityType ?? null,
        assetClass: identity.assetClass ?? live.assetClass ?? asset?.assetClass ?? null,
        country: identity.market,
        market: identity.market,
        exchange: identity.exchange ?? asset?.market.exchange ?? live.exchange ?? null,
        mic: identity.mic ?? null,
        currency: identity.currency ?? live.currency ?? null,
        instrumentId: `${identity.market}:${identity.symbol}`,
        priceSource: live.provider ?? null,
        updatedAt: live.observationTime ?? null,
        observationTime: live.observationTime ?? null,
        observationSource: live.observationSource ?? "unknown",
        price: live.price ?? null,
        profileSource: asset ? "JDDS" : "none",
        served: "live",
      };
    }
  }

  if (!asset) return identityFailureResult({ ok: false, reason: "not_found", message: `${symbol} not found in JDdS and no live provider answered.` });

  return {
    status: "OK",
    symbol: identity.symbol,
    name: asset.name,
    sector: asset.sector,
    industry: asset.industry,
    securityType: asset.securityType,
    assetClass: identity.assetClass ?? asset.assetClass,
    country: identity.market,
    market: identity.market,
    exchange: identity.exchange ?? asset.market.exchange,
    mic: identity.mic ?? null,
    currency: identity.currency,
    instrumentId: `${identity.market}:${identity.symbol}`,
    priceSource: asset.price?.source ?? null,
    updatedAt: asset.price?.updatedAt?.toISOString() ?? null,
    // Phase 13: the observation's own time and how it was obtained. The vault
    // writes the row when it fetches, so its only timestamp is a SNAPSHOT WRITE —
    // never presented as a live as-of. `cadenceSeconds` stays as a HINT; the
    // runtime decides eligibility from the observation time.
    observationTime: asset.price?.updatedAt?.toISOString() ?? null,
    observationSource: "snapshot_write",
    // The vault is refreshed on a scraper schedule, not tick-by-tick.
    cadenceSeconds: 24 * 60 * 60,
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

  // Same shared identity gate as market_snapshot/live_quote. A vault miss is NOT
  // a hard failure: the provider pipeline (SEC → FMP → Yahoo) can still answer,
  // exactly as `financial_statements` does. Only a genuinely unresolvable request
  // (unknown venue, ambiguous bare ticker, uncovered venue) stays an identity
  // failure.
  const resolved = await resolveVaultInstrument(symbol, params.market, false);
  let identity: InstrumentIdentity;
  let asset: VaultAsset | null = null;
  if (resolved.ok) {
    identity = resolved.identity;
    asset = resolved.asset;
  } else {
    const fallback = statementIdentityFallback(symbol, params.market, resolved.failure);
    if (!fallback) return identityFailureResult(resolved.failure);
    identity = fallback;
  }

  // The profile is a live-verifiable fact, not a vault-only one. When the vault
  // has no row or lacks sector/industry/name, enrich from the existing
  // fundamentals provider pipeline (SEC/FMP/Yahoo) — the SAME service the
  // Fundamentals page uses. Never fabricate; a missing field stays null and is
  // reported as `null`, not guessed.
  const vaultHasProfile = Boolean(asset && (asset.sector || asset.industry || asset.name));
  const needLive = !vaultHasProfile || params.refresh === true;
  let liveProfile: Awaited<ReturnType<typeof liveCompanyProfile>> = null;
  if (needLive) {
    liveProfile = await liveCompanyProfile(identity.symbol, identity.market);
  }

  const name = asset?.name ?? liveProfile?.name ?? null;
  const sector = asset?.sector ?? liveProfile?.sector ?? null;
  const industry = asset?.industry ?? liveProfile?.industry ?? null;
  const profileSource = asset && (asset.sector || asset.industry || asset.name)
    ? "JDDS"
    : liveProfile
      ? "provider"
      : "JDDS";

  return {
    status: "OK",
    symbol: identity.symbol,
    name,
    sector,
    industry,
    securityType: asset?.securityType ?? null,
    assetClass: identity.assetClass ?? asset?.assetClass ?? null,
    market: identity.market,
    country: identity.market ?? liveProfile?.country ?? null,
    exchange: identity.exchange ?? asset?.market?.exchange ?? liveProfile?.exchange ?? null,
    mic: identity.mic ?? null,
    currency: identity.currency ?? liveProfile?.currency ?? null,
    instrumentId: `${identity.market}:${identity.symbol}`,
    price: asset?.price?.price ?? null,
    // Provenance for the profile fields: vault or a live provider. Honest about
    // where the profile came from so a consumer never assumes the vault answered.
    profileSource,
    // Valuation ratios get their own provenance: the LIVE provider values when a
    // company snapshot was fetched this call, otherwise the vault's saved ratios
    // with their as-of. A live P/E therefore has a route (refresh), and a saved
    // one is never disguised as current (DATA-1).
    valuation: liveProfile
      ? {
          peRatio: liveProfile.trailingPE,
          forwardPE: liveProfile.forwardPE,
          provenance: "LIVE",
          source: liveProfile.valuationSource,
          asOf: liveProfile.valuationAsOf,
        }
      : asset?.price
        ? {
            peRatio: asset.price.peRatio ?? null,
            forwardPE: asset.price.forwardPE ?? null,
            provenance: "JDDS",
            source: asset.price.source ?? null,
            asOf: asset.price.updatedAt ? new Date(asset.price.updatedAt).toISOString() : null,
          }
        : null,
  };
}

/**
 * Financial statements. Served from the PERSISTED FundamentalsCache snapshot —
 * parsed once, keyed by (symbol, market), with its source + retrieval timestamp —
 * and, when the vault has none for a market, from the EXISTING fundamentals
 * provider pipeline (SEC → FMP → yfinance), which fetches and caches live. This
 * is the same service the Fundamentals page uses; there is no second statement
 * pipeline, and no non-US statement route is silently absent just because the
 * committed snapshot lacks that market.
 *
 * `refresh: true` forces a provider refresh; normal reads still try the vault
 * first so repeated queries stay deterministic.
 */
async function financialStatements(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const symbol = String(params.symbol ?? "").trim().toUpperCase();
  if (!symbol) return unavailableClass("invalid_request", "symbol is required");

  // Statements resolve through the PROVIDER CHAIN (SEC → FMP → yfinance) with the
  // vault as a CACHE, not a precondition (Harness closeout Phase 4.4). A vault
  // miss must not become an identity failure: the vault identity gate is still
  // consulted for a verified market/symbol, but when the ONLY reason it failed is
  // that no vault row exists (and the market is known/covered), we build a
  // best-effort identity and let the provider chain answer — or return `no_data`.
  const resolved = await resolveVaultInstrument(symbol, params.market, false);
  let identity: InstrumentIdentity;
  if (resolved.ok) {
    identity = resolved.identity;
  } else {
    const fallback = statementIdentityFallback(symbol, params.market, resolved.failure);
    if (!fallback) return identityFailureResult(resolved.failure);
    identity = fallback;
  }

  // Statements are cached, but a cache is only useful while it is CURRENT: a
  // FY2018/FY2019 payload was being served indefinitely with a fresh `updatedAt`
  // (the row's timestamp refreshes on any write while the VALUE stays ancient).
  // Past the cadence the provider chain is tried first; if it cannot answer, the
  // persisted snapshot is still served — with its age stated, never disguised as
  // current. The shaping lives in `data-bridge-statements.ts` (size ratchet).
  let staleCached: StaleStatements | undefined;
  const cached = await prisma.fundamentalsCache.findUnique({
    where: { symbol_market: { symbol: identity.symbol, market: identity.market } },
  });
  if (cached) {
    const read = readCachedStatements(cached, identity, params.refresh === true);
    if (read.parseError) return read.parseError;
    if (read.fresh) return read.fresh;
    staleCached = read.stale;
  }

  // Live provider fallback: the existing fundamentals service (SEC/FMP/yfinance),
  // which persists its result to FundamentalsCache for subsequent reads.
  try {
    const { getFundamentals } = await import("@/lib/fundamentals");
    const snapshot = await getFundamentals(identity.symbol, identity.market, {
      force: params.refresh === true || staleCached !== undefined,
    });
    if (!snapshot || snapshot.periods.length === 0) {
      if (staleCached) return staleStatementsResult(staleCached);
      return unavailableClass(
        "no_data",
        `no financial statements available for ${identity.symbol} (${identity.market}) ` +
          "from the vault or a configured provider (SEC/FMP/yfinance)",
      );
    }
    return {
      status: "OK",
      symbol: identity.symbol,
      market: identity.market,
      currency: snapshot.currency ?? identity.currency,
      instrumentId: `${identity.market}:${identity.symbol}`,
      provider: snapshot.primarySource,
      retrievedAt: snapshot.retrievedAt,
      statementSource: snapshot.primarySource,
      provenance: snapshot.provenance,
      assetClass: identity.assetClass,
      periods: snapshot.periods,
      // The cache now holds this payload; say the read came out fresh.
      cacheAgeDays: 0,
    };
  } catch (err) {
    if (staleCached) return staleStatementsResult(staleCached);
    return unavailableClass(
      "source_failure",
      `live statement fetch failed for ${identity.symbol}: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
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
      const outcome = await searchWeb(`${query} news`);
      if (outcome.results.length > 0) {
        return {
          status: "OK",
          sourceKind: "web",
          searchProvider: outcome.provider,
          diagnostics: outcome.diagnostics,
          items: outcome.results.slice(0, 10).map((r) => ({
            source: extractHostname(r.url),
            headline: r.title,
            summary: r.snippet,
            sentiment: null,
            url: r.url,
            timestamp: r.publishedAt ?? null,
          })),
        };
      }
      // The search transport FAILED (not merely empty): that is a source failure,
      // never a false "no news".
      if (outcome.diagnostics.some((d) => d.normalizedStatus === "failed")) {
        return unavailableClass(
          "source_failure",
          `news vault empty and web search failed: ${describeDiagnostics(outcome.diagnostics)}`,
        );
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


// ── Live structured providers (Phase 2) ─────────────────────────────────────
// Reuse the existing scraper fallback chain and Yahoo bridge — NOT a new
// market-data system. The Python retrieval layer decides *when* to call these.

async function liveQuote(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const symbol = String(params.symbol ?? "").trim().toUpperCase();
  if (!symbol) return unavailableClass("invalid_request", "symbol is required");
  const rawMarket = params.market;

  const resolved = await resolveAnyInstrument(symbol, rawMarket, termsFromParams(params));
  if (!resolved.ok) return identityFailureResult(resolved.failure);
  const { identity, asset } = resolved;
  // FX/crypto have no vault row: their quote is served live. Equities/funds
  // resolve a stored asset (the price may still be a cached scrape).
  const fromVault = asset !== null;

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
      // failure is `source_failure`. Never conflate the two (B2). Health is
      // recorded once at the `fetchCapability` boundary (all capabilities share
      // that one seam), so this function does NOT record its own outcome.
      const cls: FailureClass =
        result.status === "network_error" || result.status === "timeout"
          ? "source_failure"
          : "no_data";
      return {
        ...unavailableClass(cls, result.error),
        // Tell the boundary recorder the route that was attempted even though the
        // instrument/identity resolved and no OK fields exist to read.
        healthContext: {
          source: result.source ?? "scraper",
          market: identity.market,
          assetClass: identity.assetClass,
        },
      } as DataBridgeResult;
    }

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
      // Provenance clarity: the vault holds equities/funds, so an FX/crypto
      // quote is served LIVE, not from the stored universe. Say so, and echo the
      // caller's own symbol form (`EURUSD`) rather than the provider's
      // (`EURUSD=X`) so the payload does not contradict the request.
      served: fromVault ? "vault" : "live",
      servedLive: !fromVault,
      requestedSymbol: symbol,
      providerSymbol: identity.symbol,
      // The provider's native publishing cadence (seconds). A structured quote
      // source publishes continuously; the vault may be a nightly snapshot. This
      // lets the layer say "delayed" instead of mislabelling a fresh delayed
      // quote as stale.
      cadenceSeconds: fromVault ? 24 * 60 * 60 : 60,
      price: {
        price: q.price,
        changePct: q.changePct,
        volume: q.volume ?? null,
        marketCap: q.marketCap ?? null,
        // A price is a number with a unit, not a bare number (A7).
        currency: identity.currency,
        units: identity.assetClass === "fx" || identity.assetClass === "crypto"
          ? "quote currency per base unit"
          : "per-share",
      },
      asOf: new Date().toISOString(),
      // Phase 13: the provider's own market as-of when it reports one, else
      // "unknown" — never the retrieval clock dressed up as a market time. The
      // scraper chain reports no market timestamp, so this is honestly unknown.
      observationTime: null,
      observationSource: "unknown" as const,
    };
  } catch (err) {
    return unavailableClass("source_failure", err instanceof Error ? err.message : "live quote failed");
  }
}

/**
 * Crypto market data for a base/quote pair, keyless.
 *
 * Crypto is NOT an equity: a bare `BTC` is ambiguous across quote currencies, and
 * a crypto ticker can collide with an equity. This capability resolves the crypto
 * pair via the SHARED identifier classifier (`classifyIdentifier`) and fetches
 * through the existing crypto connector transport — no second HTTP client. It
 * returns the resolved base/quote so provenance can prove which pair a price is
 * for, never a bare number.
 */
async function cryptoMarketData(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const raw = String(params.symbol ?? "").trim().toUpperCase();
  if (!raw) return unavailableClass("invalid_request", "crypto symbol is required");

  const classified = classifyIdentifier(raw);
  if (classified.kind !== "crypto") {
    // A non-crypto identifier reaching this capability is a caller error, not a
    // data miss. An FX pair or equity must never be priced as crypto.
    return unavailableClass("invalid_request", `${raw} is not a crypto asset`);
  }
  const { base } = classified;
  const quote = params.quoteCurrency
    ? String(params.quoteCurrency).trim().toUpperCase()
    : classified.quote;

  try {
    const result = await fetchCryptoQuote(base);
    if (result.status !== "ok" || !result.quote) {
      const cls: FailureClass =
        result.status === "timeout" || result.status === "network_error"
          ? "source_failure"
          : result.status === "blocked"
            ? "source_failure"
            : "no_data";
      return {
        ...unavailableClass(cls, result.error),
        healthContext: { source: "crypto", market: "CRYPTO", assetClass: "crypto" },
      } as DataBridgeResult;
    }
    const q = result.quote;
    return {
      status: "OK",
      symbol: base,
      base,
      quote,
      pair: `${base}-${quote}`,
      market: "CRYPTO",
      assetClass: "crypto",
      securityType: "crypto",
      currency: quote,
      provider: result.source ?? "crypto",
      contract: classified.contract,
      price: q.price,
      changePct: q.changePct,
      // `volume` keeps the connector's historical meaning (24h QUOTE notional).
      // The base-asset units and the explicit quote notional ride alongside so a
      // consumer can say which volume it means instead of conflating the two.
      volume: q.volume ?? null,
      volumeBase: q.volumeBase ?? null,
      volumeQuote: q.volumeQuote ?? q.volume ?? null,
      marketCap: null,
      high24h: null,
      low24h: null,
      asOf: new Date().toISOString(),
      observationTime: null,
      observationSource: "unknown" as const,
      cadenceSeconds: 60,
      units: "quote currency per base unit",
    };
  } catch (err) {
    return unavailableClass(
      "source_failure",
      err instanceof Error ? err.message : "crypto market data failed",
    );
  }
}

async function priceHistory(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const symbol = String(params.symbol ?? "").trim().toUpperCase();
  if (!symbol) return unavailableClass("invalid_request", "symbol is required");
  const rawMarket = params.market;
  const interval = String(params.period ?? params.interval ?? "1d").trim().toLowerCase();
  const start = typeof params.start === "string" ? params.start : undefined;
  const end = typeof params.end === "string" ? params.end : undefined;
  // An explicit window picks a covering range for the bridge transport and is
  // enforced on the rows below; without one the legacy `range` default applies.
  const bounds = windowBounds(start, end);
  const range = coveringRangeFor(
    bounds.startMs,
    bounds.endMs,
    String(params.range ?? "1y").trim().toLowerCase(),
  );

  // Identity first: history for an unresolvable market must not silently fetch a
  // bare ticker either.
  const resolved = await resolveAnyInstrument(symbol, rawMarket, termsFromParams(params));
  if (!resolved.ok) return identityFailureResult(resolved.failure);
  const { identity } = resolved;

  // TWO transports, one provider. First the batched Yahoo bridge (one python
  // process) that returns the whole OHLCV series; when the bridge is off or has
  // no series, the direct chart transport (`data-bridge-history`, the same one
  // `/api/price-history` uses) answers without Python. Both label the provider
  // `yfinance`; the `transport` field names the code path — never conflated.
  try {
    const data = await fetchYahooBatchRaw([identity.symbol], identity.market, interval, range);
    const key = Object.keys(data.history ?? {})[0];
    const allRows = key ? data.history?.[key] : undefined;
    // The bridge cannot express period1/period2, so the window is enforced here.
    const rows = Array.isArray(allRows)
      ? allRows.filter((r) => timestampWithinWindow(String(r?.date ?? r?.timestamp ?? ""), bounds))
      : undefined;
    if (Array.isArray(rows) && rows.length >= 2) {
      return {
        status: "OK",
        symbol: identity.symbol,
        market: identity.market,
        assetClass: identity.assetClass,
        currency: identity.currency,
        instrumentId: `${identity.market}:${identity.symbol}`,
        interval,
        provider: "yfinance",
        transport: "yfinance-bridge",
        ...(bounds.startMs != null ? { window: { start: start ?? null, end: end ?? null } } : {}),
        series: rows,
        asOf: rows[rows.length - 1]?.date ?? null,
      };
    }
  } catch {
    /* fall through to the direct transport */
  }
  const fallback = await fetchHistorySeriesFallback(identity.symbol, identity.market, range, interval, {
    start,
    end,
  });
  if (fallback) {
    return {
      status: "OK",
      symbol: identity.symbol,
      market: identity.market,
      assetClass: identity.assetClass,
      currency: identity.currency,
      instrumentId: `${identity.market}:${identity.symbol}`,
      interval,
      provider: fallback.provider,
      transport: fallback.transport,
      // The provider ticker the chart transport actually answered for (a thin
      // market may resolve through a fallback suffix) — provenance, not a guess.
      providerSymbol: fallback.ticker,
      ...(bounds.startMs != null ? { window: { start: start ?? null, end: end ?? null } } : {}),
      series: fallback.series,
      asOf: fallback.series[fallback.series.length - 1]?.date ?? null,
    };
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
      provider: effectiveSource,
      seriesKey: identity.id,
      seriesIdentity: identity,
      // Route identity for health: macro is its own asset class; the geography
      // (or `*` for a global series) is the market axis.
      assetClass: "macro",
      market: identity.geography ?? "*",
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
  if (!query) return unavailableClass("invalid_request", "query is required");
  const limit = Number(params.limit ?? 8);
  const bounded = Number.isFinite(limit) ? Math.min(Math.max(limit, 1), 15) : 8;
  const custom = await resolveCustomSearchProvider();
  const providers = await resolveSearchProviders(custom);
  const outcome = await searchWeb(query, bounded, providers);
  if (outcome.results.length === 0) {
    // Zero results is NOT the same as a transport failure: report the class and
    // the per-provider diagnostics so the caller can tell them apart.
    const allFailed = outcome.diagnostics.every((d) => d.normalizedStatus === "failed");
    return {
      status: "UNAVAILABLE",
      failureClass: allFailed ? "source_failure" : "no_data",
      error: allFailed
        ? `web search failed: ${describeDiagnostics(outcome.diagnostics)}`
        : "the search provider returned no results",
      diagnostics: outcome.diagnostics,
    };
  }
  return {
    status: "OK",
    query,
    provider: outcome.provider,
    diagnostics: outcome.diagnostics,
    results: outcome.results,
  };
}

async function webFetchCapability(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const url = String(params.url ?? "").trim();
  if (!url) return unavailableClass("invalid_request", "url is required");
  const outcome = await fetchWebPageDetailed(url);
  if (!outcome.page) {
    const d = outcome.diagnostic;
    const cls =
      d.category === "timeout" || d.category === "transport_error" || d.category === "http_error"
        ? "source_failure"
        : d.category === "invalid_request"
          ? "invalid_request"
          : "no_data";
    return {
      status: "UNAVAILABLE",
      failureClass: cls,
      // The category (javascript_only / paywalled / …) tells the caller how to escalate.
      error: d.detail || "page could not be retrieved",
      diagnostics: [d],
    };
  }
  return {
    status: "OK",
    url: outcome.page.url,
    title: outcome.page.title,
    text: outcome.page.text,
    bytes: outcome.page.bytes,
    extraction: outcome.page.extraction ?? null,
    language: outcome.page.language ?? null,
    diagnostics: [outcome.diagnostic],
  };
}

// ── SEC filings (independent primary-source route for US issuers) ────────────

/**
 * Direct SEC company-facts retrieval for a US issuer. This is an INDEPENDENT
 * route from the JDdS vault: it reaches `data.sec.gov` through the existing SEC
 * adapter (no second SEC implementation) and returns normalized statement periods
 * with filing provenance. The Python research layer normalizes this into
 * `financial_statements` objects; the JDdS vault remains a separate source.
 */
async function secFilings(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const symbol = String(params.symbol ?? "").trim().toUpperCase();
  if (!symbol) return unavailableClass("invalid_request", "symbol is required");
  const market = String(params.market ?? "US").trim().toUpperCase();
  if (market !== "US") {
    return unavailableClass(
      "not_covered",
      `SEC EDGAR covers US issuers only; "${market}" is not supported by this route`,
    );
  }
  // Shared identity gate — the SAME one financial_statements/live_quote use, so
  // a bare/two-listed ticker cannot be silently answered for the wrong issuer.
  const resolved = await resolveVaultInstrument(symbol, params.market, false);
  if (!resolved.ok) return identityFailureResult(resolved.failure);
  const { identity } = resolved;
  try {
    const facts = await fetchSecCompanyFacts(identity.symbol, identity.market);
    if (!facts || facts.periods.length === 0) {
      return unavailableClass("no_data", `SEC EDGAR returned no statement periods for ${identity.symbol}`);
    }
    return {
      status: "OK",
      symbol: identity.symbol,
      market: identity.market,
      currency: facts.currency ?? identity.currency ?? "USD",
      instrumentId: `${identity.market}:${identity.symbol}`,
      provider: facts.provider,
      retrievedAt: facts.retrievedAt,
      company: facts.company,
      periods: facts.periods,
      cik: null,
    };
  } catch (err) {
    return unavailableClass(
      "source_failure",
      `SEC EDGAR retrieval failed: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
}

