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

export interface EarningsResult {
  rows: EarningsRow[];
  source: 'alphavantage' | 'unavailable';
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

async function fetchFromAlphaVantage(): Promise<EarningsResult> {
  const fetchedAt = new Date().toISOString();
  const key = await resolveProviderKey('ALPHAVANTAGE_API_KEY');
  if (!key) {
    return {
      rows: [],
      source: 'unavailable',
      fetchedAt,
      reason: 'No Alpha Vantage API key. Add one in Settings › API Keys.',
    };
  }
  const url = `${ALPHA_URL}?function=EARNINGS_CALENDAR&horizon=3month&apikey=${encodeURIComponent(key)}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15_000);
  try {
    const res = await fetch(url, { signal: controller.signal, cache: 'no-store' });
    if (!res.ok) {
      return { rows: [], source: 'unavailable', fetchedAt, reason: `Alpha Vantage returned ${res.status}.` };
    }
    const text = await res.text();
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
  } catch (err) {
    const reason = err instanceof Error && err.name === 'AbortError'
      ? 'Alpha Vantage request timed out.'
      : 'Could not reach Alpha Vantage.';
    return { rows: [], source: 'unavailable', fetchedAt, reason };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Earnings calendar with a 6h cache. Concurrent callers share one in-flight
 * request. On failure, a stale cached result is served rather than blanking.
 */
export async function getEarningsCalendar(): Promise<EarningsResult> {
  if (cache && Date.now() - cache.t < CACHE_TTL_MS) return cache.result;
  if (inFlight) return inFlight;
  inFlight = fetchFromAlphaVantage()
    .then((result) => {
      if (result.source === 'alphavantage') cache = { t: Date.now(), result };
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
