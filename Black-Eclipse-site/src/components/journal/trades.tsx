'use client';

// ── Journal Trades — trade list + fast add + delete ──────────────────────────
// Adding a trade uses the shared QuickAddTrade dialog (one entry point for the
// whole Journal) instead of a divergent inline form. Derived metrics (P&L, R,
// risk, duration) are computed server-side on save.

import React, { useEffect, useMemo, useState, useRef } from 'react';
import { usePageShortcuts } from '@/hooks/use-page-shortcuts';
import { useListNavigation } from '@/hooks/use-list-navigation';
import { Plus, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TradeRecord } from '@/lib/journal/types';
import { fmtR, fmtMoney } from './charts/echarts-container';
import { TradeDetail } from './trade-detail';
import { QuickAddTrade } from './quick-add-trade';

interface TradesProps {
  trades: TradeRecord[];
  analytics: unknown;
  onChanged: () => void;
  selectedDate?: string | null;
}

export function JournalTrades({ trades, onChanged, selectedDate }: TradesProps) {
  const [adding, setAdding] = useState(false);
  const [filter, setFilter] = useState('');
  const [detailTrade, setDetailTrade] = useState<TradeRecord | null>(null);

  // A day selected in the Calendar opens the quick-add dialog pre-filled.
  useEffect(() => {
    if (selectedDate) setAdding(true);
  }, [selectedDate]);

  const sorted = useMemo(
    () => [...trades].sort((a, b) => Date.parse(b.exitTime) - Date.parse(a.exitTime)),
    [trades],
  );
  const filtered = useMemo(
    () => (filter ? sorted.filter((t) => t.symbol.toLowerCase().includes(filter.toLowerCase())) : sorted),
    [sorted, filter],
  );

  const remove = async (id: string) => {
    if (!confirm('Delete this trade?')) return;
    const res = await fetch(`/api/journal/trades/${id}`, { method: 'DELETE' });
    if (res.ok) onChanged();
  };

  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const startAdding = () => setAdding(true);
  const tradeIds = useMemo(() => filtered.map((t) => t.id), [filtered]);
  const listNav = useListNavigation({
    ids: adding ? [] : tradeIds,
    rootRef,
    enabled: !adding && !detailTrade,
    shortcutPrefix: 'trades.list',
    onOpen: (id) => {
      const trade = filtered.find((t) => t.id === id);
      if (trade) setDetailTrade(trade);
    },
  });
  usePageShortcuts(rootRef, [
    { id: 'trades.new', label: 'Add trade', keys: 'Shift+N', run: startAdding, enabled: !adding && !detailTrade },
    { id: 'trades.search', label: 'Search trades', keys: 'S', run: () => searchRef.current?.focus(), enabled: !detailTrade },
    { id: 'trades.filter', label: 'Filter by symbol', keys: 'Shift+F', run: () => searchRef.current?.focus(), enabled: !detailTrade },
  ]);

  return (
    <div ref={rootRef} data-keyboard-scope="Journal trades" className="flex flex-col gap-5">
      {/* Header + Add button */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-serif text-lg font-semibold text-foreground">Trades</h2>
          <p className="text-xs text-muted-foreground mt-0.5">{trades.length} total</p>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={searchRef}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter by symbol…"
            className="w-40 rounded-lg bg-background/60 border border-border/40 px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-primary outline-none"
          />
          <button
            onClick={startAdding}
            className="inline-flex items-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 text-primary px-3 py-1.5 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer"
          >
            <Plus size={13} /> Add Trade
          </button>
          <QuickAddTrade
            onAdded={onChanged}
            defaultDate={selectedDate ?? undefined}
            open={adding}
            onOpenChange={setAdding}
            trigger={false}
          />
        </div>
      </div>

      {/* Trade table */}
      <div className="rounded-2xl glass-card overflow-hidden">
        {filtered.length === 0 ? (
          <p className="p-8 text-center text-xs text-muted-foreground italic">No trades{filter ? ' match your filter' : ' yet'}.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="sticky top-0 bg-[#0f0f0f]/95 border-b border-white/10">
                <tr>
                  {['Date', 'Symbol', 'Dir', 'Entry', 'Exit', 'R', 'P&L', 'Session', 'Setup', 'Emotion', ''].map((h) => (
                    <th key={h} className="px-3 py-2 text-[9px] uppercase tracking-widest text-muted-foreground font-bold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((t) => (
                  <tr
                    key={t.id}
                    {...listNav.rowAttributes(t.id)}
                    onClick={() => setDetailTrade(t)}
                    className={cn('border-b border-white/5 last:border-0 hover:bg-white/[0.03] cursor-pointer', listNav.isSelected(t.id) && 'bg-primary/10 ring-1 ring-inset ring-primary/40')}
                  >
                    <td className="px-3 py-2 text-muted-foreground whitespace-nowrap">{t.exitTime.slice(0, 10)}</td>
                    <td className="px-3 py-2 font-bold text-foreground">{t.symbol}</td>
                    <td className="px-3 py-2">{t.direction === 'LONG' ? <span className="text-emerald-400">LONG</span> : <span className="text-rose-400">SHORT</span>}</td>
                    <td className="px-3 py-2 text-muted-foreground">{t.entry}</td>
                    <td className="px-3 py-2 text-muted-foreground">{t.exit}</td>
                    <td className={cn('px-3 py-2 font-bold', t.rMultiple >= 0 ? 'text-emerald-400' : 'text-rose-400')}>{fmtR(t.rMultiple)}</td>
                    <td className={cn('px-3 py-2 font-bold', t.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400')}>{fmtMoney(t.pnl)}</td>
                    <td className="px-3 py-2 text-muted-foreground">{t.session ?? '—'}</td>
                    <td className="px-3 py-2 text-muted-foreground">{t.setupName ?? '—'}</td>
                    <td className="px-3 py-2 text-muted-foreground">{t.emotion ?? '—'}</td>
                    <td className="px-3 py-2">
                      <button onClick={(e) => { e.stopPropagation(); remove(t.id); }} className="text-muted-foreground hover:text-rose-400 transition-colors cursor-pointer" title="Delete">
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {detailTrade && (
        <TradeDetail trade={detailTrade} allTrades={trades} onClose={() => setDetailTrade(null)} onChanged={onChanged} />
      )}
    </div>
  );
}
