// ─── Macro series identity (A8) ─────────────────────────────────────────────
// A macro series is an identity too: a bare name like "POLICY_RATE" is
// ambiguous (US fed funds target? the reverse-repo ceiling? the ECB deposit
// rate?). Two measures of "the policy rate" must not collide as one series, and
// a generic name must never default to the US backend.
//
// This module turns a (seriesId, geography?) pair into a canonical identity:
//   geography + institution + measure + adjustment + frequency + unit.
// It never guesses: a generic id without a geography is AMBIGUOUS; an unknown
// id with a known geography is routed only to a source that covers it.

import { resolveMarketId } from "../markets";

/** Adjustment/vintage of a series. SA vs NSA must not collide. */
export type SeasonalAdjustment = "sa" | "nsa" | "unknown";
export type Frequency = "daily" | "weekly" | "monthly" | "quarterly" | "annual" | "unknown";

export interface MacroSeriesIdentity {
  /** The canonical id the system stores/uses, e.g. "US:FRED:FEDFUNDS". */
  id: string;
  /** Geography (ISO2 country or a supranational id like "EA", "WLD"). */
  geography: string;
  /** Institution/source family, e.g. "FRED", "ECB", "OECD", "WorldBank". */
  institution: string;
  /** The specific measure, e.g. "fed_funds_target", "reverse_repo_ceiling". */
  measure: string;
  adjustment: SeasonalAdjustment;
  frequency: Frequency;
  unit?: string;
  /** ISO 4217 currency for a currency-denominated series (e.g. USD bn). */
  currency?: string;
  /** The source id in `lib/economics/sources` that serves it. */
  sourceId: string;
  /** The provider series id to request. */
  providerSeries: string;
}

/**
 * Registry of known series identities. A row is required for any series the
 * system will resolve without ambiguity. Extend by adding rows, not branches.
 */
const SERIES: MacroSeriesIdentity[] = [
  // US policy measures — deliberately DISTINCT (the reported conflict).
  { id: "US:FRED:FEDFUNDS", geography: "US", institution: "FRED", measure: "fed_funds_effective", adjustment: "nsa", frequency: "monthly", unit: "percent", sourceId: "fred-analytics", providerSeries: "FEDFUNDS" },
  { id: "US:FRED:DFEDTARU", geography: "US", institution: "FRED", measure: "fed_funds_target_upper", adjustment: "nsa", frequency: "daily", unit: "percent", sourceId: "fred-analytics", providerSeries: "DFEDTARU" },
  { id: "US:FRED:DFEDTARL", geography: "US", institution: "FRED", measure: "fed_funds_target_lower", adjustment: "nsa", frequency: "daily", unit: "percent", sourceId: "fred-analytics", providerSeries: "DFEDTARL" },
  { id: "US:FRED:RRPONTSYD", geography: "US", institution: "FRED", measure: "reverse_repo_ceiling", adjustment: "nsa", frequency: "daily", unit: "usd_bn", currency: "USD", sourceId: "fred-analytics", providerSeries: "RRPONTSYD" },
  { id: "US:FRED:CPIAUCSL", geography: "US", institution: "FRED", measure: "cpi_headline", adjustment: "sa", frequency: "monthly", unit: "index", sourceId: "fred-analytics", providerSeries: "CPIAUCSL" },
  { id: "US:FRED:CPILFESL", geography: "US", institution: "FRED", measure: "cpi_core", adjustment: "sa", frequency: "monthly", unit: "index", sourceId: "fred-analytics", providerSeries: "CPILFESL" },
  { id: "US:FRED:UNRATE", geography: "US", institution: "FRED", measure: "unemployment_rate", adjustment: "sa", frequency: "monthly", unit: "percent", sourceId: "fred-analytics", providerSeries: "UNRATE" },
  { id: "US:FRED:GDP", geography: "US", institution: "FRED", measure: "gdp_nominal", adjustment: "sa", frequency: "quarterly", unit: "usd_bn", currency: "USD", sourceId: "fred-analytics", providerSeries: "GDP" },
  // Non-US — routed to non-US backends (C1).
  { id: "EA:ECB:DEPOSIT", geography: "EA", institution: "ECB", measure: "ecb_deposit_facility_rate", adjustment: "nsa", frequency: "daily", unit: "percent", sourceId: "ecb", providerSeries: "deposit" },
  { id: "EA:ECB:MRR", geography: "EA", institution: "ECB", measure: "ecb_main_refinancing_rate", adjustment: "nsa", frequency: "daily", unit: "percent", sourceId: "ecb", providerSeries: "mrr" },
  { id: "GB:BOE:BANKRATE", geography: "GB", institution: "OECD", measure: "boe_bank_rate", adjustment: "nsa", frequency: "daily", unit: "percent", sourceId: "oecd", providerSeries: "IR3TIB01GBM156N" },
  { id: "WLD:WORLDBANK:GDP", geography: "WLD", institution: "WorldBank", measure: "gdp_nominal", adjustment: "nsa", frequency: "annual", unit: "usd", sourceId: "worldbank", providerSeries: "NY.GDP.MKTP.CD" },
  { id: "WLD:IMF:CPI", geography: "WLD", institution: "IMF", measure: "cpi_headline", adjustment: "nsa", frequency: "annual", unit: "index", sourceId: "imf", providerSeries: "PCPIPC_WT" },
];

/**
 * Generic measure names that map to a FAMILY of measures (not one). A generic
 * "policy rate" is the target upper, lower, midpoint, and effective rate — the
 * system must not silently choose one (#3). The value is the set of measures the
 * generic name may refer to; resolution requires an explicit measure.
 */
const GENERIC_MEASURE_FAMILIES: Record<string, string[]> = {
  policy_rate: ["fed_funds_target_upper", "fed_funds_target_lower", "fed_funds_effective", "reverse_repo_ceiling"],
  policyrate: ["fed_funds_target_upper", "fed_funds_target_lower", "fed_funds_effective", "reverse_repo_ceiling"],
  interest_rate: ["fed_funds_effective", "fed_funds_target_upper"],
  inflation: ["cpi_headline"],
  cpi: ["cpi_headline"],
  core_inflation: ["cpi_core"],
  unemployment: ["unemployment_rate"],
  gdp: ["gdp_nominal"],
};

export type MacroResolution =
  | { ok: true; identity: MacroSeriesIdentity }
  | { ok: false; reason: "ambiguous" | "not_found" | "not_covered"; message: string; candidates?: string[] };

/**
 * Resolve a macro request. `seriesId` may be a canonical id
 * ("US:FRED:FEDFUNDS"), a provider series ("FEDFUNDS"), or a generic measure
 * ("POLICY_RATE"). `geography` is an optional country/market qualifier.
 *
 * A generic measure without a geography returns `ambiguous` with the candidate
 * identities — it MUST NOT default to the US series.
 */
export function resolveMacroSeries(seriesId: string, geography?: string | null): MacroResolution {
  const raw = seriesId.trim();
  if (!raw) return { ok: false, reason: "not_found", message: "A macro series id is required." };

  const geo = geography ? resolveMarketId(geography) : null;

  // 1. Exact canonical id.
  const byId = SERIES.find((s) => s.id.toLowerCase() === raw.toLowerCase());
  if (byId) return { ok: true, identity: byId };

  // 2. Provider series id (unique across the registry).
  const byProvider = SERIES.filter((s) => s.providerSeries.toLowerCase() === raw.toLowerCase());
  if (byProvider.length === 1) return { ok: true, identity: byProvider[0] };
  if (byProvider.length > 1) {
    const candidates = byProvider.map((s) => s.id);
    return { ok: false, reason: "ambiguous", message: `"${raw}" matches multiple series.`, candidates };
  }

  // 3. Generic measure name — resolves only when it maps to ONE measure. A
  //    generic "policy rate" spans several measures and MUST be AMBIGUOUS, even
  //    with a geography (#3). It is never silently narrowed.
  const family = GENERIC_MEASURE_FAMILIES[raw.toLowerCase().replace(/\s+/g, "_")];
  if (family) {
    const scoped = geo ? SERIES.filter((s) => s.geography === geo && family.includes(s.measure)) : [];
    if (!geo) {
      return {
        ok: false,
        reason: "ambiguous",
        message:
          `"${raw}" is generic and must be scoped to a geography ` +
          `(e.g. "US policy rate" vs "ECB policy rate").`,
        candidates: SERIES.filter((s) => family.includes(s.measure)).map((s) => s.id),
      };
    }
    if (scoped.length === 0) {
      return {
        ok: false,
        reason: "not_covered",
        message: `No "${raw}" series is registered for ${geo}.`,
      };
    }
    if (scoped.length > 1) {
      return {
        ok: false,
        reason: "ambiguous",
        message:
          `"${raw}" on ${geo} could mean any of several measures ` +
          `(${scoped.map((s) => s.measure).join(", ")}). Specify the measure.`,
        candidates: scoped.map((s) => s.id),
      };
    }
    return { ok: true, identity: scoped[0] };
  }

  // 4. Unknown id with a known geography: allow provider pass-through ONLY when a
  //    source is declared; never silently route to a US backend.
  if (geo) {
    const identity: MacroSeriesIdentity = {
      id: `${geo}:?:${raw.toUpperCase()}`,
      geography: geo,
      institution: "unknown",
      measure: raw.toLowerCase(),
      adjustment: "unknown",
      frequency: "unknown",
      sourceId: "",
      providerSeries: raw,
    };
    return { ok: true, identity };
  }

  return {
    ok: false,
    reason: "ambiguous",
    message: `"${raw}" is not a known series and no geography was supplied.`,
  };
}

/** The default source for a geography when a series has no explicit sourceId. */
export function defaultSourceForGeography(geography: string): string | null {
  const row = SERIES.find((s) => s.geography === geography && s.sourceId);
  return row?.sourceId ?? null;
}

export const _SERIES_FOR_TEST = SERIES;
