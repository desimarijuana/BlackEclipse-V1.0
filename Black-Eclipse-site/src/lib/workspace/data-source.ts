'use client';

// ── UI data-source resolver ──────────────────────────────────────────────────
// The ONE place a widget's `source` string becomes live data. A blueprint widget
// is data-only: it names a source (e.g. `portfolio:pf_…:positions` or
// `market:quote:AAPL`) and the widget renders whatever this resolver returns —
// never a fabricated value.
//
// The resolver is an ALLOW-LIST. Only the families below parse; an unknown or
// unconfigured source resolves to an explicit UNAVAILABLE state. It never
// fetches an arbitrary URL from a config (that would be an SSRF hole).
//
// Source grammar (v1):
//   portfolio:<portfolioId>:<view>            → table (positions, holdings, …)
//   portfolio:<portfolioId>:<view>.<field>    → single metric (summary.totalValue)
//   market:quote:<SYMBOLS>                    → quote table (AAPL, AAPL,MSFT)
//   market:indices:<MARKET>                   → index table (US, CRYPTO, …)
//   market:price:<SYMBOL>                     → time series (for charts)
//   news:latest                               → the latest news table
//   agent:activity                            → recent agent runs
// A trailing `.<field>` selects one column as a single value (metric-card).
//
// The vocabulary mirrors the Python runtime's `dataSourceRegistry`
// (`UiService.list_data_sources`); the runtime advertises it so the agent never
// invents a source that does not resolve.

import { useMemo } from 'react';
import { registerTopic, useTopic, type HubEntry } from './data-hub';
import {
  readPortfolio,
  readPortfolioTaxLots,
  readPortfolioTransactions,
  type PortfolioView,
} from '@/lib/portfolio/engine-read';

export const PORTFOLIO_VIEWS: readonly PortfolioView[] = [
  'summary', 'positions', 'holdings', 'transactions', 'pnl', 'performance', 'risk', 'allocation', 'tax-lots',
];

export const MARKET_MARKETS = ['US', 'CRYPTO', 'PK', 'IN', 'CN', 'TW', 'HK', 'JP', 'KR', 'SG', 'MY', 'AU', 'UK', 'DE', 'FR', 'CA'] as const;

export interface SourceColumn {
  key: string;
  label: string;
  align?: 'left' | 'right';
}

export interface SourceSeries {
  name: string;
  points: number[];
  dates?: string[];
}

/** The normalized result a widget renders. Never carries a fabricated number. */
export interface ResolvedSource {
  kind: 'rows' | 'value' | 'series' | 'unavailable';
  columns?: SourceColumn[];
  rows?: Record<string, unknown>[];
  value?: string | number | null;
  label?: string;
  series?: SourceSeries[];
  provenance: 'LIVE' | 'UNAVAILABLE';
  detail?: string;
}

export type ParsedSource =
  | { family: 'portfolio'; portfolioId: string; view: PortfolioView; field?: string }
  | { family: 'market'; kind: 'quote' | 'indices' | 'price'; arg: string; field?: string }
  | { family: 'news'; arg: 'latest'; field?: string }
  | { family: 'agent'; arg: 'activity'; field?: string }
  | { family: 'tasks'; view: 'list' | 'plans' }
  | { family: 'artifacts'; view: 'list' }
  | { family: 'research'; view: 'list' }
  | { family: 'jdds'; view: 'search'; arg: string; field?: string };

const PORTFOLIO_PREFIX = 'portfolio';

/** Split `a.b` into base + field; a field is only after the FIRST dot. */
function splitField(value: string): { base: string; field?: string } {
  const dot = value.indexOf('.');
  if (dot < 0) return { base: value };
  return { base: value.slice(0, dot), field: value.slice(dot + 1) || undefined };
}

/** Parse a source string, or return null when it is not a known family/shape. */
export function parseSource(source: string | null | undefined): ParsedSource | null {
  const raw = (source ?? '').trim();
  if (!raw) return null;
  const parts = raw.split(':');
  if (parts.length < 2) return null;

  if (parts[0] === PORTFOLIO_PREFIX) {
    if (parts.length !== 3) return null;
    const portfolioId = parts[1].trim();
    const { base, field } = splitField(parts[2].trim());
    if (!portfolioId || !base) return null;
    if (!(PORTFOLIO_VIEWS as readonly string[]).includes(base)) return null;
    return { family: 'portfolio', portfolioId, view: base as PortfolioView, field };
  }

  if (parts[0] === 'market') {
    if (parts.length !== 3) return null;
    const kind = parts[1];
    if (kind !== 'quote' && kind !== 'indices' && kind !== 'price') return null;
    const { base, field } = splitField(parts[2].trim());
    if (!base) return null;
    return { family: 'market', kind, arg: base, field };
  }

  if (parts[0] === 'news' && parts.length === 2 && parts[1] === 'latest') {
    return { family: 'news', arg: 'latest' };
  }
  if (parts[0] === 'agent' && parts.length === 2 && parts[1] === 'activity') {
    return { family: 'agent', arg: 'activity' };
  }
  if (parts[0] === 'tasks' && parts.length === 2 && (parts[1] === 'list' || parts[1] === 'plans')) {
    return { family: 'tasks', view: parts[1] };
  }
  if (parts[0] === 'artifacts' && parts.length === 2 && parts[1] === 'list') {
    return { family: 'artifacts', view: 'list' };
  }
  if (parts[0] === 'research' && parts.length === 2 && parts[1] === 'list') {
    return { family: 'research', view: 'list' };
  }
  if (parts[0] === 'jdds' && parts.length === 3 && parts[1] === 'search') {
    const { base, field } = splitField(parts[2].trim());
    if (!base) return null;
    return { family: 'jdds', view: 'search', arg: base, field };
  }
  return null;
}

function unavailable(detail: string): ResolvedSource {
  return { kind: 'unavailable', provenance: 'UNAVAILABLE', detail };
}

function asString(v: unknown): string {
  if (v == null) return '—';
  if (typeof v === 'number') return v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  return String(v);
}

function metricValue(v: unknown): string | number | null {
  if (v == null) return null;
  if (typeof v === 'number' || typeof v === 'string') return v;
  return asString(v);
}

async function getJson(url: string): Promise<{ ok: boolean; data: Record<string, unknown> | null; detail?: string }> {
  try {
    const res = await fetch(url);
    const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (!res.ok) {
      const detail = (body?.detail ?? body?.error) as string | undefined;
      return { ok: false, data: null, detail: detail || `runtime HTTP ${res.status}` };
    }
    return { ok: true, data: body };
  } catch (err) {
    return { ok: false, data: null, detail: err instanceof Error ? err.message : 'request failed' };
  }
}

/** Resolve one source string to renderable data. */
export async function resolveSource(source: string | null | undefined): Promise<ResolvedSource> {
  const parsed = parseSource(source);
  if (!parsed) return unavailable(source?.trim() ? `unrecognised source "${source}"` : 'no source configured');

  switch (parsed.family) {
    case 'portfolio': return resolvePortfolio(parsed);
    case 'market': return resolveMarket(parsed);
    case 'news': return resolveNews();
    case 'agent': return resolveAgent();
    case 'tasks': return resolveTasks(parsed);
    case 'artifacts': return resolveArtifacts();
    case 'research': return resolveResearch();
    case 'jdds': return resolveJdds(parsed);
    default: return unavailable('unrecognised source');
  }
}

// ── portfolio ────────────────────────────────────────────────────────────────

async function resolvePortfolio(parsed: Extract<ParsedSource, { family: 'portfolio' }>): Promise<ResolvedSource> {
  const { view, field } = parsed;
  const isTable = view === 'positions' || view === 'holdings'
    || view === 'allocation' || view === 'transactions' || view === 'tax-lots';

  if (view === 'transactions') {
    const res = await readPortfolioTransactions(parsed.portfolioId);
    if (!res.ok || !res.data) return unavailable(res.detail ?? 'transactions unavailable');
    const body = res.data as { transactions?: Record<string, unknown>[] };
    const rows = body.transactions ?? (Array.isArray(res.data) ? (res.data as Record<string, unknown>[]) : []);
    return { kind: 'rows', rows, columns: columnsFromRows(rows, ['tradeDate', 'type', 'symbol', 'quantity', 'price', 'fees']), provenance: 'LIVE' };
  }

  if (view === 'tax-lots') {
    const res = await readPortfolioTaxLots(parsed.portfolioId);
    if (!res.ok || !res.data) return unavailable(res.detail ?? 'tax lots unavailable');
    const rows = (res.data as { symbols?: Record<string, unknown>[] }).symbols ?? [];
    return {
      kind: 'rows', rows, provenance: 'LIVE',
      columns: [
        { key: 'symbol', label: 'Symbol' },
        { key: 'remainingQuantity', label: 'Qty', align: 'right' },
        { key: 'averageCost', label: 'Avg Cost', align: 'right' },
        { key: 'remainingCostBasis', label: 'Cost Basis', align: 'right' },
        { key: 'realizedPnl', label: 'Realized P/L', align: 'right' },
      ],
    };
  }

  const read = await readPortfolio(parsed.portfolioId, view);
  if (!read.ok || !read.data) return unavailable(read.detail ?? 'portfolio unavailable');
  const data = read.data as unknown as Record<string, unknown>;

  if (isTable) return { kind: 'rows', provenance: 'LIVE', ...tableFor(view, data) };

  const metrics = metricsFor(view, data);
  if (field) {
    const value = pickMetric(metrics, field);
    if (value === undefined) return unavailable(`field "${field}" is not available on a "${view}" view`);
    return { kind: 'value', value: metricValue(value), label: field, provenance: 'LIVE' };
  }
  const first = Object.keys(metrics)[0];
  if (!first) return unavailable(`no metrics in a "${view}" view`);
  return { kind: 'value', value: metricValue(metrics[first]), label: first, provenance: 'LIVE' };
}

function pickMetric(metrics: Record<string, unknown>, key: string): unknown {
  if (key in metrics) return metrics[key];
  const lower = key.toLowerCase();
  const match = Object.keys(metrics).find((k) => k.toLowerCase() === lower);
  return match ? metrics[match] : undefined;
}

function tableFor(view: PortfolioView, data: Record<string, unknown>): { rows: Record<string, unknown>[]; columns: SourceColumn[] } {
  if (view === 'positions' || view === 'holdings') {
    return {
      rows: (data.positions as Record<string, unknown>[]) ?? [],
      columns: [
        { key: 'symbol', label: 'Symbol' },
        { key: 'quantity', label: 'Qty', align: 'right' },
        { key: 'averageCost', label: 'Avg Cost', align: 'right' },
        { key: 'price', label: 'Price', align: 'right' },
        { key: 'marketValueBase', label: 'Value (base)', align: 'right' },
        { key: 'unrealizedPnlBase', label: 'Unrealized P/L', align: 'right' },
        { key: 'weight', label: 'Weight %', align: 'right' },
      ],
    };
  }
  if (view === 'allocation') {
    const allocations = (data.allocation as Record<string, { breakdown?: Record<string, unknown>[] }>) ?? {};
    const dimension = 'assetClass' in allocations ? 'assetClass' : Object.keys(allocations)[0];
    return {
      rows: dimension ? (allocations[dimension]?.breakdown ?? []) : [],
      columns: [
        { key: 'key', label: dimension ?? 'Bucket' },
        { key: 'value', label: 'Value', align: 'right' },
        { key: 'weight', label: 'Weight %', align: 'right' },
      ],
    };
  }
  return { rows: [], columns: [] };
}

function metricsFor(view: PortfolioView, data: Record<string, unknown>): Record<string, unknown> {
  if (view === 'summary') {
    const v = (data.valuation ?? {}) as Record<string, unknown>;
    const cash = (data.cash ?? {}) as Record<string, unknown>;
    return {
      totalValue: v.totalValue ?? null,
      investedValue: v.investedValue ?? null,
      cash: cash.balance ?? v.cash ?? null,
      netDeposits: cash.netDeposits ?? null,
      dividends: cash.dividends ?? null,
    };
  }
  if (view === 'pnl') {
    const pnl = (data.pnl ?? {}) as Record<string, unknown>;
    return {
      realizedPnl: pnl.realizedPnl ?? null,
      unrealizedPnl: pnl.unrealizedPnl ?? null,
      totalPnl: pnl.totalPnl ?? null,
      costBasis: pnl.costBasis ?? null,
      dividends: pnl.dividends ?? null,
    };
  }
  if (view === 'risk') {
    const risk = (data.risk ?? {}) as Record<string, unknown>;
    return { status: risk.status ?? null, ...((risk.metrics as Record<string, unknown>) ?? {}) };
  }
  if (view === 'performance') {
    const perf = (data.performance ?? {}) as Record<string, unknown>;
    return { status: perf.status ?? null, ...((perf.metrics as Record<string, unknown>) ?? {}) };
  }
  return {};
}

// ── market / news / agent ────────────────────────────────────────────────────

async function resolveMarket(parsed: Extract<ParsedSource, { family: 'market' }>): Promise<ResolvedSource> {
  if (parsed.kind === 'price') {
    const res = await getJson(`/api/price-history?symbol=${encodeURIComponent(parsed.arg)}`);
    if (!res.ok || !res.data) return unavailable(res.detail ?? 'price history unavailable');
    const body = res.data as { points?: number[]; series?: Array<{ date?: string; close?: number }> };
    const points = body.points ?? (body.series ?? []).map((b) => Number(b.close ?? 0)).filter((n) => Number.isFinite(n));
    if (!points || points.length < 2) return unavailable('no price history for this symbol');
    const dates = (body.series ?? []).map((b) => b.date ?? '').filter(Boolean);
    return { kind: 'series', series: [{ name: parsed.arg, points, dates: dates.length ? dates : undefined }], provenance: 'LIVE' };
  }

  const url = parsed.kind === 'quote'
    ? `/api/quote?symbols=${encodeURIComponent(parsed.arg)}`
    : `/api/indices?market=${encodeURIComponent(parsed.arg)}`;
  const key = parsed.kind === 'quote' ? 'quotes' : 'indices';
  const res = await getJson(url);
  if (!res.ok || !res.data) return unavailable(res.detail ?? `${parsed.kind} unavailable`);
  const rows = (res.data[key] as Record<string, unknown>[]) ?? [];
  if (rows.length === 0) return unavailable(`no ${parsed.kind} data for "${parsed.arg}"`);
  if (parsed.field) {
    const value = pickMetric(rows[0], parsed.field);
    if (value === undefined) return unavailable(`field "${parsed.field}" is not available`);
    return { kind: 'value', value: metricValue(value), label: parsed.field, provenance: 'LIVE' };
  }
  return {
    kind: 'rows', rows, provenance: 'LIVE',
    columns: columnsFromRows(rows, parsed.kind === 'quote'
      ? ['symbol', 'name', 'price', 'changePercent', 'currency']
      : ['symbol', 'name', 'price', 'change', 'changePct']),
  };
}

async function resolveNews(): Promise<ResolvedSource> {
  const res = await getJson('/api/news?limit=30');
  if (!res.ok || !res.data) return unavailable(res.detail ?? 'news unavailable');
  const rows = (res.data.news as Record<string, unknown>[]) ?? [];
  return {
    kind: 'rows', rows, provenance: 'LIVE',
    columns: columnsFromRows(rows, ['timestamp', 'source', 'ticker', 'headline', 'sentiment']),
  };
}

async function resolveAgent(): Promise<ResolvedSource> {
  const res = await getJson('/api/agent/activity');
  if (!res.ok || !res.data) return unavailable(res.detail ?? 'agent activity unavailable');
  const rows = (res.data.runs as Record<string, unknown>[]) ?? [];
  return {
    kind: 'rows', rows, provenance: 'LIVE',
    columns: columnsFromRows(rows, ['startedAt', 'agent', 'status', 'toolCalls', 'toolErrors']),
  };
}

async function resolveTasks(parsed: Extract<ParsedSource, { family: 'tasks' }>): Promise<ResolvedSource> {
  const isPlans = parsed.view === 'plans';
  const res = await getJson(`/api/tasks${isPlans ? '/plans' : '?limit=50'}`);
  if (!res.ok || !res.data) return unavailable(res.detail ?? 'tasks unavailable');
  const key = isPlans ? 'plans' : 'tasks';
  const rows = (res.data[key] as Record<string, unknown>[]) ?? [];
  return {
    kind: 'rows', rows, provenance: 'LIVE',
    columns: columnsFromRows(rows, isPlans
      ? ['title', 'status', 'priority', 'updatedAt']
      : ['title', 'status', 'priority', 'assignedTo', 'updatedAt']),
  };
}

async function resolveArtifacts(): Promise<ResolvedSource> {
  const res = await getJson('/api/artifacts?limit=50');
  if (!res.ok || !res.data) return unavailable(res.detail ?? 'artifacts unavailable');
  const rows = (res.data.artifacts as Record<string, unknown>[]) ?? [];
  return {
    kind: 'rows', rows, provenance: 'LIVE',
    columns: columnsFromRows(rows, ['createdAt', 'displayName', 'category', 'mimeType', 'sizeBytes']),
  };
}

async function resolveResearch(): Promise<ResolvedSource> {
  const res = await getJson('/api/research/list?limit=50');
  if (!res.ok || !res.data) return unavailable(res.detail ?? 'research runs unavailable');
  const rows = (res.data.runs as Record<string, unknown>[]) ?? [];
  return {
    kind: 'rows', rows, provenance: 'LIVE',
    columns: columnsFromRows(rows, ['createdAt', 'question', 'intent', 'state', 'status']),
  };
}

async function resolveJdds(parsed: Extract<ParsedSource, { family: 'jdds' }>): Promise<ResolvedSource> {
  const res = await getJson(`/api/quote?q=${encodeURIComponent(parsed.arg)}`);
  if (!res.ok || !res.data) return unavailable(res.detail ?? 'jdds search unavailable');
  const rows = (res.data.suggestions as Record<string, unknown>[]) ?? [];
  if (rows.length === 0) return unavailable(`no instruments match "${parsed.arg}"`);
  if (parsed.field) {
    const value = pickMetric(rows[0], parsed.field);
    if (value === undefined) return unavailable(`field "${parsed.field}" is not available`);
    return { kind: 'value', value: metricValue(value), label: parsed.field, provenance: 'LIVE' };
  }
  return {
    kind: 'rows', rows, provenance: 'LIVE',
    columns: columnsFromRows(rows, ['symbol', 'name', 'marketId', 'price', 'currency']),
  };
}

// ── shared helpers ───────────────────────────────────────────────────────────

function labelise(key: string): string {
  return key
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/^\w/, (c) => c.toUpperCase());
}

/** Build columns from a row set, preferring a known field order. */
export function columnsFromRows(rows: Record<string, unknown>[], preferred: string[] = []): SourceColumn[] {
  const keys = new Set<string>();
  for (const key of preferred) if (rows.some((r) => key in r)) keys.add(key);
  for (const row of rows.slice(0, 3)) for (const key of Object.keys(row)) keys.add(key);
  return [...keys].map((key) => ({
    key,
    label: labelise(key),
    align: rows.some((r) => typeof r[key] === 'number') ? 'right' : 'left',
  }));
}

const NONE_TOPIC = 'ui-source:__none__';

/**
 * Subscribe a component to a source string. Registers a dynamic, cached DataHub
 * topic so the same source is fetched once and shared by every widget using it.
 */
export function useDataSource(source?: string | null): HubEntry<ResolvedSource> {
  const parsed = parseSource(source);
  const topicId = parsed ? `ui-source:${source}` : NONE_TOPIC;
  useMemo(() => {
    if (parsed) {
      registerTopic({ id: topicId, ttl: 60_000, interval: 60_000, fetch: () => resolveSource(source) });
    } else {
      registerTopic({ id: NONE_TOPIC, ttl: 60_000, interval: 0, fetch: async () => unavailable('no source configured') });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed by topicId (source derives it)
  }, [topicId]);
  return useTopic<ResolvedSource>(topicId);
}
