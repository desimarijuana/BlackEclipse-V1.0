// ── Interactive dataset bridge ───────────────────────────────────────────────
//
// A widget may ask for a REAL market series, but it never fetches it: the host
// (app origin) reads the existing read-only `/api/price-history` route and hands
// the normalized bars to the sandboxed frame over postMessage. That keeps the
// frame offline and keeps the model out of the data path — it names a symbol,
// it never types prices.
//
// Pure normalization is separated from the fetch so it can be unit tested.

import {
  INTERACTIVE_INTERVALS,
  INTERACTIVE_RANGES,
  MAX_INTERACTIVE_BARS,
  type InteractiveDatasetRequest,
} from '@/lib/response/blocks/interactive';

export interface InteractiveBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export type InteractiveDatasetEnvelope =
  | { status: 'loading' }
  | {
      status: 'ready';
      bars: InteractiveBar[];
      source: string;
      asOf: string | null;
      freshness: string;
      stale: boolean;
      interval: string;
      currency?: string;
    }
  | { status: 'unavailable'; reason: string };

const SYMBOL_RE = /^[A-Za-z0-9^.\-=]{1,32}$/;
const MARKET_RE = /^[A-Za-z]{1,16}$/;

function asNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function asDate(value: unknown): string | null {
  if (typeof value === 'string' && value.trim() !== '') return value.trim();
  if (typeof value === 'number' && Number.isFinite(value)) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date.toISOString().slice(0, 10);
  }
  return null;
}

function rowToBar(row: unknown): InteractiveBar | null {
  if (!row || typeof row !== 'object') return null;
  const record = row as Record<string, unknown>;
  const date = asDate(record.date) ?? asDate(record.t);
  const open = asNumber(record.open);
  const close = asNumber(record.close);
  if (!date || open == null || close == null) return null;
  const high = asNumber(record.high) ?? Math.max(open, close);
  const low = asNumber(record.low) ?? Math.min(open, close);
  const volume = asNumber(record.volume ?? record.v);
  return { date, open, high, low, close, volume };
}

/** Validate a request before it can reach the market bridge. */
export function validateDatasetRequest(request: InteractiveDatasetRequest): string | null {
  if (!request || typeof request !== 'object') return 'Missing dataset request.';
  if (!SYMBOL_RE.test(request.symbol ?? '')) return 'Invalid symbol.';
  if (request.market && !MARKET_RE.test(request.market)) return 'Invalid market.';
  if (request.range && !(INTERACTIVE_RANGES as readonly string[]).includes(request.range)) {
    return 'Unsupported range.';
  }
  if (request.interval && !(INTERACTIVE_INTERVALS as readonly string[]).includes(request.interval)) {
    return 'Unsupported interval.';
  }
  return null;
}

/** Turn a `/api/price-history` payload into the host→frame envelope. */
export function normalizeHistoryPayload(
  payload: unknown,
  request: InteractiveDatasetRequest,
): InteractiveDatasetEnvelope {
  const record = payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : {};
  const rawSeries = Array.isArray(record.series) ? record.series : [];
  const bars = rawSeries
    .map(rowToBar)
    .filter((bar): bar is InteractiveBar => bar != null)
    .slice(-MAX_INTERACTIVE_BARS);

  if (bars.length === 0) {
    return {
      status: 'unavailable',
      reason: `No price series for ${request.symbol.toUpperCase()}.`,
    };
  }

  const observationTime =
    typeof record.observationTime === 'string' ? record.observationTime : null;
  const freshness = typeof record.freshness === 'string' ? record.freshness : 'unknown';
  return {
    status: 'ready',
    bars,
    source: typeof record.source === 'string' ? record.source : 'unknown',
    asOf: observationTime ? observationTime.slice(0, 10) : bars[bars.length - 1]?.date ?? null,
    freshness,
    stale: record.stale === true || freshness === 'stale' || freshness === 'historical',
    interval: typeof record.interval === 'string' ? record.interval : request.interval ?? '1d',
    currency: typeof record.currency === 'string' ? record.currency : undefined,
  };
}

export interface LoadDatasetOptions {
  fetchImpl?: typeof fetch;
  signal?: AbortSignal;
}

/**
 * Fetch a series through the existing market bridge. Never throws: a failure
 * becomes an explicit `unavailable` envelope so the widget can render an honest
 * empty state instead of inventing data.
 */
export async function loadInteractiveDataset(
  request: InteractiveDatasetRequest | undefined,
  options: LoadDatasetOptions = {},
): Promise<InteractiveDatasetEnvelope> {
  if (!request) return { status: 'unavailable', reason: 'No dataset requested.' };
  const invalid = validateDatasetRequest(request);
  if (invalid) return { status: 'unavailable', reason: invalid };

  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  if (typeof fetchImpl !== 'function') {
    return { status: 'unavailable', reason: 'Market data is unavailable in this environment.' };
  }

  const params = new URLSearchParams({
    symbol: request.symbol.toUpperCase(),
    range: request.range ?? '6mo',
    interval: request.interval ?? '1d',
  });
  if (request.market) params.set('market', request.market.toUpperCase());

  try {
    const response = await fetchImpl(`/api/price-history?${params.toString()}`, {
      signal: options.signal,
      headers: { accept: 'application/json' },
    });
    if (!response.ok) {
      return { status: 'unavailable', reason: `Market data request failed (HTTP ${response.status}).` };
    }
    const payload: unknown = await response.json();
    return normalizeHistoryPayload(payload, request);
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return { status: 'unavailable', reason: 'Market data request was cancelled.' };
    }
    return { status: 'unavailable', reason: 'Could not load market data.' };
  }
}

/** The envelope used when a widget has no dataset (static or user-supplied). */
export function staticDatasetEnvelope(): InteractiveDatasetEnvelope {
  return {
    status: 'ready',
    bars: [],
    source: 'none',
    asOf: null,
    freshness: 'unknown',
    stale: false,
    interval: '1d',
  };
}
