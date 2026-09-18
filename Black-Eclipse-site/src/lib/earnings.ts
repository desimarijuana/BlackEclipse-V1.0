// ── Earnings calendar ────────────────────────────────────────────────────────
// Upcoming company earnings for the Command Center. Server-only.
//
// Primary source: Alpha Vantage EARNINGS_CALENDAR (CSV, horizon=3month) using
// the operator's key from the existing provider-key vault
// (`ALPHAVANTAGE_API_KEY`). The key is read server-side only and never returned
// to the browser. On any failure — no key, network error, rate limit, or an
// unparseable body — the result is an explicit `unavailable` state with a
// reason. This module NEVER fabricates rows.

import { resolveProviderKey } from '@/lib/provider-keys';

const ALPHA_URL = 'https://www.alphavantage.co/query';

export interface EarningsRow {
  symbol: string;
  name: string;
  /** ISO date (YYYY-MM-DD). */
  date: string;
  /** 'BMO' (before open) | 'AMC' (after close) | null when unreported. */
  time: 'BMO' | 'AMC' | null;
  epsEstimate: number | null;
  /** Reported EPS is present for past dates only. */
  epsActual: number | null;
  currency: string | null;
}

export type EarningsSource = 'alphavantage' | 'nasdaq' | 'unavailable';

export interface EarningsResult {
  rows: EarningsRow[];
  source: EarningsSource;
  /** ISO timestamp of the fetch. */
  fetchedAt: string;
  /** Human reason shown when `source === 'unavailable'`. */
  reason?: string;
}

/** Split a CSV line, honouring double-quoted fields with embedded commas. */
function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (line[i + 1] === '"') { cur += '"'; i++; }
        else inQuotes = false;
      } else cur += ch;
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ',') {
      out.push(cur); cur = '';
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out;
}

function parseNum(v: string | undefined): number | null {
  if (v == null) return null;
  const t = v.trim();
  if (!t || t.toLowerCase() === 'none' || t.toLowerCase() === 'null') return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

/** Parse the Alpha Vantage EARNINGS_CALENDAR CSV payload. Exported for tests. */
export function parseEarningsCsv(csv: string): EarningsRow[] {
  const lines = csv.split(/\r?\n/).filter(l => l.trim() !== '');
  if (lines.length < 2) return [];
  const header = splitCsvLine(lines[0]).map(h => h.trim().toLowerCase());
  // Accept Alpha Vantage's header aliases across API versions
  // (`estimate` vs `estimatedEPS`, `reportedEPS` vs `reported`).
  const col = (...names: string[]) => {
    for (const n of names) {
      const i = header.indexOf(n);
      if (i !== -1) return i;
    }
    return -1;
  };
  const iSym = col('symbol');
  const iName = col('name');
  const iDate = col('reportdate');
  const iTime = col('timeoftheday');
  const iEst = col('estimatedeps', 'estimate');
  const iAct = col('reportedeps', 'reported');
  const iCur = col('currency');
  if (iSym === -1 || iDate === -1) return [];

  const rows: EarningsRow[] = [];
  for (let i = 1; i < lines.length; i++) {
    const f = splitCsvLine(lines[i]);
    const symbol = (f[iSym] ?? '').trim().toUpperCase();
    const date = (f[iDate] ?? '').trim();
    if (!symbol || !date) continue;
    const rawTime = (iTime !== -1 ? (f[iTime] ?? '').trim().toLowerCase() : '');
    // Alpha Vantage returns either `bmo`/`amc` or `pre-market`/`post-market`.
    const time: EarningsRow['time'] =
      rawTime.startsWith('bmo') || rawTime.startsWith('pre') ? 'BMO'
        : rawTime.startsWith('amc') || rawTime.startsWith('post') ? 'AMC'
          : null;
    rows.push({
      symbol,
      name: (iName !== -1 ? (f[iName] ?? '').trim() : '') || symbol,
      date,
      time,
      epsEstimate: parseNum(iEst !== -1 ? f[iEst] : undefined),
      epsActual: parseNum(iAct !== -1 ? f[iAct] : undefined),
      currency: (iCur !== -1 ? (f[iCur] ?? '').trim() : '') || null,
    });
  }
  return rows;
}

// ── Cache ────────────────────────────────────────────────────────────────────
// The calendar changes slowly; cache for 6h and serve stale on error so a
// transient Alpha Vantage hiccup never blanks the widget.

const CACHE_TTL_MS = 6 * 60 * 60 * 1000;
let cache: { t: number; result: EarningsResult } | null = null;
let inFlight: Promise<EarningsResult> | null = null;

async function getJson(url: string, timeoutMs = 15_000): Promise<{ ok: boolean; status: number; text: string }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      cache: 'no-store',
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; BlackEclipse/1.0)', Accept: 'application/json, text/csv, */*' },
    });
    return { ok: res.ok, status: res.status, text: await res.text() };
  } finally {
    clearTimeout(timer);
  }
}

async function fetchFromAlphaVantage(key: string): Promise<EarningsResult> {
  const fetchedAt = new Date().toISOString();
  const url = `${ALPHA_URL}?function=EARNINGS_CALENDAR&horizon=3month&apikey=${encodeURIComponent(key)}`;
  const res = await getJson(url);
  if (!res.ok) {
    return { rows: [], source: 'unavailable', fetchedAt, reason: `Alpha Vantage returned ${res.status}.` };
  }
  const text = res.text;
  // Alpha Vantage answers a rate limit / bad key with JSON (or an info note)
  // rather than a non-200, so detect it before treating the body as CSV.
  const head = text.trimStart().slice(0, 40).toLowerCase();
  if (head.startsWith('{') || head.startsWith('"') || head.includes('thank you for using')) {
    let note = 'Alpha Vantage rejected the request.';
    try {
      const j = JSON.parse(text) as Record<string, string>;
      note = j['Information'] || j['Note'] || j['Error Message'] || note;
    } catch { /* keep default */ }
    return { rows: [], source: 'unavailable', fetchedAt, reason: note };
  }
  const rows = parseEarningsCsv(text);
  if (rows.length === 0) {
    return { rows: [], source: 'unavailable', fetchedAt, reason: 'Alpha Vantage returned no earnings rows.' };
  }
  return { rows, source: 'alphavantage', fetchedAt };
}

// ── Nasdaq fallback (keyless) ────────────────────────────────────────────────
// Alpha Vantage is the PRIMARY source, but a zero-config install has no key.
// Nasdaq's public calendar endpoint needs no key, so we fall back to it. Shape:
//   { data: { rows: [{ symbol, name, time, epsForecast, ... }] } }
// `time` is 'time-pre-market' | 'time-after-hours' | 'time-not-supplied'.

function parseNasdaqMoney(v: unknown): number | null {
  if (typeof v !== 'string') return null;
  const t = v.trim();
  if (!t || t === 'N/A') return null;
  const negative = /^\(.*\)$/.test(t);
  const n = Number(t.replace(/[()$,]/g, ''));
  if (!Number.isFinite(n)) return null;
  return negative ? -n : n;
}

/** Parse one Nasdaq calendar response. Exported for tests. */
export function parseNasdaqEarnings(json: unknown): EarningsRow[] {
  const rows = (json as { data?: { rows?: unknown } })?.data?.rows;
  if (!Array.isArray(rows)) return [];
  const out: EarningsRow[] = [];
  for (const r of rows) {
    if (!r || typeof r !== 'object') continue;
    const o = r as Record<string, unknown>;
    const symbol = typeof o.symbol === 'string' ? o.symbol.trim().toUpperCase() : '';
    if (!symbol) continue;
    // The endpoint is queried per-day; the date is injected by the caller.
    const time = typeof o.time === 'string'
      ? (/pre/i.test(o.time) ? 'BMO' as const : /after|post/i.test(o.time) ? 'AMC' as const : null)
      : null;
    out.push({
      symbol,
      name: typeof o.name === 'string' && o.name.trim() ? o.name.trim() : symbol,
      date: '', // filled in by fetchFromNasdaq
      time,
      epsEstimate: parseNasdaqMoney(o.epsForecast),
      epsActual: null,
      currency: 'USD',
    });
  }
  return out;
}

/** Fetch a few upcoming weekdays from Nasdaq and merge into one list. */
async function fetchFromNasdaq(): Promise<EarningsResult> {
  const fetchedAt = new Date().toISOString();
  const days: string[] = [];
  // Next 5 weekdays (today included) — enough for the Today/Tomorrow/Week filters.
  for (let i = 0; days.length < 5 && i < 9; i++) {
    const d = new Date(Date.now() + i * 86_400_000);
    const dow = d.getDay();
    if (dow === 0 || dow === 6) continue;
    days.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`);
  }
  const results = await Promise.all(days.map(async (date) => {
    try {
      const res = await getJson(`https://api.nasdaq.com/api/calendar/earnings?date=${date}`, 12_000);
      if (!res.ok) return [] as EarningsRow[];
      const parsed = parseNasdaqEarnings(JSON.parse(res.text));
      return parsed.map(r => ({ ...r, date }));
    } catch { return [] as EarningsRow[]; }
  }));
  const rows = results.flat();
  if (rows.length === 0) {
    return { rows: [], source: 'unavailable', fetchedAt, reason: 'Nasdaq returned no earnings rows.' };
  }
  return { rows, source: 'nasdaq', fetchedAt };
}

/** Alpha Vantage first (if a key is configured), then the keyless Nasdaq feed. */
async function fetchEarnings(): Promise<EarningsResult> {
  const key = await resolveProviderKey('ALPHAVANTAGE_API_KEY');
  if (key) {
    const av = await fetchFromAlphaVantage(key);
    if (av.source === 'alphavantage') return av;
    // Key present but rejected/limited — fall through to Nasdaq rather than
    // showing nothing, and keep the Alpha Vantage reason if Nasdaq also fails.
    const nasdaq = await fetchFromNasdaq();
    if (nasdaq.source !== 'unavailable') return nasdaq;
    return { ...nasdaq, reason: `${av.reason ?? 'Alpha Vantage failed.'} · ${nasdaq.reason ?? ''}`.trim() };
  }
  return fetchFromNasdaq();
}

/**
 * Earnings calendar with a 6h cache. Concurrent callers share one in-flight
 * request. On failure, a stale cached result is served rather than blanking.
 */
export async function getEarningsCalendar(): Promise<EarningsResult> {
  if (cache && Date.now() - cache.t < CACHE_TTL_MS) return cache.result;
  if (inFlight) return inFlight;
  inFlight = fetchEarnings()
    .then((result) => {
      if (result.source !== 'unavailable') cache = { t: Date.now(), result };
      else if (cache) return cache.result; // serve stale on failure
      return result;
    })
    .finally(() => { inFlight = null; });
  return inFlight;
}

/** Test seam: clear the module cache. */
export function __clearEarningsCache(): void {
  cache = null;
  inFlight = null;
}
