// ── Observation freshness ────────────────────────────────────────────────────
// One place that decides whether a market observation may be presented as
// current. Before this, `/api/price-history` returned `source: "snapshot"` for a
// stale JDDS `Price` row but the payload carried no observation time or age, so
// a chart could draw a months-old close as if it were today's series — the same
// class of defect as a live header shown next to a stale series for the same
// symbol. It is symbol- and market-agnostic: every instrument goes through the
// same path. Freshness is METRIC-AND-INTERVAL AWARE: a daily bar is current
// on the session it belongs to, while an intraday bar ages within minutes.
//
// A live quote, an annual figure and a news article must not share one TTL, so
// the caller passes the series interval and this returns an explicit state. It
// never invents a timestamp: when none is known the state is `unknown`, and a
// last-good value is labelled `stale`/`historical`, never silently `live`.

export type Freshness = "live" | "delayed" | "stale" | "historical" | "unavailable" | "unknown";

export interface FreshnessRule {
  /** Observation is treated as current within this age. */
  live: number;
  /** Observation is `delayed` up to here, `stale` beyond it. */
  delayed: number;
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

// Yahoo allows ~15-min delayed data for many venues; a daily bar is current for
// the whole trading day it belongs to (plus a lazy overnight window). A 1-minute
// series decays within minutes. All values are deliberate, not universal truth.
export const FRESHNESS_RULES: Record<string, FreshnessRule> = {
  "1m": { live: 2 * MINUTE, delayed: 15 * MINUTE },
  "5m": { live: 10 * MINUTE, delayed: 60 * MINUTE },
  "15m": { live: 30 * MINUTE, delayed: 4 * HOUR },
  "30m": { live: 60 * MINUTE, delayed: 8 * HOUR },
  "60m": { live: 2 * HOUR, delayed: 2 * DAY },
  "1h": { live: 2 * HOUR, delayed: 2 * DAY },
  "1d": { live: 30 * HOUR, delayed: 5 * DAY },
  "1wk": { live: 8 * DAY, delayed: 21 * DAY },
  "1mo": { live: 35 * DAY, delayed: 95 * DAY },
};

const DEFAULT_RULE: FreshnessRule = FRESHNESS_RULES["1d"];

export function ruleForInterval(interval: string): FreshnessRule {
  return FRESHNESS_RULES[(interval || "").toLowerCase()] ?? DEFAULT_RULE;
}

export interface FreshnessAssessment {
  freshness: Freshness;
  /** Age of the observation in ms, or null when the observation time is unknown. */
  ageMs: number | null;
  stale: boolean;
}

/**
 * Classify a single observation time against `now`.
 * `observationMs` of null/NaN yields `unknown` (never `live`).
 */
export function assessFreshness(
  observationMs: number | null | undefined,
  interval: string,
  now = Date.now(),
): FreshnessAssessment {
  if (observationMs == null || !Number.isFinite(observationMs)) {
    return { freshness: "unknown", ageMs: null, stale: true };
  }
  // A future-stamped observation (clock skew) is treated as current, not stale.
  const ageMs = Math.max(0, now - observationMs);
  const rule = ruleForInterval(interval);
  if (ageMs <= rule.live) return { freshness: "live", ageMs, stale: false };
  if (ageMs <= rule.delayed) return { freshness: "delayed", ageMs, stale: true };
  return { freshness: "stale", ageMs, stale: true };
}

/** Latest bar time from a series, as epoch ms, or null when undeterminable. */
export function lastBarTimeMs(
  bars: Array<{ time?: number; date?: string }> | null | undefined,
): number | null {
  if (!bars || bars.length === 0) return null;
  for (let i = bars.length - 1; i >= 0; i--) {
    const b = bars[i];
    if (typeof b?.time === "number" && Number.isFinite(b.time)) return b.time;
    if (typeof b?.date === "string" && b.date) {
      const t = Date.parse(`${b.date}T00:00:00Z`);
      if (Number.isFinite(t)) return t;
    }
  }
  return null;
}

export interface ObservationMeta {
  /** End time of the newest observation (ISO), when known. */
  observationTime: string | null;
  /** When Eclipse produced this payload (ISO). */
  retrievedAt: string;
  freshness: Freshness;
  stale: boolean;
  ageMs: number | null;
}

/**
 * Build the freshness envelope attached to every market-history payload. The
 * `retrievedAt` is always stamped (we are producing the payload now); the
 * `observationTime` is only present when a real bar time exists.
 */
export function observationMeta(
  bars: Array<{ time?: number; date?: string }> | null | undefined,
  interval: string,
  now = Date.now(),
): ObservationMeta {
  const timeMs = lastBarTimeMs(bars);
  const { freshness, ageMs, stale } = assessFreshness(timeMs, interval, now);
  return {
    observationTime: timeMs != null ? new Date(timeMs).toISOString() : null,
    retrievedAt: new Date(now).toISOString(),
    freshness,
    stale,
    ageMs,
  };
}

/** Human label for a freshness state (UI + logs). */
export function freshnessLabel(f: Freshness): string {
  switch (f) {
    case "live": return "Live";
    case "delayed": return "Delayed";
    case "stale": return "Stale";
    case "historical": return "Historical";
    case "unavailable": return "Unavailable";
    default: return "Unknown";
  }
}

/**
 * One honest source line for the chart header/footer. It never prints "live"
 * for a stale observation — the whole point of the freshness envelope. `source`
 * is the provider (`yfinance`/`psx`/`snapshot`/`index`), `freshness` the age
 * verdict, `observationTime` the ISO bar time used to show the real as-of date.
 */
export function describeSeriesSource(
  source: string | undefined | null,
  freshness: Freshness | undefined | null,
  observationTime: string | null | undefined,
): string {
  if (!source || source === "none") return "";
  const asOf = observationTime ? observationTime.slice(0, 10) : "";
  if (freshness === "stale" || freshness === "historical") {
    return `stale${asOf ? ` · as of ${asOf}` : ""}`;
  }
  if (freshness === "delayed" || freshness === "unknown") {
    return `delayed${asOf ? ` · as of ${asOf}` : ""}`;
  }
  switch (source) {
    case "yfinance": return "live · Yahoo Finance";
    case "psx": return "live · PSX";
    case "index": return "live · index";
    case "snapshot": return `snapshot${asOf ? ` · as of ${asOf}` : ""}`;
    default: return source;
  }
}
