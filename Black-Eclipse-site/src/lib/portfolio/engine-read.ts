// ── Portfolio engine reads (browser) ─────────────────────────────────────────
// The CLIENT-safe transport for reading a portfolio from the Python Portfolio
// Accounting Engine through the existing front door (`/api/portfolio/**`).
// It adds NO accounting logic: it maps a UI *view* to the engine's `include`
// set (or a dedicated read route) and returns exactly what the runtime owns,
// with an honest UNAVAILABLE result instead of a fabricated one.
//
// This is the data half of the UI data-source resolver
// (`src/lib/workspace/data-source.ts`); `portfolio-client.ts` is the
// server-only equivalent and must not be imported here.

import type { PortfolioRead } from '@/lib/harness/portfolio-client';

export type PortfolioView =
  | 'summary'
  | 'positions'
  | 'holdings'
  | 'transactions'
  | 'pnl'
  | 'performance'
  | 'risk'
  | 'allocation'
  | 'tax-lots';

/** The engine `include` set that augments the always-on read for a view. */
export const PORTFOLIO_VIEW_INCLUDE: Partial<Record<PortfolioView, string[]>> = {
  pnl: ['pnl'],
  holdings: ['pnl'],
  performance: ['performance'],
  risk: ['risk'],
  allocation: ['allocation'],
};

export interface EngineReadResult<T = unknown> {
  ok: boolean;
  data: T | null;
  /** Honest provenance; never inferred beyond what the front door reported. */
  provenance: 'LIVE' | 'UNAVAILABLE';
  detail?: string;
}

function queryUrl(id: string): string {
  return `/api/portfolio/${encodeURIComponent(id)}/query`;
}

/** Read one portfolio as the engine's full `PortfolioRead`. */
export async function readPortfolio(
  id: string,
  view: PortfolioView = 'summary',
  opts: { marks?: Record<string, unknown> } = {},
): Promise<EngineReadResult<PortfolioRead>> {
  try {
    const res = await fetch(queryUrl(id), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ include: PORTFOLIO_VIEW_INCLUDE[view] ?? [], marks: opts.marks }),
    });
    const body = (await res.json().catch(() => ({}))) as Partial<PortfolioRead> & { error?: string; detail?: string };
    if (!res.ok) {
      return { ok: false, data: null, provenance: 'UNAVAILABLE', detail: body?.detail || body?.error || `runtime HTTP ${res.status}` };
    }
    return { ok: true, data: body as PortfolioRead, provenance: 'LIVE' };
  } catch (err) {
    return { ok: false, data: null, provenance: 'UNAVAILABLE', detail: err instanceof Error ? err.message : 'portfolio read failed' };
  }
}

/** Read the transaction ledger (a dedicated route, not part of `query`). */
export async function readPortfolioTransactions(id: string, limit = 200): Promise<EngineReadResult> {
  return getJson(`/api/portfolio/${encodeURIComponent(id)}/history?limit=${limit}`);
}

/** Read open tax lots. */
export async function readPortfolioTaxLots(id: string, symbol?: string): Promise<EngineReadResult> {
  const q = symbol ? `?symbol=${encodeURIComponent(symbol)}` : '';
  return getJson(`/api/portfolio/${encodeURIComponent(id)}/tax-lots${q}`);
}

async function getJson(url: string): Promise<EngineReadResult> {
  try {
    const res = await fetch(url);
    const body = (await res.json().catch(() => ({}))) as { error?: string; detail?: string };
    if (!res.ok) {
      return { ok: false, data: null, provenance: 'UNAVAILABLE', detail: body?.detail || body?.error || `runtime HTTP ${res.status}` };
    }
    return { ok: true, data: body, provenance: 'LIVE' };
  } catch (err) {
    return { ok: false, data: null, provenance: 'UNAVAILABLE', detail: err instanceof Error ? err.message : 'portfolio read failed' };
  }
}

/** List portfolios (id + name + base currency) — used by pickers/verification. */
export async function listEnginePortfolios(): Promise<Array<{ id: string; name: string; baseCurrency: string }>> {
  try {
    const res = await fetch('/api/portfolio/list');
    if (!res.ok) return [];
    const body = (await res.json().catch(() => ({}))) as { portfolios?: Array<{ id: string; name: string; baseCurrency: string }> };
    return body.portfolios ?? [];
  } catch {
    return [];
  }
}
