// ── Statement cache freshness + live profile/valuation ──────────────────────
// Extracted from `data-bridge.ts` (the size ratchet named the
// statement/valuation block as the next split candidate). This is shaping plus
// the EXISTING fundamentals service call — no second provider pipeline.

import { unavailableClass } from "@/lib/harness/data-bridge/data-bridge-result";
import type { DataBridgeResult } from "@/lib/harness/data-bridge/data-bridge-types";

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
  /** The newest reported period end (not the fetch time). */
  periodEnd: string | null;
  /** How old that period end is, in calendar days. */
  periodAgeDays: number;
}

/**
 * Statement cache key version. Bump whenever the cache-key/freshness contract
 * changes, so a poisoned entry (e.g. FY2018 served as "latest") is not re-served.
 */
export const STATEMENT_CACHE_VERSION = 2;

/** Per-statement-type maximum age, calendar-aware. */
export const ANNUAL_STATEMENT_MAX_AGE_DAYS = 548; // 18 months
export const QUARTERLY_STATEMENT_MAX_AGE_DAYS = 150;

function periodEndOf(period: unknown): string | null {
  if (!period || typeof period !== "object") return null;
  const record = period as Record<string, unknown>;
  const value =
    record.endDate ?? record.periodEnd ?? record.date ?? record.fiscalDateEnding ?? record.end;
  return typeof value === "string" && value.length >= 10 ? value.slice(0, 10) : null;
}

function newestPeriodEnd(periods: unknown[]): string | null {
  const dates = periods.map(periodEndOf).filter((d): d is string => Boolean(d)).sort();
  return dates.length ? dates[dates.length - 1] : null;
}

function looksQuarterly(periods: unknown[]): boolean {
  const dates = periods.map(periodEndOf).filter((d): d is string => Boolean(d)).sort();
  if (dates.length < 2) {
    const p = periods.find((x) => x && typeof x === "object") as Record<string, unknown> | undefined;
    return Boolean(p && typeof p.period === "string" && /^Q/i.test(p.period));
  }
  const first = Date.parse(dates[0]);
  const last = Date.parse(dates[dates.length - 1]);
  if (!Number.isFinite(first) || !Number.isFinite(last) || dates.length < 2) return false;
  return (last - first) / (dates.length - 1) < 200 * 24 * 3600 * 1000;
}

export function statementMaxAgeDays(periods: unknown[]): number {
  return looksQuarterly(periods)
    ? QUARTERLY_STATEMENT_MAX_AGE_DAYS
    : ANNUAL_STATEMENT_MAX_AGE_DAYS;
}

/** Age of the newest reported period (never the cache write time). */
export function statementPeriodAge(periods: unknown[]): {
  periodEnd: string | null;
  periodAgeDays: number;
  maxAgeDays: number;
  stale: boolean;
} {
  const periodEnd = newestPeriodEnd(periods);
  const maxAgeDays = statementMaxAgeDays(periods);
  if (!periodEnd) return { periodEnd: null, periodAgeDays: 0, maxAgeDays, stale: false };
  const end = Date.parse(periodEnd);
  const ageDays = Number.isFinite(end)
    ? Math.max(0, Math.floor((Date.now() - end) / (24 * 3600 * 1000)))
    : 0;
  return { periodEnd, periodAgeDays: ageDays, maxAgeDays, stale: ageDays > maxAgeDays };
}

/**
 * The period-quality fields added to a statements payload. A provider can hand
 * back an ancient period with a fresh fetch timestamp; judge the PERIOD, not
 * the fetch, so an FY2018 payload is STALE and names its period end and age.
 */
export function statementPeriodFields(periods: unknown[]): Record<string, unknown> {
  const period = statementPeriodAge(periods);
  return {
    periodEnd: period.periodEnd,
    periodAgeDays: period.periodAgeDays,
    maxAgeDays: period.maxAgeDays,
    ...(period.stale
      ? { stale: true, qualityVerdict: "STALE", reasonCode: "DATA_STALE" }
      : {}),
  };
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
  const period = statementPeriodAge(periods);
  const cacheVersion = Number(snapshot.cacheVersion ?? 0);
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
    periodEnd: period.periodEnd,
    periodAgeDays: period.periodAgeDays,
    maxAgeDays: period.maxAgeDays,
  };
  // Fresh only when the CACHE KEY VERSION matches, the fetch is recent AND the
  // actual reported PERIOD is inside its cadence. A fresh fetch timestamp on an
  // FY2018 payload is exactly the defect this guards.
  if (cacheVersion === STATEMENT_CACHE_VERSION && ageMs <= STALE_STATEMENTS_MS
      && !period.stale && !refresh) {
    return { fresh: { status: "OK", ...body, provenance: "CACHED", cacheAgeDays: ageDays } };
  }
  return { stale: { ...body, ageDays, periodEnd: period.periodEnd, periodAgeDays: period.periodAgeDays } };
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
    periodEnd: stale.periodEnd,
    periodAgeDays: stale.periodAgeDays,
    qualityVerdict: "STALE",
    reasonCode: "DATA_STALE",
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
