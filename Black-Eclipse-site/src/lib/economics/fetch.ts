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
  "release_date", "asOfDate", "time", "timestamp", "data",
] as const;

// ~7 value-key spellings.
export const VALUE_KEYS = [
  "value", "Value", "VALUE", "OBS_VALUE", "obs_value", "obsValue",
  "amount", "rate", "Rate", "y", "Y", "close", "level", "valor",
] as const;

// Zero-pad a bare year so lexicographic sorting is correct: "999" -> "0999".
export function padYear(date: string): string {
  const trimmed = date.trim();
  if (/^\d{1,3}$/.test(trimmed)) return trimmed.padStart(4, "0");
  // Partial year like "999-01" (year 999, month 01) → pad the year part. Only
  // when the string has no 4-digit year already (i.e. it's not a full date).
  if (!/\d{4}/.test(trimmed)) {
    const m = trimmed.match(/^(\d{1,3})([-/].+)$/);
    if (m) return m[1].padStart(4, "0") + m[2];
  }
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
    if (raw.length === 0) return [];
    // Prefer a nested array-of-objects member (World Bank v2 returns
    // [meta, [rows]]; IMF/others wrap data in arrays too). Recurse into the
    // first element that is itself an array of plain objects.
    for (const v of raw) {
      if (Array.isArray(v) && v.length > 0 && typeof v[0] === "object" && !Array.isArray(v[0])) {
        const nested = extractRows(v);
        if (nested.length > 0) return nested;
      }
    }
    // Otherwise, an array of plain objects is the rows themselves.
    const first = raw[0];
    if (typeof first === "object" && first !== null && !Array.isArray(first)) {
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
      return (raw as unknown[][]).filter((t) => {
        // A data tuple's last cell must be a scalar number (not an object/array,
        // not a metadata row like ["meta"]).
        const last = t[t.length - 1];
        return typeof last !== "object" && Number.isFinite(Number(String(last).replace(/,/g, "")));
      }).map((t) => {
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
  // SDMX-JSON: { value: { "0": 100.5, ... }, dimension: { time: {...}, geo: {...} } }
  // Values are keyed by flattened index; dimensions map each index to labels.
  const sdmx = rowsFromSdmx(raw);
  if (sdmx.length > 0) return sdmx;

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

// SDMX-JSON (Eurostat, OECD, BIS, ILO, UNESCO, ECB): the payload has a `value`
// object keyed by flattened index and a `dimension` object whose members map
// each index to a label (e.g. time → { "0": "2015", ... }, geo → { "0": "EU27_2020" }).
// We reconstruct one row per index, using the `time` dimension as the date.
function rowsFromSdmx(raw: unknown): EconPoint[] {
  if (!raw || typeof raw !== "object") return [];
  const obj = raw as Record<string, unknown>;
  const value = obj.value;
  const dimension = obj.dimension;
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];
  if (!dimension || typeof dimension !== "object" || Array.isArray(dimension)) return [];

  const dims = dimension as Record<string, unknown>;
  // Find the time dimension (any of the common spellings).
  const timeKey = Object.keys(dims).find((k) => ["time", "TIME", "Time", "period", "TIME_PERIOD"].includes(k));
  const timeDim = timeKey ? (dims[timeKey] as Record<string, unknown>) : null;
  const timeIndex = timeDim && typeof timeDim === "object" ? (timeDim.index as Record<string, unknown> | undefined) : undefined;

  const out: EconPoint[] = [];
  for (const [idx, v] of Object.entries(value as Record<string, unknown>)) {
    if (v === null || v === undefined) continue;
    const n = typeof v === "number" ? v : Number(String(v).replace(/,/g, ""));
    if (!Number.isFinite(n)) continue;
    let date: string | null = null;
    if (timeIndex && timeIndex[idx] !== undefined) {
      date = padYear(String(timeIndex[idx]));
    } else if (timeDim && timeDim.categories) {
      const cat = (timeDim.categories as Record<string, unknown>).index as Record<string, unknown> | undefined;
      if (cat && cat[idx] !== undefined) date = padYear(String(cat[idx]));
    }
    if (!date) continue;
    out.push({ date, value: n });
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
  // POINTS counts every observation row, including gap rows.
  return { latest, change, min, max, avg, points: points.length, asOf: sorted[sorted.length - 1].date, isTimeSeries };
}