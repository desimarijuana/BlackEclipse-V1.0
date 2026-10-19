'use client';

// ── Portfolio Ledger — the accounting-engine UI ──────────────────────────────
// Renders the Python Portfolio Accounting Engine's read model: positions,
// valuation, P&L, allocation, tax lots and rebalancing proposals. Prices come
// from the same JDdS quotes the rest of the app uses, passed to the engine as
// `marks` so valuation is real; a missing or stale price is surfaced, never
// hidden. No accounting math happens here — every number is the engine's.
//
// It talks ONLY to the Next.js proxy routes (/api/portfolio/**), never to the
// Python harness client directly (that module imports Node builtins and is
// server-only). Types are imported type-only, so they are erased.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { sdkUnlockHeaders } from '@/lib/sdk';
import type {
  MarksMap,
  PortfolioRead,
  PortfolioSummary,
  RebalanceResult,
  TaxLotsResult,
} from '@/lib/harness/portfolio-client';

const BASE = '/api/portfolio';

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...sdkUnlockHeaders(), ...(init.headers ?? {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { error?: string; detail?: string }).error ?? (data as { detail?: string }).detail;
    throw new Error(detail || `request failed (${res.status})`);
  }
  return data as T;
}

function fmt(value: string | number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || value === '') return '—';
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return '—';
  return n.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

const freshnessTone: Record<string, string> = {
  FRESH: 'text-emerald-400',
  STALE: 'text-amber-400',
  VERY_STALE: 'text-orange-400',
  MISSING: 'text-red-400',
};

async function buildMarks(symbols: string[]): Promise<MarksMap> {
  const marks: MarksMap = {};
  const now = new Date().toISOString();
  const unique = [...new Set(symbols.map((s) => s.toUpperCase()))].filter(Boolean);
  const currencies = new Set<string>();
  try {
    if (unique.length > 0) {
      const res = await fetch(`/api/quote?symbols=${encodeURIComponent(unique.join(','))}`, {
        signal: AbortSignal.timeout(20000),
      });
      const data = await res.json();
      for (const q of Array.isArray(data?.quotes) ? data.quotes : []) {
        if (!q?.symbol || !q?.found || !(q.price > 0)) continue;
        marks[q.symbol.toUpperCase()] = {
          price: q.price,
          currency: q.currency || 'USD',
          timestamp: now,
          source: 'jdds',
        };
        if (q.currency && q.currency !== 'USD') currencies.add(q.currency);
      }
    }
  } catch {
    /* marks stay sparse — the engine reports the gap honestly */
  }
  if (currencies.size > 0) {
    try {
      const res = await fetch('/api/forex', { signal: AbortSignal.timeout(8000) });
      const data = await res.json();
      for (const p of Array.isArray(data?.pairs) ? data.pairs : []) {
        if (p?.base === 'USD' && p?.found && p.price > 0 && currencies.has(p.quote)) {
          (marks as Record<string, unknown>)[`USD/${p.quote}`] = { rate: p.price, timestamp: now, source: 'jdds' };
        }
      }
    } catch {
      /* missing FX is reported by the engine */
    }
  }
  return marks;
}

export function PortfolioLedger() {
  const [portfolios, setPortfolios] = useState<PortfolioSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [read, setRead] = useState<PortfolioRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState('');
  const [newMethod, setNewMethod] = useState<'FIFO' | 'LIFO' | 'AVERAGE_COST'>('FIFO');
  const [lots, setLots] = useState<TaxLotsResult | null>(null);
  const [plan, setPlan] = useState<RebalanceResult | null>(null);
  const [form, setForm] = useState({ symbol: '', quantity: '', price: '' });
  const [risk, setRisk] = useState<{ risk?: Record<string, unknown>; performance?: Record<string, unknown> } | null>(null);
  const [optim, setOptim] = useState<Record<string, unknown> | null>(null);
  const [hedgeResult, setHedgeResult] = useState<Record<string, unknown> | null>(null);
  const [recon, setRecon] = useState<Record<string, unknown> | null>(null);
  const [reconText, setReconText] = useState('[]');

  const loadPortfolios = useCallback(async () => {
    try {
      const data = await api<{ portfolios: PortfolioSummary[] }>('/list');
      const list = data.portfolios ?? [];
      setPortfolios(list);
      setSelected((prev) => prev ?? list[0]?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to load portfolios');
      setPortfolios([]);
    }
  }, []);

  useEffect(() => {
    void loadPortfolios();
  }, [loadPortfolios]);

  const refresh = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const base = await api<PortfolioRead>(`/${encodeURIComponent(id)}/query`, {
        method: 'POST',
        body: JSON.stringify({ include: ['positions', 'cash', 'pnl', 'allocation', 'exposure'] }),
      });
      const marks = await buildMarks(base.positions.map((p) => p.symbol));
      const withMarks = await api<PortfolioRead>(`/${encodeURIComponent(id)}/query`, {
        method: 'POST',
        body: JSON.stringify({ include: ['positions', 'cash', 'pnl', 'allocation', 'exposure'], marks }),
      });
      setRead(withMarks);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to read portfolio');
      setRead(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selected) void refresh(selected);
  }, [selected, refresh]);

  const onCreate = async () => {
    if (!newName.trim()) return;
    try {
      const created = await api<PortfolioSummary>('/create', {
        method: 'POST',
        body: JSON.stringify({ name: newName.trim(), costBasisMethod: newMethod }),
      });
      setNewName('');
      await loadPortfolios();
      setSelected(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'create failed');
    }
  };

  const onAdd = async () => {
    if (!selected || !form.symbol || !form.quantity) return;
    try {
      const out = await api<{ status: string; error?: { message: string } }>(
        `/${encodeURIComponent(selected)}/position`,
        {
          method: 'POST',
          body: JSON.stringify({
            symbol: form.symbol.trim().toUpperCase(),
            quantity: form.quantity,
            price: form.price || undefined,
          }),
        },
      );
      if (out.status === 'FAILED') {
        setError(out.error?.message ?? 'add failed');
      } else {
        setForm({ symbol: '', quantity: '', price: '' });
        await refresh(selected);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'add failed');
    }
  };

  const onLoadLots = async () => {
    if (!selected) return;
    try {
      setLots(await api<TaxLotsResult>(`/${encodeURIComponent(selected)}/tax-lots`));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'tax lots failed');
    }
  };

  const onRebalance = async () => {
    if (!selected || !read) return;
    const targets: Record<string, number> = {};
    const eq = read.positions.length ? 1 / read.positions.length : 0;
    for (const p of read.positions) targets[p.symbol] = eq;
    try {
      const marks = await buildMarks(read.positions.map((p) => p.symbol));
      setPlan(
        await api<RebalanceResult>(`/${encodeURIComponent(selected)}/rebalance`, {
          method: 'POST',
          body: JSON.stringify({ target: targets, allowed_drift: 0.05, marks }),
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'rebalance failed');
    }
  };

  const onDelete = async () => {
    if (!selected) return;
    try {
      await api(`/${encodeURIComponent(selected)}`, { method: 'DELETE' });
      setSelected(null);
      setRead(null);
      setLots(null);
      setPlan(null);
      await loadPortfolios();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'delete failed');
    }
  };

  const onRisk = async () => {
    if (!selected) return;
    try {
      setRisk(await api(`/${encodeURIComponent(selected)}/query`, {
        method: 'POST',
        body: JSON.stringify({ include: ['risk', 'performance'] }),
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'risk failed');
    }
  };

  const onOptimize = async () => {
    if (!selected) return;
    try {
      setOptim(await api(`/${encodeURIComponent(selected)}/optimize`, {
        method: 'POST',
        body: JSON.stringify({ method: 'min_variance' }),
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'optimizer failed');
    }
  };

  const onHedge = async () => {
    if (!selected || !read) return;
    try {
      const marks = await buildMarks(read.positions.map((p) => p.symbol));
      setHedgeResult(await api(`/${encodeURIComponent(selected)}/hedge`, {
        method: 'POST',
        body: JSON.stringify({ marks, target_flat: true }),
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'hedge failed');
    }
  };

  const onReconcile = async () => {
    if (!selected) return;
    try {
      const external = JSON.parse(reconText || '[]');
      setRecon(await api(`/${encodeURIComponent(selected)}/reconcile`, {
        method: 'POST',
        body: JSON.stringify({ external_positions: external }),
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'reconcile failed');
    }
  };

  const dq = read?.dataQuality;
  const warnings = useMemo(() => {
    if (!dq) return [];
    const out: string[] = [];
    if (dq.missingPrices.length) out.push(`Missing prices: ${dq.missingPrices.join(', ')}`);
    if (dq.stalePrices.length) out.push(`Stale prices: ${dq.stalePrices.map((s) => `${s.symbol} (${s.freshness})`).join(', ')}`);
    if (dq.missingFX.length) out.push(`Missing FX: ${dq.missingFX.join(', ')}`);
    return out.concat(dq.warnings ?? []);
  }, [dq]);

  return (
    <div className="flex h-full w-full flex-col gap-4 overflow-y-auto p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold text-foreground">Accounting Ledger</h2>
        <select
          className="glass-card-subtle rounded-md px-3 py-1.5 text-sm"
          value={selected ?? ''}
          onChange={(e) => setSelected(e.target.value || null)}
        >
          <option value="">Select a portfolio…</option>
          {(portfolios ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} · {p.costBasisMethod} · {p.baseCurrency}
            </option>
          ))}
        </select>
        <input
          className="glass-card-subtle rounded-md px-3 py-1.5 text-sm"
          placeholder="New portfolio name"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <select
          className="glass-card-subtle rounded-md px-3 py-1.5 text-sm"
          value={newMethod}
          onChange={(e) => setNewMethod(e.target.value as typeof newMethod)}
        >
          <option value="FIFO">FIFO</option>
          <option value="LIFO">LIFO</option>
          <option value="AVERAGE_COST">Average cost</option>
        </select>
        <button className="glass-card-strong rounded-md px-3 py-1.5 text-sm" onClick={onCreate}>
          Create
        </button>
        {selected && (
          <button className="glass-card-subtle rounded-md px-3 py-1.5 text-sm text-red-400" onClick={onDelete}>
            Delete
          </button>
        )}
        {loading && <span className="text-xs text-muted-foreground">loading…</span>}
      </div>

      {error && <div className="glass-card-subtle rounded-md px-3 py-2 text-sm text-red-400">{error}</div>}

      {warnings.length > 0 && (
        <div className="glass-card-subtle rounded-md border border-amber-500/40 px-3 py-2 text-xs text-amber-300">
          <div className="font-semibold">Data quality: {dq?.status}</div>
          <ul className="mt-1 list-disc pl-4">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {read && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Total value" value={`${fmt(read.valuation.totalValue)} ${read.valuation.baseCurrency}`} />
            <Stat label="Cash" value={fmt(read.valuation.cash)} />
            <Stat label="Realized P&L" value={fmt(read.pnl?.realizedPnl)} />
            <Stat label="Unrealized P&L" value={fmt(read.pnl?.unrealizedPnl)} />
          </div>

          <section className="glass-card rounded-lg p-4">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold">Positions</h3>
              <span className="text-xs text-muted-foreground">{read.positions.length} open</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr className="text-left">
                    <th className="py-1">Symbol</th>
                    <th>Qty</th>
                    <th>Avg cost</th>
                    <th>Price</th>
                    <th>Value</th>
                    <th>Unreal. P&L</th>
                    <th>Weight</th>
                    <th>Freshness</th>
                  </tr>
                </thead>
                <tbody>
                  {read.positions.map((p) => (
                    <tr key={p.symbol} className="border-t border-white/5">
                      <td className="py-1 font-medium">{p.symbol}</td>
                      <td>{fmt(p.quantity, 4)}</td>
                      <td>{fmt(p.averageCost)}</td>
                      <td>{fmt(p.price)}</td>
                      <td>{fmt(p.marketValueBase)}</td>
                      <td className={Number(p.unrealizedPnlBase) >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                        {fmt(p.unrealizedPnlBase)}
                      </td>
                      <td>{p.weight === null ? '—' : `${p.weight.toFixed(2)}%`}</td>
                      <td className={freshnessTone[p.priceFreshness] ?? ''}>{p.priceFreshness}</td>
                    </tr>
                  ))}
                  {read.positions.length === 0 && (
                    <tr>
                      <td colSpan={8} className="py-3 text-center text-xs text-muted-foreground">
                        No open positions.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {read.allocation?.assetClass && (
            <section className="glass-card rounded-lg p-4">
              <h3 className="mb-2 text-sm font-semibold">Allocation by asset class</h3>
              <div className="space-y-2">
                {read.allocation.assetClass.breakdown.map((b) => (
                  <div key={b.key} className="flex items-center gap-3 text-sm">
                    <span className="w-32 truncate">{b.key}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/10">
                      <div className="h-full rounded-full bg-sky-500/70" style={{ width: `${b.weight ?? 0}%` }} />
                    </div>
                    <span className="w-16 text-right">{b.weight === null ? '—' : `${b.weight.toFixed(1)}%`}</span>
                    <span className="w-24 text-right text-muted-foreground">{fmt(b.value)}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="glass-card rounded-lg p-4">
            <h3 className="mb-2 text-sm font-semibold">Add position</h3>
            <div className="flex flex-wrap gap-2">
              <input
                className="glass-card-subtle rounded-md px-3 py-1.5 text-sm"
                placeholder="Symbol"
                value={form.symbol}
                onChange={(e) => setForm((f) => ({ ...f, symbol: e.target.value }))}
              />
              <input
                className="glass-card-subtle rounded-md px-3 py-1.5 text-sm"
                placeholder="Quantity"
                value={form.quantity}
                onChange={(e) => setForm((f) => ({ ...f, quantity: e.target.value }))}
              />
              <input
                className="glass-card-subtle rounded-md px-3 py-1.5 text-sm"
                placeholder="Price (optional)"
                value={form.price}
                onChange={(e) => setForm((f) => ({ ...f, price: e.target.value }))}
              />
              <button className="glass-card-strong rounded-md px-3 py-1.5 text-sm" onClick={onAdd}>
                Add BUY
              </button>
              <button className="glass-card-subtle rounded-md px-3 py-1.5 text-sm" onClick={onLoadLots}>
                Load tax lots
              </button>
              <button className="glass-card-subtle rounded-md px-3 py-1.5 text-sm" onClick={onRebalance}>
                Propose rebalance
              </button>
            </div>
          </section>

          {lots && (
            <section className="glass-card rounded-lg p-4">
              <h3 className="mb-2 text-sm font-semibold">Tax lots ({lots.method})</h3>
              {lots.symbols.map((s) => (
                <div key={s.symbol} className="mb-2">
                  <div className="text-sm">
                    {s.symbol}: qty {fmt(s.remainingQuantity, 4)} · cost basis {fmt(s.remainingCostBasis)} · realized{' '}
                    {fmt(s.realizedPnl)}
                  </div>
                  <ul className="ml-4 list-disc text-xs text-muted-foreground">
                    {s.openLots.map((l) => (
                      <li key={l.id}>
                        {fmt(l.quantity, 4)} @ {fmt(l.costPerUnit)} (acquired {l.openedAt?.slice(0, 10)})
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </section>
          )}

          {plan && (
            <section className="glass-card rounded-lg p-4">
              <h3 className="mb-2 text-sm font-semibold">Rebalance proposal · {plan.method}</h3>
              <p className="mb-2 text-xs text-muted-foreground">{plan.execution}</p>
              <table className="w-full text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr className="text-left">
                    <th className="py-1">Symbol</th>
                    <th>Action</th>
                    <th>Qty</th>
                    <th>Est. value</th>
                    <th>Est. fees</th>
                    <th>Tax impact</th>
                  </tr>
                </thead>
                <tbody>
                  {plan.recommendations.map((r) => (
                    <tr key={r.symbol} className="border-t border-white/5">
                      <td className="py-1 font-medium">{r.symbol}</td>
                      <td className={r.action === 'BUY' ? 'text-emerald-400' : 'text-red-400'}>{r.action}</td>
                      <td>{fmt(r.quantity, 4)}</td>
                      <td>{fmt(r.estimatedValue)}</td>
                      <td>{fmt(r.estFees)}</td>
                      <td>{r.taxImpact ? fmt(r.taxImpact) : 'unknown'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          <section className="glass-card rounded-lg p-4">
            <h3 className="mb-2 text-sm font-semibold">Advanced analytics</h3>
            <div className="flex flex-wrap gap-2">
              <button className="glass-card-subtle rounded-md px-3 py-1.5 text-sm" onClick={onRisk}>
                Risk &amp; performance
              </button>
              <button className="glass-card-subtle rounded-md px-3 py-1.5 text-sm" onClick={onOptimize}>
                Optimize (min-variance)
              </button>
              <button className="glass-card-subtle rounded-md px-3 py-1.5 text-sm" onClick={onHedge}>
                Currency hedge
              </button>
            </div>

            {read.pnl && (read.pnl.bySector?.length ?? 0) > 0 && (
              <div className="mt-3 text-xs">
                <div className="font-semibold">P&amp;L by sector</div>
                {read.pnl.bySector!.map((s) => (
                  <div key={s.key} className="flex justify-between text-muted-foreground">
                    <span>{s.key}</span>
                    <span>{fmt(s.totalPnl)}</span>
                  </div>
                ))}
              </div>
            )}

            {risk?.risk && (
              <div className="mt-3 text-xs text-muted-foreground">
                <div className="font-semibold text-foreground">Risk</div>
                status {String((risk.risk as Record<string, unknown>).status)} · vol{' '}
                {fmt((risk.risk as { metrics?: Record<string, unknown> }).metrics?.volatility as number)} · sharpe{' '}
                {fmt((risk.risk as { metrics?: Record<string, unknown> }).metrics?.sharpe as number)} · maxDD{' '}
                {fmt((risk.risk as { metrics?: Record<string, unknown> }).metrics?.maxDrawdown as number)}
              </div>
            )}

            {optim && (
              <div className="mt-3 text-xs">
                <div className="font-semibold">Optimizer targets ({String(optim.method)})</div>
                {Object.entries((optim.weights as Record<string, number>) ?? {}).map(([sym, w]) => (
                  <div key={sym} className="flex justify-between text-muted-foreground">
                    <span>{sym}</span>
                    <span>{(Number(w) * 100).toFixed(2)}%</span>
                  </div>
                ))}
                <div className="text-muted-foreground">vol {fmt(optim.volatility as number, 4)} · turnover {fmt(optim.turnover as number, 4)}</div>
              </div>
            )}

            {hedgeResult && (
              <div className="mt-3 text-xs">
                <div className="font-semibold">Currency hedge proposals</div>
                {((hedgeResult.proposals as Array<Record<string, unknown>>) ?? []).map((h) => (
                  <div key={String(h.currency)} className="text-muted-foreground">
                    {String(h.currency)}: {String(h.direction)} {fmt(h.hedgeNotionalBase as string)}
                  </div>
                ))}
                {((hedgeResult.proposals as unknown[]) ?? []).length === 0 && (
                  <div className="text-muted-foreground">No non-base currency exposure.</div>
                )}
              </div>
            )}

            <div className="mt-4">
              <div className="mb-1 text-xs font-semibold">Reconciliation (external positions JSON)</div>
              <textarea
                className="glass-card-subtle h-20 w-full rounded-md px-3 py-2 font-mono text-xs"
                value={reconText}
                onChange={(e) => setReconText(e.target.value)}
              />
              <div className="mt-2 flex items-center gap-2">
                <button className="glass-card-strong rounded-md px-3 py-1.5 text-sm" onClick={onReconcile}>
                  Reconcile
                </button>
                {recon && <span className="text-xs text-muted-foreground">status: {String(recon.status)}</span>}
              </div>
              {recon && (
                <table className="mt-2 w-full text-xs">
                  <tbody>
                    {((recon.items as Array<Record<string, unknown>>) ?? []).slice(0, 20).map((it) => (
                      <tr key={String(it.symbol)} className="border-t border-white/5">
                        <td className="py-0.5 font-medium">{String(it.symbol)}</td>
                        <td>{String(it.internalQuantity ?? '—')}</td>
                        <td>{String(it.externalQuantity ?? '—')}</td>
                        <td className={it.status === 'MATCHED' ? 'text-emerald-400' : 'text-amber-400'}>
                          {String(it.status)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </section>
        </>
      )}

      {!read && !error && portfolios !== null && (
        <div className="glass-card-subtle rounded-md px-3 py-6 text-center text-sm text-muted-foreground">
          {portfolios.length === 0
            ? 'Create a portfolio to begin tracking positions and tax lots.'
            : 'Select a portfolio to view its ledger.'}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="glass-card rounded-lg p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-base font-semibold">{value}</div>
    </div>
  );
}

export default PortfolioLedger;
