// ── One-time migration: localStorage funds → the Portfolio engine ───────────
// The Portfolio screen had TWO books: the default view read localStorage
// ("Fund"/"Transaction") while the Ledger read the Python Portfolio Accounting
// Engine — so the same "holdings" question had two answers. This migrates the
// legacy book into the engine (the single source of truth, ADR: the ledger is
// authoritative) exactly once, idempotently, and records a fund.id → portfolioId
// map so reads can resolve the same book afterwards.
//
// It runs in the BROWSER through the `/api/portfolio/**` proxy (`portfolio-client`
// is server-only); the engine never trusts a body flag, so the proxy's operator
// token is what authorizes the write. Migration is best-effort: a failure leaves
// the legacy store intact and the flag unset, so it is retried, never half-lost.

import type { Fund, Transaction } from '@/lib/portfolio/types';

export const PORTFOLIO_MIGRATION_FLAG = 'be_portfolio_migrated_v1';
export const PORTFOLIO_FUND_MAP_KEY = 'be_portfolio_fund_map_v1';

type MinimalStorage = Pick<Storage, 'getItem' | 'setItem'>;
export type EngineFetch = (path: string, init?: RequestInit) => Promise<Response>;

export interface MigrationSummary {
  migrated: boolean;
  funds: number;
  positions: number;
  skippedTransactions: number;
  map: Record<string, string>;
  errors: string[];
}

function defaultStorage(): MinimalStorage | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null;
  } catch {
    return null;
  }
}

/** The engine accepts only these as position-affecting trades. */
const POSITION_TYPES = new Set(['BUY', 'SELL']);

/** Map one legacy transaction to the engine's add-position payload, or null to skip. */
export function mapTransactionToPosition(tx: Transaction): Record<string, unknown> | null {
  if (!POSITION_TYPES.has(tx.type) || !tx.symbol) return null;
  return {
    symbol: tx.symbol.trim().toUpperCase(),
    quantity: String(tx.quantity),
    price: String(tx.price),
    fees: tx.fee ? String(tx.fee) : undefined,
    type: tx.type,
    tradeDate: tx.date || undefined,
  };
}

/**
 * Migrate the legacy localStorage funds into the engine exactly once.
 *
 * Idempotent: a completed migration (flag set) is a no-op; a fund already present
 * in the map is not re-created. Never throws — a failure is reported in `errors`
 * and leaves the flag unset so the next load retries.
 */
export async function migrateFundsToEngine(
  funds: Fund[],
  opts: { fetchImpl?: EngineFetch; base?: string; storage?: MinimalStorage | null } = {},
): Promise<MigrationSummary> {
  const storage = opts.storage === undefined ? defaultStorage() : opts.storage;
  const base = opts.base ?? '/api/portfolio';
  const doFetch: EngineFetch = opts.fetchImpl ?? ((path, init) => fetch(path, init));
  const empty: MigrationSummary = {
    migrated: false, funds: 0, positions: 0, skippedTransactions: 0, map: {}, errors: [],
  };
  if (!storage || storage.getItem(PORTFOLIO_MIGRATION_FLAG) === '1' || funds.length === 0) {
    return empty;
  }

  let map: Record<string, string> = {};
  try {
    map = JSON.parse(storage.getItem(PORTFOLIO_FUND_MAP_KEY) || '{}') as Record<string, string>;
  } catch {
    map = {};
  }

  const summary: MigrationSummary = { ...empty, map: { ...map } };
  for (const fund of funds) {
    let portfolioId = map[fund.id];
    try {
      if (!portfolioId) {
        const created = await doFetch(`${base}/create`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: fund.name,
            cost_basis_method: 'FIFO',
            kind: 'fund',
            metadata: {
              kind: 'fund',
              icon: fund.icon,
              accent: fund.accent,
              ...(fund.goalValue != null ? { goal: fund.goalValue } : {}),
            },
          }),
        });
        if (!created.ok) throw new Error(`create ${created.status}`);
        const body = (await created.json()) as { id?: string };
        if (!body?.id) throw new Error('create returned no id');
        portfolioId = body.id;
        map[fund.id] = portfolioId;
        storage.setItem(PORTFOLIO_FUND_MAP_KEY, JSON.stringify(map));
        summary.funds += 1;
      }
      for (const tx of fund.transactions) {
        const payload = mapTransactionToPosition(tx);
        if (payload === null) {
          summary.skippedTransactions += 1;
          continue;
        }
        const added = await doFetch(`${base}/${encodeURIComponent(portfolioId)}/position`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!added.ok) throw new Error(`position ${added.status}`);
        summary.positions += 1;
      }
    } catch (err) {
      summary.errors.push(`${fund.id}: ${err instanceof Error ? err.message : String(err)}`);
      return summary; // leave the flag unset → retried on the next load
    }
  }

  if (summary.errors.length === 0) {
    storage.setItem(PORTFOLIO_MIGRATION_FLAG, '1');
    summary.migrated = true;
    summary.map = map;
  }
  return summary;
}
