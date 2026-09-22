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
  /** For an index series: its base (e.g. "1982-84=100"). An index without a
   *  base is not a number. */
  unitBase?: string;
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
  // CPI: an index LEVEL is not an inflation rate. The base is part of the value.
  { id: "US:FRED:CPIAUCSL", geography: "US", institution: "FRED", measure: "cpi_headline", adjustment: "sa", frequency: "monthly", unit: "index", unitBase: "1982-84=100", sourceId: "fred-analytics", providerSeries: "CPIAUCSL" },
  { id: "US:FRED:CPILFESL", geography: "US", institution: "FRED", measure: "cpi_core", adjustment: "sa", frequency: "monthly", unit: "index", unitBase: "1982-84=100", sourceId: "fred-analytics", providerSeries: "CPILFESL" },
  { id: "US:FRED:UNRATE", geography: "US", institution: "FRED", measure: "unemployment_rate", adjustment: "sa", frequency: "monthly", unit: "percent", sourceId: "fred-analytics", providerSeries: "UNRATE" },
  { id: "US:FRED:GDP", geography: "US", institution: "FRED", measure: "gdp_nominal", adjustment: "sa", frequency: "quarterly", unit: "usd_bn", currency: "USD", sourceId: "fred-analytics", providerSeries: "GDP" },
  { id: "US:FRED:M2SL", geography: "US", institution: "FRED", measure: "m2_money_stock", adjustment: "sa", frequency: "monthly", unit: "usd_bn", currency: "USD", sourceId: "fred-analytics", providerSeries: "M2SL" },
  // Non-US — routed to non-US backends (C1).
  { id: "EA:ECB:HICP", geography: "EA", institution: "ECB", measure: "hicp_headline", adjustment: "nsa", frequency: "monthly", unit: "index", unitBase: "2015=100", sourceId: "ecb", providerSeries: "hicp" },
  { id: "EA:ECB:DEPOSIT", geography: "EA", institution: "ECB", measure: "ecb_deposit_facility_rate", adjustment: "nsa", frequency: "daily", unit: "percent", sourceId: "ecb", providerSeries: "deposit" },
  { id: "EA:ECB:MRR", geography: "EA", institution: "ECB", measure: "ecb_main_refinancing_rate", adjustment: "nsa", frequency: "daily", unit: "percent", sourceId: "ecb", providerSeries: "mrr" },
  { id: "GB:BOE:BANKRATE", geography: "GB", institution: "OECD", measure: "boe_bank_rate", adjustment: "nsa", frequency: "daily", unit: "percent", sourceId: "oecd", providerSeries: "IR3TIB01GBM156N" },
  { id: "WLD:WORLDBANK:GDP", geography: "WLD", institution: "WorldBank", measure: "gdp_nominal", adjustment: "nsa", frequency: "annual", unit: "usd", sourceId: "worldbank", providerSeries: "NY.GDP.MKTP.CD" },
  { id: "WLD:IMF:CPI", geography: "WLD", institution: "IMF", measure: "cpi_headline", adjustment: "nsa", frequency: "annual", unit: "index", unitBase: "index", sourceId: "imf", providerSeries: "PCPIPC_WT" },
];

/**
 * Generic measure aliases → the set of measures they may refer to.
 *
 * A generic name must NEVER silently narrow to one measure. `cpi` spans the
 * headline and core index levels — it is AMBIGUOUS unless the caller names the
 * measure. An alias with an EMPTY set is a recognised concept with no registered
 * series (e.g. PMI) → `not_covered`, never a silent pass-through.
 */
const GENERIC_MEASURE_FAMILIES: Record<string, string[]> = {
  policy_rate: ["fed_funds_target_upper", "fed_funds_target_lower", "fed_funds_effective", "reverse_repo_ceiling"],
  policyrate: ["fed_funds_target_upper", "fed_funds_target_lower", "fed_funds_effective", "reverse_repo_ceiling"],
  interest_rate: ["fed_funds_effective", "fed_funds_target_upper"],
  // CPI is an INDEX, not a rate — never silently resolve to the index level.
  cpi: ["cpi_headline", "cpi_core"],
  inflation: ["cpi_headline", "cpi_core"],
  core_inflation: ["cpi_core"],
  hicp: ["hicp_headline"],
  unemployment: ["unemployment_rate"],
  gdp: ["gdp_nominal"],
  money_supply: ["m2_money_stock"],
  m2: ["m2_money_stock"],
  // Recognised macro concepts with no registered series yet.
  pmi: [],
  retail_sales: [],
  industrial_production: [],
  trade_balance: [],
  government_debt: [],
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
    // A recognised concept with no registered series is NOT_COVERED, never a
    // silent pass-through (e.g. PMI).
    if (family.length === 0) {
      return {
        ok: false,
        reason: "not_covered",
        message: `No "${raw}" series is registered${geo ? ` for ${geo}` : ""}.`,
      };
    }
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

  // 4. Unknown id: we cannot verify it against any registered series, so it is
  //    NOT_COVERED rather than a silent pass-through to a guessed backend.
  return {
    ok: false,
    reason: "not_covered",
    message: `"${raw}" is not a registered series.`,
  };
}

/** The default source for a geography when a series has no explicit sourceId. */
export function defaultSourceForGeography(geography: string): string | null {
  const row = SERIES.find((s) => s.geography === geography && s.sourceId);
  return row?.sourceId ?? null;
}

export const _SERIES_FOR_TEST = SERIES;
