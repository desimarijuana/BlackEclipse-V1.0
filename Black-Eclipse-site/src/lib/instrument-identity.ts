// ─── Canonical instrument identity ──────────────────────────────────────────
// A ticker string is NOT an instrument identity. Tickers are reused across
// venues, asset classes and issuers (`FFC` is both Fauji Fertilizer on PSX and
// a US closed-end fund; `PPL`, `MTL`, `AGL` each name four or five unrelated
// issuers in the committed universe). A bare ticker carries no currency, no
// venue, no asset class and no share class.
//
// This module defines the identity that MUST accompany any instrument data:
//
//   market     the canonical JDDS market id the instrument belongs to
//   symbol     the venue-local ticker (as stored in the instrument master)
//   currency   the denomination of the instrument's prices, in ISO 4217
//   securityType  equity / ETF / fund / debt / crypto / …, when known
//
// The rule the whole layer enforces:
//
//   * If a caller supplies a market qualifier, the resolved instrument MUST
//     belong to it. A result from another market is not an answer — it is an
//     AMBIGUOUS/UNAVAILABLE outcome.
//   * If no qualifier is supplied and the bare ticker maps to more than one
//     instrument, the request is AMBIGUOUS. We never pick a "best match".
//
// AMBIGUOUS and UNAVAILABLE are success states of this module; fabricating a
// plausible instrument is the failure.

import { resolveMarketId, currencyIsoFor, MARKET_FULL_NAME } from "./markets";

export type AssetClass =
  | "equity"
  | "etf"
  | "fund"
  | "debt"
  | "crypto"
  | "index"
  | "fx"
  | "commodity"
  | "derivative"
  | "other";

/**
 * Asset classes whose VALUE IS UNDEFINED without contract terms (A5/A6).
 * A derivative price without expiry/strike/right is meaningless; a bond yield
 * without maturity/coupon/seniority is meaningless. These must never be
 * returned as a bare number.
 */
export const TERMS_REQUIRED_CLASSES: ReadonlySet<AssetClass> = new Set<AssetClass>([
  "derivative",
  "debt",
]);

/**
 * Contract terms that identify a specific derivative / fixed-income instrument.
 * Each is optional in the type but required per asset class at resolution time.
 */
export interface ContractTerms {
  /** Derivatives: ISO date the contract expires. */
  expiry?: string;
  /** Futures: contract month (e.g. "2026-12"). */
  contractMonth?: string;
  /** Options: strike price. */
  strike?: number;
  /** Options: call or put. */
  right?: "call" | "put";
  /** Fixed income: ISO maturity date. */
  maturity?: string;
  /** Fixed income: coupon rate (percent). */
  coupon?: number;
  /** Fixed income: seniority (senior/subordinated/…). */
  seniority?: string;
}

/**
 * The terms that MUST be present for each terms-required asset class. Data, not
 * branching — a new derivative type adds a row here.
 */
const REQUIRED_TERMS: Partial<Record<AssetClass, (keyof ContractTerms)[]>> = {
  derivative: ["expiry"],
  debt: ["maturity"],
};

/**
 * Validate that a terms-required instrument carries enough to be priced.
 * Returns the missing term names (empty when satisfied or not required).
 */
export function missingContractTerms(assetClass: AssetClass, terms?: ContractTerms): (keyof ContractTerms)[] {
  const required = REQUIRED_TERMS[assetClass];
  if (!required) return [];
  const t = terms ?? {};
  return required.filter((k) => t[k] === undefined || t[k] === null || t[k] === "");
}

/** Maps a JDDS `securityType` / `assetClass` string to a coarse asset class. */
export function toAssetClass(securityType?: string | null, assetClass?: string | null): AssetClass {
  const t = `${securityType ?? ""} ${assetClass ?? ""}`.toLowerCase();
  if (/crypto|token|erc-20|bep-20|trc-20/.test(t)) return "crypto";
  if (/etf/.test(t)) return "etf";
  if (/mutual fund|closed-end|fund|reit|trust|modaraba/.test(t)) return "fund";
  if (/debt|bond|sukuk|national savings/.test(t)) return "debt";
  if (/stock|equity|common|preferred|adr|warrant|spl/.test(t)) return "equity";
  if (/index/.test(t)) return "index";
  if (/forex|fx/.test(t)) return "fx";
  if (/commodit/.test(t)) return "commodity";
  if (/future|option|derivative|swap/.test(t)) return "derivative";
  return "other";
}

/** A resolved, unambiguous instrument. */
export interface InstrumentIdentity {
  /** Canonical JDDS market id (country-level: "US", "PK", …). */
  market: string;
  /** Venue-local ticker exactly as the instrument master stores it. */
  symbol: string;
  /** ISO 4217 currency the instrument's prices are denominated in. */
  currency: string;
  /** Coarse asset class, when the master records one. */
  assetClass: AssetClass;
  /** Raw security type string, for the audit trail. */
  securityType?: string | null;
  /** Human-readable name, when known. */
  name?: string | null;
}

/**
 * Why an instrument could not be resolved to a single identity.
 *
 * - `market_unknown`   — the market/venue qualifier is not one we can honor.
 * - `not_found`        — the ticker is not in that market's universe.
 * - `ambiguous`        — no qualifier given and the ticker names >1 instrument.
 * - `currency_mismatch`— the provider answered for a different currency.
 * - `venue_mismatch`   — the provider answered for a different venue.
 * - `terms_missing`    — a derivative/fixed-income identity lacks contract terms.
 */
export type IdentityFailureReason =
  | "market_unknown"
  | "not_found"
  | "ambiguous"
  | "currency_mismatch"
  | "venue_mismatch"
  | "terms_missing";

export interface IdentityFailure {
  ok: false;
  reason: IdentityFailureReason;
  /** User-safe explanation. Never contains provider internals. */
  message: string;
  /** Candidate markets when the failure is `ambiguous`. */
  candidates?: string[];
}

export type IdentityResult = { ok: true; identity: InstrumentIdentity } | IdentityFailure;

/** A candidate row from the instrument master (the only fields identity needs). */
export interface InstrumentRow {
  symbol: string;
  market: string;
  name?: string | null;
  securityType?: string | null;
  assetClass?: string | null;
}

/** The market qualifier a caller supplied, before resolution. */
export interface MarketQualifier {
  /** Raw value the caller passed (e.g. "PSX", "PK", "Pakistan"). */
  raw?: string | null;
}

/**
 * Resolve one ticker + optional market qualifier against the instrument master.
 *
 * `rows` is the set of master rows sharing this ticker (the caller queries the
 * master by symbol; this function does not touch the database).
 *
 * This is the single decision point. It never guesses: an unknown qualifier, a
 * miss, or a multi-market bare ticker all return a typed failure.
 */
export function resolveInstrument(
  ticker: string,
  qualifier: MarketQualifier,
  rows: InstrumentRow[],
  terms?: ContractTerms,
): IdentityResult {
  const symbol = ticker.trim().toUpperCase();
  if (!symbol) {
    return { ok: false, reason: "not_found", message: "A ticker is required." };
  }

  const rawQualifier = qualifier.raw?.trim() ?? "";

  // 1. A qualifier was supplied: it MUST resolve to a known market and the
  //    instrument MUST belong to that market. Never fall through to a bare
  //    ticker when the qualifier cannot be honored.
  if (rawQualifier) {
    const market = resolveMarketId(rawQualifier);
    if (!market) {
      return {
        ok: false,
        reason: "market_unknown",
        message:
          `Unknown market/venue "${rawQualifier}". ` +
          "Refusing to resolve the bare ticker because that risks returning a " +
          "different instrument from another market.",
      };
    }
    const match = rows.find((r) => r.market === market);
    if (!match) {
      return {
        ok: false,
        reason: "not_found",
        message: `${symbol} is not in the ${MARKET_FULL_NAME[market] ?? market} universe.`,
      };
    }
    return finishIdentity(match, terms);
  }

  // 2. No qualifier: the bare ticker is only an identity when it is unique
  //    across the whole master. Otherwise it is ambiguous.
  const distinctMarkets = [...new Set(rows.map((r) => r.market))];
  if (rows.length === 0) {
    return { ok: false, reason: "not_found", message: `${symbol} is not in the instrument universe.` };
  }
  if (distinctMarkets.length > 1) {
    return {
      ok: false,
      reason: "ambiguous",
      message:
        `"${symbol}" matches ${distinctMarkets.length} different instruments ` +
        `(${distinctMarkets.join(", ")}). Specify the market.`,
      candidates: distinctMarkets,
    };
  }
  // Single market, but the same market can still hold more than one row for a
  // ticker (e.g. a share class); require exactly one.
  if (rows.length > 1) {
    return {
      ok: false,
      reason: "ambiguous",
      message: `"${symbol}" matches ${rows.length} instruments in ${distinctMarkets[0]}.`,
      candidates: distinctMarkets,
    };
  }
  return finishIdentity(rows[0], terms);
}

/** Attach the identity, enforcing contract terms for terms-required classes. */
function finishIdentity(row: InstrumentRow, terms?: ContractTerms): IdentityResult {
  const identity = toIdentity(row);
  const missing = missingContractTerms(identity.assetClass, terms);
  if (missing.length > 0) {
    return {
      ok: false,
      reason: "terms_missing",
      message:
        `${identity.symbol} is a ${identity.assetClass} instrument; its value is ` +
        `undefined without ${missing.join(", ")}. Provide the contract terms.`,
    };
  }
  return { ok: true, identity };
}

function toIdentity(row: InstrumentRow): InstrumentIdentity {
  return {
    market: row.market,
    symbol: row.symbol,
    currency: currencyIsoFor(row.market),
    assetClass: toAssetClass(row.securityType, row.assetClass),
    securityType: row.securityType ?? null,
    name: row.name ?? null,
  };
}

/**
 * Verify that a provider's answer actually belongs to the requested identity.
 *
 * The provider states the currency (or market) it priced; if that disagrees with
 * the resolved instrument, the answer is for a different instrument and MUST be
 * rejected. Absent provider metadata is NOT grounds for rejection — it is a
 * weaker answer, not a wrong one; callers should treat missing currency as
 * unverified rather than assume a mismatch.
 */
export function verifyProviderIdentity(
  identity: InstrumentIdentity,
  provider: { market?: string | null; currency?: string | null },
): IdentityResult {
  // Currency is part of the value (A7): a mismatch is a failure, not formatting.
  if (provider.currency && identity.currency && provider.currency !== identity.currency) {
    return {
      ok: false,
      reason: "currency_mismatch",
      message:
        `Provider priced this in ${provider.currency}, but ${identity.symbol} on ` +
        `${identity.market} is denominated in ${identity.currency}. ` +
        "Discarding the mismatched quote.",
    };
  }
  if (provider.market) {
    const providerMarket = resolveMarketId(provider.market);
    // A venue the provider names that we cannot map is itself a failure: we
    // cannot prove the answer belongs to the requested instrument.
    if (!providerMarket) {
      return {
        ok: false,
        reason: "venue_mismatch",
        message:
          `Provider answered for venue "${provider.market}", which could not be ` +
          `verified against ${identity.market}. Discarding the unverifiable quote.`,
      };
    }
    if (providerMarket !== identity.market) {
      return {
        ok: false,
        reason: "venue_mismatch",
        message:
          `Provider answered for market ${providerMarket}, but ${identity.symbol} ` +
          `was requested on ${identity.market}. Discarding the mismatched quote.`,
      };
    }
  }
  return { ok: true, identity };
}

/** A stable string key for an identity, for cache keys and logs. */
export function instrumentKey(identity: Pick<InstrumentIdentity, "market" | "symbol">): string {
  return `${identity.market}:${identity.symbol}`;
}
