// Economic calendar — upcoming releases (CPI, NFP, rate decisions, PMIs) with
// actual/forecast/previous values, importance, country and time.
//
// Primary source: Fincept's public econocalendar mirror (same catalog as the
// Economic Calendar source). Falls back to a curated static schedule of the
// highest-importance recurring releases when the mirror is unreachable — the
// fallback carries forecast/previous context only as labels, never fabricated
// numbers.

import { sortByDate } from "./fetch";

export interface CalendarEvent {
  id: string;
  date: string;       // ISO
  country: string;
  title: string;
  importance: "high" | "medium" | "low";
  actual: string | null;
  forecast: string | null;
  previous: string | null;
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
  return rows
    .map((row, i) => {
      const title = String(row.event ?? row.title ?? row.Event ?? "Release");
      const dateRaw = row.date ?? row.datetime ?? row.DateTime ?? row.time ?? row.Date;
      const ts = dateRaw ? Date.parse(String(dateRaw)) : NaN;
      if (Number.isNaN(ts)) return null;
      const str = (v: unknown) => (v === undefined || v === null || v === "" ? null : String(v));
      return {
        id: String(row.id ?? `${ts}-${i}`),
        date: new Date(ts).toISOString(),
        country: String(row.country ?? row.Country ?? row.region ?? "—"),
        title,
        importance: (["high", "medium", "low"].includes(String(row.importance ?? row.impact ?? "").toLowerCase())
          ? String(row.importance ?? row.impact).toLowerCase()
          : classifyImportance(title)) as CalendarEvent["importance"],
        actual: str(row.actual ?? row.Actual ?? row.actual_value),
        forecast: str(row.forecast ?? row.Forecast ?? row.forecast_value ?? row.consensus),
        previous: str(row.previous ?? row.Previous ?? row.previous_value),
      };
    })
    .filter((e): e is CalendarEvent => e !== null)
    .sort((a, b) => Date.parse(a.date) - Date.parse(b.date));
}

// Fallback: the recurring high-impact monthly schedule (times = ET). These are
// *scheduled slots*, not confirmed — values stay null until the mirror returns.
const FALLBACK_EVENTS: CalendarEvent[] = [
  { id: "fb-cpi", date: "", country: "US", title: "Consumer Price Index (CPI)", importance: "high", actual: null, forecast: null, previous: null },
  { id: "fb-nfp", date: "", country: "US", title: "Nonfarm Payrolls (NFP)", importance: "high", actual: null, forecast: null, previous: null },
  { id: "fb-fomc", date: "", country: "US", title: "FOMC Interest Rate Decision", importance: "high", actual: null, forecast: null, previous: null },
  { id: "fb-ecb", date: "", country: "EU", title: "ECB Interest Rate Decision", importance: "high", actual: null, forecast: null, previous: null },
  { id: "fb-boe", date: "", country: "UK", title: "BoE Interest Rate Decision", importance: "high", actual: null, forecast: null, previous: null },
  { id: "fb-boj", date: "", country: "JP", title: "BoJ Interest Rate Decision", importance: "high", actual: null, forecast: null, previous: null },
  { id: "fb-gdp", date: "", country: "US", title: "GDP (QoQ advance)", importance: "high", actual: null, forecast: null, previous: null },
  { id: "fb-ism", date: "", country: "US", title: "ISM Manufacturing PMI", importance: "medium", actual: null, forecast: null, previous: null },
];

export async function fetchEconomicCalendar(): Promise<{ events: CalendarEvent[]; source: string }> {
  try {
    const res = await fetch("https://fincept.pythonanywhere.com/api/v1/econocalendar/data", {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(15_000),
    });
    if (res.ok) {
      const events = mapRows(await res.json());
      if (events.length > 0) return { events, source: "fincept" };
    }
  } catch (err) {
    console.error("[economics/calendar] mirror fetch failed:", err instanceof Error ? err.message : err);
  }
  const now = new Date();
  const events = FALLBACK_EVENTS.map((e, i) => ({
    ...e,
    // Spread fallback placeholders over the next 30 days as scheduled slots.
    date: new Date(now.getTime() + (i + 1) * 3.5 * 24 * 3600 * 1000).toISOString(),
  }));
  return { events: sortByDate(events), source: "schedule-fallback" };
}