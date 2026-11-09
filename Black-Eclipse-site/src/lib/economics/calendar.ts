// Economic calendar — upcoming releases (CPI, NFP, rate decisions, PMIs) with
// actual/forecast/previous values, importance, country and time.
//
// Two independent sources are merged:
//   1. Fincept's public econocalendar mirror — the release catalog with
//      actual/forecast/previous values.
//   2. Official schedules (currently the Federal Reserve's FOMC calendar) —
//      authoritative *confirmed dates*, even when the mirror is unavailable.
//
// There is NO synthetic fallback. If neither source yields a date, the event is
// absent (or its date stays empty) — a fabricated date is worse than a gap.

import { fetchFomcSchedule } from "./calendars/fomc";

export type CalendarProvenance = "mirror" | "official" | "web";

export interface CalendarEvent {
  id: string;
  /** ISO datetime, or `YYYY-MM-DD` when the provider publishes a date only. */
  date: string;
  /** Human-readable release time, e.g. "14:00 ET". Null when unknown. */
  time?: string | null;
  country: string;
  title: string;
  importance: "high" | "medium" | "low";
  actual: string | null;
  forecast: string | null;
  previous: string | null;
  /** False when the official source itself marks the date tentative. */
  confirmed?: boolean;
  source?: CalendarProvenance;
  url?: string | null;
}

const HIGH_KEYWORDS = ["cpi", "nonfarm", "nfp", "interest rate", "rate decision", "fomc", "gdp", "payroll", "unemployment", "pmi", "monetary policy"];

function classifyImportance(title: string): CalendarEvent["importance"] {
  const t = title.toLowerCase();
  if (HIGH_KEYWORDS.some((k) => t.includes(k))) return "high";
  if (t.includes("sentiment") || t.includes("confidence") || t.includes("sales") || t.includes("claims")) return "medium";
  return "low";
}

// Map the Fincept mirror's row spellings into CalendarEvent.
function mapRows(raw: unknown): CalendarEvent[] {
  const rows: Record<string, unknown>[] = Array.isArray(raw)
    ? (raw as Record<string, unknown>[])
    : raw && typeof raw === "object" && Array.isArray((raw as Record<string, unknown>).data)
      ? ((raw as Record<string, unknown>).data as Record<string, unknown>[])
      : [];
  const mapped: (CalendarEvent | null)[] = rows.map((row, i): CalendarEvent | null => {
      const title = String(row.event ?? row.title ?? row.Event ?? "Release");
      const dateRaw = row.date ?? row.datetime ?? row.DateTime ?? row.time ?? row.Date;
      const ts = dateRaw ? Date.parse(String(dateRaw)) : NaN;
      if (Number.isNaN(ts)) return null;
      const str = (v: unknown) => (v === undefined || v === null || v === "" ? null : String(v));
      return {
        id: String(row.id ?? `${ts}-${i}`),
        date: new Date(ts).toISOString(),
        time: null,
        country: String(row.country ?? row.Country ?? row.region ?? "—"),
        title,
        importance: (["high", "medium", "low"].includes(String(row.importance ?? row.impact ?? "").toLowerCase())
          ? String(row.importance ?? row.impact).toLowerCase()
          : classifyImportance(title)) as CalendarEvent["importance"],
        actual: str(row.actual ?? row.Actual ?? row.actual_value),
        forecast: str(row.forecast ?? row.Forecast ?? row.forecast_value ?? row.consensus),
        previous: str(row.previous ?? row.Previous ?? row.previous_value),
        confirmed: true,
        source: "mirror" as const,
        url: null,
      };
    });
  return mapped
    .filter((e): e is CalendarEvent => e !== null)
    .sort((a, b) => Date.parse(a.date) - Date.parse(b.date));
}

function dayDistance(a: string, b: string): number {
  const ta = Date.parse(a);
  const tb = Date.parse(b);
  if (Number.isNaN(ta) || Number.isNaN(tb)) return Number.POSITIVE_INFINITY;
  return Math.abs(ta - tb) / (24 * 3600 * 1000);
}

function sameRelease(a: string, b: string): boolean {
  const x = a.toLowerCase();
  const y = b.toLowerCase();
  const isFomc = (t: string) => /fomc|federal reserve|federal open market/.test(t);
  if (isFomc(x) && isFomc(y)) return true;
  return x === y;
}

/**
 * Prefer the official date/confirmation while keeping the mirror's actual,
 * forecast and previous values. This is the only place a date is upgraded.
 */
export function mergeOfficialEvents(
  mirror: CalendarEvent[],
  official: CalendarEvent[],
): CalendarEvent[] {
  const merged = [...mirror];
  for (const event of official) {
    const index = merged.findIndex(
      (candidate) =>
        sameRelease(candidate.title, event.title) && dayDistance(candidate.date, event.date) <= 4,
    );
    if (index >= 0) {
      merged[index] = {
        ...merged[index],
        date: event.date,
        time: event.time ?? merged[index].time,
        confirmed: event.confirmed,
        source: "official",
        url: event.url ?? merged[index].url,
      };
    } else {
      merged.push(event);
    }
  }
  return merged.sort((a, b) => Date.parse(a.date) - Date.parse(b.date));
}

export interface EconomicCalendar {
  events: CalendarEvent[];
  source: "mirror" | "official" | "mirror+official" | "unavailable";
  /** Non-fatal diagnostics, e.g. "FOMC schedule unreachable". */
  warnings: string[];
}

export async function fetchEconomicCalendar(): Promise<EconomicCalendar> {
  const warnings: string[] = [];
  let mirror: CalendarEvent[] = [];
  try {
    const res = await fetch("https://fincept.pythonanywhere.com/api/v1/econocalendar/data", {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(15_000),
    });
    if (res.ok) {
      mirror = mapRows(await res.json());
    } else {
      warnings.push(`calendar mirror HTTP ${res.status}`);
    }
  } catch (err) {
    warnings.push(
      `calendar mirror failed: ${err instanceof Error ? err.message : String(err)}`,
    );
  }

  let official: CalendarEvent[] = [];
  try {
    const meetings = await fetchFomcSchedule();
    const cutoff = Date.now() - 24 * 60 * 60 * 1000;
    official = meetings
      .filter((m) => Date.parse(m.date) >= cutoff)
      .map((m) => ({
        id: `fomc-${m.date}`,
        date: m.date,
        time: m.time,
        country: m.country,
        title: m.title,
        importance: "high" as const,
        actual: null,
        forecast: null,
        previous: null,
        confirmed: m.confirmed,
        source: "official" as const,
        url: m.url,
      }));
  } catch (err) {
    warnings.push(
      `FOMC schedule failed: ${err instanceof Error ? err.message : String(err)}`,
    );
  }

  if (mirror.length === 0 && official.length === 0) {
    if (warnings.length > 0) {
      console.error("[economics/calendar]", warnings.join("; "));
    }
    return { events: [], source: "unavailable", warnings };
  }

  const events = mergeOfficialEvents(mirror, official);
  const source: EconomicCalendar["source"] =
    mirror.length > 0 && official.length > 0
      ? "mirror+official"
      : mirror.length > 0
        ? "mirror"
        : "official";
  return { events, source, warnings };
}
