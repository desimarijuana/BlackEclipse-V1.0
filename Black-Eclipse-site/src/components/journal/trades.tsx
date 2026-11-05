'use client';

// ── Journal Trades — trade list + fast add + delete ──────────────────────────
// Adding a trade uses the shared QuickAddTrade dialog (one entry point for the
// whole Journal) instead of a divergent inline form. Derived metrics (P&L, R,
// risk, duration) are computed server-side on save.
//
// This screen owns the journal's advanced list controls: multi-dimension
// filtering, column sorting, pagination and CSV/PDF export. Filtering is
// client-side over the already-loaded trade set so it stays instant and the
// analytics fetch remains a single source of truth.

import React, { useEffect, useMemo, useState, useRef } from 'react';
import { usePageShortcuts } from '@/hooks/use-page-shortcuts';
import { useListNavigation } from '@/hooks/use-list-navigation';
import { Plus, Trash2, Download, FileText, ChevronLeft, ChevronRight, SlidersHorizontal, ArrowUp, ArrowDown } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { BrokerSyncButton } from './broker-sync-button';
import type { TradeRecord } from '@/lib/journal/types';
import { isRMeasurable, classifyTradeOutcome } from '@/lib/journal/trade-math';
import { fmtPrice, fmtDateTime } from '@/lib/journal/format';
import { fmtR, fmtMoney } from './charts/echarts-container';
import { TradeDetail } from './trade-detail';
import { QuickAddTrade } from './quick-add-trade';

interface TradesProps {
  trades: TradeRecord[];
  analytics: unknown;
  onChanged: () => void;
  selectedDate?: string | null;
}

type SortKey = 'exitTime' | 'symbol' | 'entry' | 'exit' | 'rMultiple' | 'pnl';
type ResultFilter = 'all' | 'win' | 'loss' | 'breakeven';
const PAGE_SIZE = 25;

interface RefOption { id: string; name: string }

export function JournalTrades({ trades, onChanged, selectedDate }: TradesProps) {
  const [adding, setAdding] = useState(false);
  const [detailTrade, setDetailTrade] = useState<TradeRecord | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [exporting, setExporting] = useState(false);

  const [strategies, setStrategies] = useState<RefOption[]>([]);
  const [setups, setSetups] = useState<RefOption[]>([]);
  const [tags, setTags] = useState<RefOption[]>([]);
  const [accounts, setAccounts] = useState<RefOption[]>([]);

  const [symbol, setSymbol] = useState('');
  const [strategyId, setStrategyId] = useState('');
  const [setupId, setSetupId] = useState('');
  const [accountId, setAccountId] = useState('');
  const [tagName, setTagName] = useState('');
  const [emotion, setEmotion] = useState('');
  const [session, setSession] = useState('');
  const [direction, setDirection] = useState('');
  const [result, setResult] = useState<ResultFilter>('all');
  const [source, setSource] = useState<'all' | 'broker' | 'manual' | 'demo'>('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const [sortKey, setSortKey] = useState<SortKey>('exitTime');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(1);

  useEffect(() => {
    void (async () => {
      const [sRes, suRes, tRes, aRes] = await Promise.all([
        fetch('/api/journal/strategies'),
        fetch('/api/journal/setups'),
        fetch('/api/journal/tags'),
        fetch('/api/journal/accounts'),
      ]);
      const [sData, suData, tData, aData] = await Promise.all([sRes.json(), suRes.json(), tRes.json(), aRes.json()]);
      setStrategies(sData.strategies ?? []);
      setSetups(suData.setups ?? []);
      setTags(tData.tags ?? []);
      setAccounts(aData.accounts ?? []);
    })();
  }, []);

  // A day selected in the Calendar opens the quick-add dialog pre-filled.
  useEffect(() => {
    if (selectedDate) setAdding(true);
  }, [selectedDate]);

  const filtered = useMemo(() => {
    const sym = symbol.trim().toLowerCase();
    const from = dateFrom ? Date.parse(dateFrom + 'T00:00:00') : null;
    const to = dateTo ? Date.parse(dateTo + 'T23:59:59') : null;
    const rows = trades.filter((t) => {
      if (sym && !t.symbol.toLowerCase().includes(sym)) return false;
      if (strategyId && t.strategyId !== strategyId) return false;
      if (setupId && t.setupId !== setupId) return false;
      if (accountId && t.accountId !== accountId) return false;
      if (tagName && !(t.tags ?? []).includes(tagName)) return false;
      if (emotion && t.emotion !== emotion) return false;
      if (session && t.session !== session) return false;
      if (direction && t.direction !== direction) return false;
      if (source !== 'all' && (t.source ?? 'manual') !== source) return false;
      if (result !== 'all') {
        if (t.status === 'open') return false;
        if (classifyTradeOutcome(t) !== result) return false;
      }
      const ts = Date.parse(t.exitTime);
      if (from != null && ts < from) return false;
      if (to != null && ts > to) return false;
      return true;
    });
    const dir = sortDir === 'asc' ? 1 : -1;
    return rows.sort((a, b) => {
      let av: number | string;
      let bv: number | string;
      if (sortKey === 'exitTime') { av = Date.parse(a.exitTime); bv = Date.parse(b.exitTime); }
      else if (sortKey === 'symbol') { av = a.symbol; bv = b.symbol; }
      else { av = a[sortKey] ?? 0; bv = b[sortKey] ?? 0; }
      if (typeof av === 'string' && typeof bv === 'string') return av.localeCompare(bv) * dir;
      return ((av as number) - (bv as number)) * dir;
    });
  }, [trades, symbol, strategyId, setupId, accountId, tagName, emotion, session, direction, source, result, dateFrom, dateTo, sortKey, sortDir]);

  // Reset to page 1 whenever the filter/sort changes.
  useEffect(() => { setPage(1); }, [filtered.length, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = useMemo(
    () => filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [filtered, page],
  );

  const emotions = useMemo(() => [...new Set(trades.map((t) => t.emotion).filter(Boolean))] as string[], [trades]);
  const sessions = useMemo(() => [...new Set(trades.map((t) => t.session).filter(Boolean))] as string[], [trades]);

  const activeFilterCount = [symbol, strategyId, setupId, accountId, tagName, emotion, session, direction, dateFrom, dateTo].filter(Boolean).length + (result !== 'all' ? 1 : 0) + (source !== 'all' ? 1 : 0);
  const clearFilters = () => {
    setSymbol(''); setStrategyId(''); setSetupId(''); setAccountId(''); setTagName('');
    setEmotion(''); setSession(''); setDirection(''); setResult('all'); setSource('all'); setDateFrom(''); setDateTo('');
  };

  const remove = async (id: string) => {
    if (!confirm('Delete this trade?')) return;
    const res = await fetch(`/api/journal/trades/${id}`, { method: 'DELETE' });
    if (res.ok) onChanged();
  };

  const exportCsv = () => {
    window.location.href = '/api/journal/export';
  };
  const exportPdf = async () => {
    setExporting(true);
    try {
      const { tradesToPdf } = await import('@/lib/journal/pdf');
      await tradesToPdf(filtered);
    } finally {
      setExporting(false);
    }
  };

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir(key === 'symbol' ? 'asc' : 'desc'); }
  };

  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const startAdding = () => setAdding(true);
  const tradeIds = useMemo(() => pageRows.map((t) => t.id), [pageRows]);
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
    { id: 'trades.filters', label: 'Toggle filters', keys: 'Shift+F', run: () => setShowFilters((v) => !v), enabled: !detailTrade },
  ]);

  const selectCls = 'rounded-lg bg-background/60 border border-border/40 px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-primary outline-none';

  return (
    <div ref={rootRef} data-keyboard-scope="Journal trades" className="flex flex-col gap-5">
      {/* Header + controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-serif text-lg font-semibold text-foreground">Trades</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {filtered.length} of {trades.length}{activeFilterCount > 0 && <span className="text-primary"> · {activeFilterCount} filter{activeFilterCount > 1 ? 's' : ''}</span>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={searchRef}
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="Filter by symbol…"
            className="w-36 rounded-lg bg-background/60 border border-border/40 px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-primary outline-none"
          />
          <button
            onClick={() => setShowFilters((v) => !v)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition-all cursor-pointer',
              showFilters || activeFilterCount > 0 ? 'border-primary/40 bg-primary/10 text-primary' : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:text-foreground',
            )}
          >
            <SlidersHorizontal size={13} /> Filters{activeFilterCount > 0 ? ` (${activeFilterCount})` : ''}
          </button>
          <button
            onClick={exportCsv}
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition-all cursor-pointer"
            title="Export CSV"
          >
            <Download size={13} /> CSV
          </button>
          <button
            onClick={() => void exportPdf()}
            disabled={exporting || filtered.length === 0}
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition-all cursor-pointer disabled:opacity-50"
            title="Export PDF"
          >
            <FileText size={13} /> {exporting ? 'Building…' : 'PDF'}
          </button>
          <BrokerSyncButton onSynced={onChanged} />
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

      {/* Advanced filters */}
      {showFilters && (
        <div className="rounded-2xl glass-card p-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            <Filter label="Strategy">
              <select value={strategyId} onChange={(e) => setStrategyId(e.target.value)} className={cn(selectCls, 'w-full')}>
                <option value="">All</option>
                {strategies.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </Filter>
            <Filter label="Setup">
              <select value={setupId} onChange={(e) => setSetupId(e.target.value)} className={cn(selectCls, 'w-full')}>
                <option value="">All</option>
                {setups.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </Filter>
            <Filter label="Account">
              <select value={accountId} onChange={(e) => setAccountId(e.target.value)} className={cn(selectCls, 'w-full')}>
                <option value="">All</option>
                {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </Filter>
            <Filter label="Tag">
              <select value={tagName} onChange={(e) => setTagName(e.target.value)} className={cn(selectCls, 'w-full')}>
                <option value="">All</option>
                {tags.map((t) => <option key={t.id} value={t.name}>{t.name}</option>)}
              </select>
            </Filter>
            <Filter label="Emotion">
              <select value={emotion} onChange={(e) => setEmotion(e.target.value)} className={cn(selectCls, 'w-full')}>
                <option value="">All</option>
                {emotions.map((e2) => <option key={e2} value={e2}>{e2}</option>)}
              </select>
            </Filter>
            <Filter label="Session">
              <select value={session} onChange={(e) => setSession(e.target.value)} className={cn(selectCls, 'w-full')}>
                <option value="">All</option>
                {sessions.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Filter>
            <Filter label="Direction">
              <select value={direction} onChange={(e) => setDirection(e.target.value)} className={cn(selectCls, 'w-full')}>
                <option value="">All</option>
                <option value="LONG">LONG</option>
                <option value="SHORT">SHORT</option>
              </select>
            </Filter>
            <Filter label="Result">
              <select value={result} onChange={(e) => setResult(e.target.value as ResultFilter)} className={cn(selectCls, 'w-full')}>
                <option value="all">All</option>
                <option value="win">Wins</option>
                <option value="loss">Losses</option>
                <option value="breakeven">Breakeven</option>
              </select>
            </Filter>
            <Filter label="Source">
              <select
                value={source}
                onChange={(e) => setSource(e.target.value as 'all' | 'broker' | 'manual' | 'demo')}
                className={cn(selectCls, 'w-full')}
              >
                <option value="all">All</option>
                <option value="broker">Broker</option>
                <option value="manual">Manual / CSV</option>
                <option value="demo">Demo</option>
              </select>
            </Filter>
            <Filter label="From">
              <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className={cn(selectCls, 'w-full')} />
            </Filter>
            <Filter label="To">
              <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className={cn(selectCls, 'w-full')} />
            </Filter>
          </div>
          <div className="mt-3 flex justify-end">
            <button onClick={clearFilters} className="text-[11px] font-semibold text-muted-foreground hover:text-foreground cursor-pointer">Clear all</button>
          </div>
        </div>
      )}

      {/* Trade table */}
      <div className="rounded-2xl glass-card overflow-hidden">
        {filtered.length === 0 ? (
          <p className="p-8 text-center text-xs text-muted-foreground italic">No trades{activeFilterCount > 0 ? ' match your filters' : ' yet'}.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="sticky top-0 bg-[#0f0f0f]/95 border-b border-white/10">
                <tr>
                  {([
                    ['Date / time', 'exitTime'], ['Symbol', 'symbol'], ['Dir', null], ['Entry', 'entry'], ['Exit', 'exit'],
                    ['R', 'rMultiple'], ['P&L', 'pnl'], ['Session', null], ['Setup', null], ['Emotion', null], ['', null],
                  ] as [string, SortKey | null][]).map(([h, key]) => (
                    <th key={h} className="px-3 py-2 text-[9px] uppercase tracking-widest text-muted-foreground font-bold">
                      {key ? (
                        <button onClick={() => toggleSort(key)} className="inline-flex items-center gap-1 hover:text-foreground cursor-pointer">
                          {h}
                          {sortKey === key && (sortDir === 'asc' ? <ArrowUp size={10} /> : <ArrowDown size={10} />)}
                        </button>
                      ) : h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pageRows.map((t) => (
                  <tr
                    key={t.id}
                    {...listNav.rowAttributes(t.id)}
                    onClick={() => setDetailTrade(t)}
                    className={cn('border-b border-white/5 last:border-0 hover:bg-white/[0.03] cursor-pointer', listNav.isSelected(t.id) && 'bg-primary/10 ring-1 ring-inset ring-primary/40')}
                  >
                    <td className="px-3 py-2 text-muted-foreground whitespace-nowrap">{fmtDateTime(t.exitTime)}</td>
                    <td className="px-3 py-2 font-bold text-foreground">
                      {t.symbol}
                      {t.source === 'broker' && (
                        <span className="ml-1.5 rounded border border-primary/25 bg-primary/10 px-1 py-0.5 align-middle font-mono text-[8px] font-bold tracking-widest text-primary">
                          BROKER
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">{t.direction === 'LONG' ? <span className="text-emerald-400">LONG</span> : <span className="text-rose-400">SHORT</span>}</td>
                    <td className="px-3 py-2 text-muted-foreground">{fmtPrice(t.entry)}</td>
                    <td className="px-3 py-2 text-muted-foreground">{t.status === 'open' ? '—' : fmtPrice(t.exit)}</td>
                    <td className={cn('px-3 py-2 font-bold', !isRMeasurable(t) ? 'text-muted-foreground/50' : t.rMultiple >= 0 ? 'text-emerald-400' : 'text-rose-400')}>{isRMeasurable(t) ? fmtR(t.rMultiple) : '—'}</td>
                    <td className={cn('px-3 py-2 font-bold', t.status === 'open' ? 'text-muted-foreground/70' : t.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400')}>{t.status === 'open' ? 'open' : fmtMoney(t.pnl)}</td>
                    <td className="px-3 py-2 text-muted-foreground">{t.session ?? '—'}</td>
                    <td className="px-3 py-2 text-muted-foreground">{t.setupName ?? '—'}</td>
                    <td className="px-3 py-2 text-muted-foreground">{t.emotion ?? '—'}</td>
                    <td className="px-3 py-2">
                      <button onClick={(e) => { e.stopPropagation(); void remove(t.id); }} className="text-muted-foreground hover:text-rose-400 transition-colors cursor-pointer" title="Delete">
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {filtered.length > PAGE_SIZE && (
          <div className="flex items-center justify-between border-t border-white/10 px-3 py-2 text-[11px] text-muted-foreground font-mono">
            <span>Page {page} of {totalPages}</span>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/[0.03] px-2 py-1 hover:text-foreground disabled:opacity-40 cursor-pointer disabled:cursor-default"
              >
                <ChevronLeft size={12} /> Prev
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/[0.03] px-2 py-1 hover:text-foreground disabled:opacity-40 cursor-pointer disabled:cursor-default"
              >
                Next <ChevronRight size={12} />
              </button>
            </div>
          </div>
        )}
      </div>

      {detailTrade && (
        <TradeDetail trade={detailTrade} allTrades={trades} onClose={() => setDetailTrade(null)} onChanged={onChanged} />
      )}
    </div>
  );
}

function Filter({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}
