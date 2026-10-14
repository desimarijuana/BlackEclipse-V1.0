// ── Statement cache freshness + live profile/valuation ──────────────────────
// Extracted from `data-bridge.ts` (the size ratchet named the
// statement/valuation block as the next split candidate). This is shaping plus
// the EXISTING fundamentals service call — no second provider pipeline.

import { unavailableClass } from "@/lib/harness/data-bridge-result";
import type { DataBridgeResult } from "@/lib/harness/data-bridge-types";

/** A persisted statements payload, kept for an honest age-labelled fallback. */
export interface StaleStatements {
  symbol: string;
  market: string;
  currency: string | null;
  instrumentId: string;
  assetClass: string | null;
  periods: unknown[];
  provider: string;
  retrievedAt: string;
  statementSource: string;
  ageDays: number;
}

/** Statements older than this are refreshed before being served. */
export const STALE_STATEMENTS_MS = 7 * 24 * 3600 * 1000;

export interface CachedStatementsRow {
  payload: string;
  primarySource: string;
  fetchedAt: Date;
}

export interface IdentityShape {
  symbol: string;
  market: string;
  currency: string;
  assetClass?: string | null;
}

/**
 * Read a persisted statements row. A payload within the cadence (and no forced
 * refresh) is served directly with its age; a stale payload is returned so the
 * caller can try the provider chain FIRST; an unparsable payload is an explicit
 * result, never silently a cache miss.
 */
export function readCachedStatements(
  row: CachedStatementsRow,
  identity: IdentityShape,
  refresh: boolean,
): { fresh?: DataBridgeResult; stale?: StaleStatements; parseError?: DataBridgeResult } {
  let snapshot: Record<string, unknown>;
  try {
    snapshot = JSON.parse(row.payload) as Record<string, unknown>;
  } catch {
    return { parseError: unavailableClass("incomplete", "persisted statements could not be parsed") };
  }
  const periods = Array.isArray(snapshot.periods) ? snapshot.periods : [];
  if (periods.length === 0) return {}; // an empty shell is a cache miss
  const ageMs = Date.now() - row.fetchedAt.getTime();
  const ageDays = Math.max(0, Math.round(ageMs / (24 * 3600 * 1000)));
  const body = {
    symbol: identity.symbol,
    market: identity.market,
    currency: identity.currency,
    instrumentId: `${identity.market}:${identity.symbol}`,
    provider: row.primarySource,
    retrievedAt: row.fetchedAt.toISOString(),
    statementSource: (snapshot.primarySource as string | undefined) ?? row.primarySource,
    assetClass: identity.assetClass ?? null,
    periods,
  };
  if (ageMs <= STALE_STATEMENTS_MS && !refresh) {
    return { fresh: { status: "OK", ...body, provenance: "CACHED", cacheAgeDays: ageDays } };
  }
  return { stale: { ...body, ageDays } };
}

/**
 * The honest fallback when the provider chain cannot answer: the persisted
 * payload with `stale: true` and its age — never disguised as current (a
 * FY2018/FY2019 snapshot was once served indefinitely).
 */
export function staleStatementsResult(stale: StaleStatements): DataBridgeResult {
  return {
    status: "OK",
    symbol: stale.symbol,
    market: stale.market,
    currency: stale.currency,
    instrumentId: stale.instrumentId,
    provider: stale.provider,
    retrievedAt: stale.retrievedAt,
    statementSource: stale.statementSource,
    provenance: "CACHED",
    stale: true,
    cacheAgeDays: stale.ageDays,
    periods: stale.periods,
  };
}

export interface LiveCompanyProfile {
  name: string | null;
  sector: string | null;
  industry: string | null;
  country: string | null;
  exchange: string | null;
  currency: string | null;
  trailingPE: number | null;
  forwardPE: number | null;
  valuationSource: string | null;
  valuationAsOf: string | null;
}

/**
 * The company profile + valuation ratios from the live provider pipeline
 * (SEC → FMP → Yahoo), or null when no provider can answer. Reuses the existing
 * fundamentals service — there is no second provider implementation here.
 */
export async function liveCompanyProfile(
  symbol: string,
  market: string,
): Promise<LiveCompanyProfile | null> {
  try {
    const { getFundamentals } = await import("@/lib/fundamentals");
    const snapshot = await getFundamentals(symbol, market);
    if (!snapshot) return null;
    const c = snapshot.company;
    const metrics = Array.isArray(snapshot.metrics) ? snapshot.metrics : [];
    const metric = (key: string) => metrics.find((m) => m.key === key);
    const pe = metric("pe");
    const forward = metric("forwardPE");
    return {
      name: c.name ?? null,
      sector: c.sector ?? null,
      industry: c.industry ?? null,
      country: c.country ?? null,
      exchange: c.exchange ?? null,
      currency: snapshot.currency ?? null,
      trailingPE: pe?.value ?? null,
      forwardPE: forward?.value ?? null,
      valuationSource: pe?.source ?? forward?.source ?? null,
      valuationAsOf: snapshot.retrievedAt ?? null,
    };
  } catch {
    return null;
  }
}
