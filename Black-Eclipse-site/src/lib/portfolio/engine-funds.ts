'use client';

// ── Engine-backed funds ──────────────────────────────────────────────────────
// There is ONE portfolio type: a fund. The Python Portfolio Accounting Engine is
// the durable book (transactions, lots, positions, valuation); this module maps
// its rows to the Fund view's shape so the Fund Manager/Workspace keep their UI
// without a second localStorage ledger.

import { sdkUnlockHeaders } from '@/lib/sdk';
import type { Fund, Transaction, TxType } from '@/lib/portfolio/types';

interface EnginePortfolio {
  id: string;
  name: string;
  baseCurrency?: string;
  costBasisMethod?: string;
  kind?: string;
  metadata?: Record<string, unknown> | string;
  createdAt?: string;
  updatedAt?: string;
}

interface EngineTransaction {
  id: string;
  type: string;
  symbol?: string | null;
  quantity?: string | number | null;
  price?: string | number | null;
  grossAmount?: string | number | null;
  netAmount?: string | number | null;
  fees?: string | number | null;
  fee?: string | number | null;
  tradeDate?: string | null;
  createdAt?: string | null;
  notes?: string | null;
}

const DEFAULT_ICON = 'Briefcase';
const DEFAULT_ACCENT = '#34d399';
const DEFAULT_CURRENCY = 'USD';

function parseMetadata(raw: EnginePortfolio['metadata']): Record<string, unknown> {
  if (raw && typeof raw === 'object') return raw;
  if (typeof raw === 'string' && raw.trim()) {
    try {
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : {};
    } catch {
      return {};
    }
  }
  return {};
}

function num(value: unknown): number {
  const n = typeof value === 'number' ? value : Number(String(value ?? '').replace(/[,\s]/g, ''));
  return Number.isFinite(n) ? n : 0;
}

const TX_ALIASES: Record<string, TxType> = {
  TRANSFER_IN: 'BUY',
  TRANSFER_OUT: 'SELL',
};

function mapTransaction(tx: EngineTransaction): Transaction | null {
  const rawType = String(tx.type || '').toUpperCase();
  const type = (rawType in TX_ALIASES ? TX_ALIASES[rawType] : rawType) as TxType;
  if (!['BUY', 'SELL', 'DEPOSIT', 'WITHDRAWAL', 'DIVIDEND'].includes(type)) return null;
  const gross = num(tx.grossAmount ?? tx.netAmount);
  const cashFlow = type === 'DEPOSIT' || type === 'WITHDRAWAL';
  // The UI cost engine derives dividend income from quantity × price; the
  // engine stores a gross amount. Map that to 1 × gross so income is preserved.
  const dividend = type === 'DIVIDEND' && gross > 0;
  return {
    id: String(tx.id),
    type,
    symbol: String(tx.symbol || (cashFlow ? 'CASH' : '')).toUpperCase(),
    quantity: cashFlow ? gross || num(tx.quantity) : dividend ? 1 : num(tx.quantity),
    price: cashFlow ? 1 : dividend ? gross : num(tx.price),
    fee: num(tx.fees ?? tx.fee),
    date: String(tx.tradeDate || tx.createdAt || new Date().toISOString()),
    notes: tx.notes || undefined,
  };
}

function mapFund(record: EnginePortfolio, transactions: EngineTransaction[]): Fund {
  const meta = parseMetadata(record.metadata);
  const goal = meta.goal ?? meta.goalValue;
  return {
    id: record.id,
    name: record.name,
    icon: typeof meta.icon === 'string' && meta.icon ? meta.icon : DEFAULT_ICON,
    accent: typeof meta.accent === 'string' && meta.accent ? meta.accent : DEFAULT_ACCENT,
    goalValue: goal == null || goal === '' ? null : num(goal),
    baseCurrency: record.baseCurrency || DEFAULT_CURRENCY,
    costBasisMethod: (record.costBasisMethod as Fund['costBasisMethod']) || 'FIFO',
    createdAt: record.createdAt || new Date().toISOString(),
    transactions: transactions.map(mapTransaction).filter((tx): tx is Transaction => tx !== null),
  };
}

async function json<T>(url: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...sdkUnlockHeaders(), ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string; detail?: unknown };
  if (!res.ok) {
    const detail = body.detail;
    const message = typeof detail === 'string' ? detail
      : (detail && typeof detail === 'object' && 'message' in detail ? String((detail as { message?: string }).message) : '')
        || body.error || `portfolio request failed (${res.status})`;
    throw new Error(message);
  }
  return body;
}

function historyFunds(transactions: unknown): EngineTransaction[] {
  const body = transactions as { transactions?: EngineTransaction[] };
  return Array.isArray(body?.transactions) ? body.transactions : [];
}

/** Every portfolio is a fund; read them from the engine with their ledgers. */
export async function listEngineFunds(): Promise<Fund[]> {
  const { portfolios } = await json<{ portfolios?: EnginePortfolio[] }>('/api/portfolio/list');
  const records = (portfolios ?? []).filter((p) => (p.kind || 'fund') === 'fund');
  return Promise.all(records.map(async (record) => {
    try {
      const history = await fetch(`/api/portfolio/${encodeURIComponent(record.id)}/history?limit=500`, {
        headers: { ...sdkUnlockHeaders() },
      });
      const body = history.ok ? await history.json().catch(() => ({})) : {};
      return mapFund(record, historyFunds(body));
    } catch {
      return mapFund(record, []);
    }
  }));
}

/** Create a fund (the only portfolio type) with optional starting cash. */
export async function createEngineFund(input: {
  name: string;
  icon: string;
  accent: string;
  goalValue: number | null;
  startingCash: number;
  baseCurrency?: string;
  costBasisMethod?: 'FIFO' | 'LIFO' | 'AVERAGE_COST';
}): Promise<string> {
  const baseCurrency = input.baseCurrency || DEFAULT_CURRENCY;
  const created = await json<EnginePortfolio>('/api/portfolio/create', {
    method: 'POST',
    body: JSON.stringify({
      name: input.name,
      base_currency: baseCurrency,
      cost_basis_method: input.costBasisMethod || 'FIFO',
      kind: 'fund',
      metadata: {
        kind: 'fund',
        icon: input.icon,
        accent: input.accent,
        ...(input.goalValue != null ? { goal: input.goalValue } : {}),
      },
    }),
  });
  if (input.startingCash > 0) {
    await json(`/api/portfolio/${encodeURIComponent(created.id)}/transaction`, {
      method: 'POST',
      body: JSON.stringify({
        type: 'DEPOSIT',
        symbol: 'CASH',
        gross_amount: String(input.startingCash),
        currency: baseCurrency,
        notes: 'Starting budget',
      }),
    });
  }
  return created.id;
}

/** Update the fund's user-facing fields; metadata is merged engine-side. */
export async function updateEngineFund(
  fundId: string,
  patch: { name?: string; goalValue?: number | null; icon?: string; accent?: string },
): Promise<void> {
  const metadata: Record<string, unknown> = {};
  if (patch.goalValue !== undefined) metadata.goal = patch.goalValue;
  if (patch.icon !== undefined) metadata.icon = patch.icon;
  if (patch.accent !== undefined) metadata.accent = patch.accent;
  await json(`/api/portfolio/${encodeURIComponent(fundId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ name: patch.name, metadata }),
  });
}

export async function deleteEngineFund(fundId: string): Promise<void> {
  await json(`/api/portfolio/${encodeURIComponent(fundId)}`, { method: 'DELETE' });
}

/** Append one transaction to a fund's engine ledger. */
export async function addEngineFundTransaction(fund: Fund, tx: Transaction): Promise<void> {
  const currency = fund.baseCurrency || DEFAULT_CURRENCY;
  const payload: Record<string, unknown> = {
    type: tx.type,
    symbol: tx.symbol || (tx.type === 'DEPOSIT' || tx.type === 'WITHDRAWAL' ? 'CASH' : ''),
    currency,
    trade_date: tx.date,
    notes: tx.notes,
  };
  if (tx.type === 'DEPOSIT' || tx.type === 'WITHDRAWAL' || tx.type === 'DIVIDEND') {
    payload.gross_amount = String(tx.quantity * tx.price);
  } else {
    payload.quantity = String(tx.quantity);
    payload.price = String(tx.price);
    payload.fees = String(tx.fee || 0);
  }
  await json(`/api/portfolio/${encodeURIComponent(fund.id)}/transaction`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/** Import parsed fund books into the engine (create + replay transactions). */
export async function importEngineFunds(funds: Fund[]): Promise<{ created: number; errors: string[] }> {
  let created = 0;
  const errors: string[] = [];
  for (const fund of funds) {
    try {
      const id = await createEngineFund({
        name: fund.name,
        icon: fund.icon,
        accent: fund.accent,
        goalValue: fund.goalValue ?? null,
        startingCash: 0,
        baseCurrency: fund.baseCurrency,
      });
      for (const tx of fund.transactions) {
        await addEngineFundTransaction({ ...fund, id }, tx);
      }
      created += 1;
    } catch (err) {
      errors.push(`${fund.name}: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
  return { created, errors };
}
