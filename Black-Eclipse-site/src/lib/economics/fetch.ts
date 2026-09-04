// Economic series normalization — one function that flattens ANY provider's
// response into { date, value, ...rest } rows.
//
// Providers spell dates and values ~dozens of ways ("date", "Date",
// "TIME_PERIOD", "period", "year", "record_date", "obs_date", ... and "value",
// "Value", "OBS_VALUE", "obs_value", "amount", "rate", ...). The normalizer
// scans every known spelling on each row, zero-pads bare years so "999" sorts
// before "1999", and returns null (never a silent 0) for gaps.

export interface EconPoint {
  date: string;
  value: number | null;
  [key: string]: unknown;
}

// ~15 date-key spellings across World Bank, IMF, OECD, Eurostat, BLS, Census,
// FiscalData, BCB, StatCan, ILO, Comtrade, OWID, BEA, EIA, ...
export const DATE_KEYS = [
  "date", "Date", "DATE", "TIME_PERIOD", "time_period", "timePeriod", "period",
  "Period", "year", "Year", "YEAR", "record_date", "ref_date", "obs_date",
  "obsDate", "referenceAreaDate", "REF_DATE", "Ref_Date", "start_of_week",
  "release_date", "asOfDate", "time", "timestamp",
] as const;

// ~7 value-key spellings.
export const VALUE_KEYS = [
  "value", "Value", "VALUE", "OBS_VALUE", "obs_value", "obsValue",
  "amount", "rate", "Rate", "y", "Y", "close", "level",
] as const;

// Zero-pad a bare year so lexicographic sorting is correct: "999" -> "0999".
export function padYear(date: string): string {
  const trimmed = date.trim();
  if (/^\d{1,3}$/.test(trimmed)) return trimmed.padStart(4, "0");
  // ISO-ish "999-01" partial → pad the year part.
  const m = trimmed.match(/^(\d{1,3})([-/].+)$/);
  if (m) return m[1].padStart(4, "0") + m[2];
  return trimmed;
}

function pickDate(row: Record<string, unknown>): string | null {
  for (const key of DATE_KEYS) {
    const v = row[key];
    if (v !== undefined && v !== null && typeof v !== "object") {
      const s = String(v);
      if (s.trim()) return padYear(s);
    }
  }
  return null;
}

function pickValue(row: Record<string, unknown>): number | null {
  for (const key of VALUE_KEYS) {
    const v = row[key];
    if (v === undefined || v === null) continue;
    if (typeof v === "number") return Number.isFinite(v) ? v : null;
    if (typeof v === "string") {
      const cleaned = v.replace(/[, ]/g, "").replace(/^\((.*)\)$/, "-$1");
      if (cleaned === "" || cleaned === ".." || cleaned === "." || cleaned === "NA" || cleaned === "N/A" || cleaned === "-") continue;
      const n = Number(cleaned);
      if (Number.isFinite(n)) return n;
    }
  }
  return null; // gap — never coerce to 0
}

// Recursively find the first array of objects (or arrays) inside a response —
// providers wrap data in { data: {...} }, { records: [...] }, { results: [...] },
// { indicator: [...], country: [...], data: [...] } etc.
function extractRows(raw: unknown): Record<string, unknown>[] {
  if (Array.isArray(raw)) {
    // Array of scalars → not rows; array of objects/arrays → rows.
    if (raw.length === 0) return [];
    const first = raw[0];
    if (typeof first === "object" && first !== null) {
      return raw as Record<string, unknown>[];
    }
  }
  if (raw && typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    // Prefer known wrapper keys, then any first array-valued member.
    for (const key of ["records", "data", "results", "observations", "series", "points", "items", "rows", "history"]) {
      const v = obj[key];
      if (Array.isArray(v) && v.length > 0 && typeof v[0] === "object") {
        return extractRows(v);
      }
    }
    for (const v of Object.values(obj)) {
      if (Array.isArray(v) && v.length > 0 && typeof v[0] === "object") {
        const nested = extractRows(v);
        if (nested.length > 0) return nested;
      }
    }
  }
  return [];
}

// World Bank v2 returns compact [country, indicator, date, value] tuples in
// `records` when using the /source/2/ endpoint with formats=json.
function rowsFromTuples(raw: unknown): Record<string, unknown>[] {
  if (Array.isArray(raw)) {
    if (raw.length > 0 && Array.isArray(raw[0])) {
      return (raw as unknown[][]).map((t) => {
        // Heuristic: [.., dateStr, value] — last two cells.
        const date = t.length >= 2 ? t[t.length - 2] : t[0];
        const value = t[t.length - 1];
        return { date, value };
      });
    }
  }
  if (raw && typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    if (Array.isArray(obj.records) && obj.records.length > 0 && Array.isArray(obj.records[0])) {
      return rowsFromTuples(obj.records);
    }
  }
  return [];
}

export function normalizeEconomicSeries(raw: unknown, _sourceId: string): EconPoint[] {
  const tuples = rowsFromTuples(raw);
  const rows = tuples.length > 0 ? tuples : extractRows(raw);
  const out: EconPoint[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const date = pickDate(row);
    if (!date) continue;
    const value = pickValue(row);
    const rest: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(row)) {
      if (DATE_KEYS.includes(k as (typeof DATE_KEYS)[number]) || VALUE_KEYS.includes(k as (typeof VALUE_KEYS)[number])) continue;
      if (v !== null && typeof v === "object") continue;
      rest[k] = v;
    }
    out.push({ date, value, ...rest });
  }
  return out;
}

// Sort (date, value) chronologically — oldest first. Handles "2023", "2023-Q1",
// "2023-01", ISO datetimes, and the zero-padded years above.
export function sortByDate(points: EconPoint[]): EconPoint[] {
  const time = (d: string): number => {
    const ts = Date.parse(d);
    if (!Number.isNaN(ts)) return ts;
    // "2023-Q2" → quarter end; "2023" → year start; "0999" padded years parse fine after expansion
    const y = parseInt(d.slice(0, 4), 10);
    if (Number.isFinite(y)) return new Date(y, 0, 1).getTime();
    return Number.MAX_SAFE_INTEGER;
  };
  return [...points].sort((a, b) => time(a.date) - time(b.date) || (a.value ?? 0) - (b.value ?? 0));
}

// ─── Stat-card math ──────────────────────────────────────────────────────

export interface SeriesStats {
  latest: number | null;
  change: number | null; // (latest-prev)/|prev|
  min: number | null;
  max: number | null;
  avg: number | null;
  points: number;
  asOf: string | null;
  isTimeSeries: boolean; // false → cross-section (one row per country etc.)
}

export function computeStats(points: EconPoint[]): SeriesStats {
  const finite = points.filter((p) => p.value !== null && Number.isFinite(p.value));
  if (finite.length === 0) {
    return { latest: null, change: null, min: null, max: null, avg: null, points: points.length, asOf: null, isTimeSeries: false };
  }
  const sorted = sortByDate(finite);
  const dates = new Set(sorted.map((p) => p.date));
  // Cross-section: one row per date (e.g. all countries for one year) — not a
  // time series, so LATEST/CHANGE are meaningless.
  const isTimeSeries = sorted.length > 1 && dates.size > 1;
  const latest = sorted[sorted.length - 1].value;
  const prev = sorted.length >= 2 ? sorted[sorted.length - 2].value : null;
  const change =
    isTimeSeries && latest !== null && prev !== null && prev !== 0
      ? (latest - prev) / Math.abs(prev)
      : null;
  const values = sorted.map((p) => p.value as number);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const avg = values.reduce((s, v) => s + v, 0) / values.length;
  return { latest, change, min, max, avg, points: sorted.length, asOf: sorted[sorted.length - 1].date, isTimeSeries };
}