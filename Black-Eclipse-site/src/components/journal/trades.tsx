'use client';

// ── Journal Trades — trade list + fast add + delete ──────────────────────────
// Adding a trade is a single inline form (no multi-page navigation). Derived
// metrics (P&L, R, risk, duration) are computed server-side on save.

import React, { useEffect, useMemo, useState, useRef } from 'react';
import { usePageShortcuts } from '@/hooks/use-page-shortcuts';
import { useListNavigation } from '@/hooks/use-list-navigation';
import { Plus, Trash2, X, Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TradeRecord } from '@/lib/journal/types';
import { fmtR, fmtMoney } from './charts/echarts-container';
import { TradeDetail } from './trade-detail';

interface TradesProps {
  trades: TradeRecord[];
  analytics: unknown;
  onChanged: () => void;
  selectedDate?: string | null;
}

const SESSIONS = ['Asia', 'London', 'New York', 'Sydney', 'Tokyo'];
const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d'];
const EMOTIONS = ['Calm', 'Focused', 'Confident', 'Fearful', 'FOMO', 'Revenge', 'Bored', 'Overconfident', 'Hesitant'];
const MISTAKES = ['Early exit', 'Moved stop', 'Moved target', 'Partial exit', 'Overtraded', 'Revenge', 'No stop', 'Chased entry'];

interface TradeForm {
  symbol: string;
  direction: 'LONG' | 'SHORT';
  entry: string;
  exit: string;
  stopLoss: string;
  takeProfit: string;
  quantity: string;
  entryTime: string;
  exitTime: string;
  session: string;
  timeframe: string;
  emotion: string;
  confidence: string;
  mistakes: string[];
  notes: string;
  strategyId: string;
  setupId: string;
  tagNames: string[];
}

const emptyForm = (date?: string): TradeForm => ({
  symbol: '',
  direction: 'LONG',
  entry: '',
  exit: '',
  stopLoss: '',
  takeProfit: '',
  quantity: '1',
  entryTime: `${date ?? new Date().toISOString().slice(0, 10)}T09:30`,
  exitTime: `${date ?? new Date().toISOString().slice(0, 10)}T10:00`,
  session: 'New York',
  timeframe: '15m',
  emotion: 'Calm',
  confidence: '3',
  mistakes: [],
  notes: '',
  strategyId: '',
  setupId: '',
  tagNames: [],
});

export function JournalTrades({ trades, onChanged, selectedDate }: TradesProps) {
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<TradeForm>(() => emptyForm(selectedDate ?? undefined));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const [detailTrade, setDetailTrade] = useState<TradeRecord | null>(null);
  const [strategies, setStrategies] = useState<{ id: string; name: string }[]>([]);
  const [setups, setSetups] = useState<{ id: string; name: string }[]>([]);
  const [tags, setTags] = useState<{ id: string; name: string }[]>([]);

  useEffect(() => {
    void (async () => {
      const [sRes, suRes, tRes] = await Promise.all([
        fetch('/api/journal/strategies'),
        fetch('/api/journal/setups'),
        fetch('/api/journal/tags'),
      ]);
      const sData = await sRes.json();
      const suData = await suRes.json();
      const tData = await tRes.json();
      setStrategies(sData.strategies ?? []);
      setSetups(suData.setups ?? []);
      setTags(tData.tags ?? []);
    })();
  }, []);

  useEffect(() => {
    if (selectedDate) {
      setForm(emptyForm(selectedDate));
      setAdding(true);
    }
  }, [selectedDate]);

  const sorted = useMemo(
    () => [...trades].sort((a, b) => Date.parse(b.exitTime) - Date.parse(a.exitTime)),
    [trades],
  );
  const filtered = useMemo(
    () => (filter ? sorted.filter((t) => t.symbol.toLowerCase().includes(filter.toLowerCase())) : sorted),
    [sorted, filter],
  );

  const set = (patch: Partial<TradeForm>) => setForm((f) => ({ ...f, ...patch }));

  const toggleMistake = (m: string) =>
    setForm((f) => ({
      ...f,
      mistakes: f.mistakes.includes(m) ? f.mistakes.filter((x) => x !== m) : [...f.mistakes, m],
    }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await fetch('/api/journal/trades', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: form.symbol,
          direction: form.direction,
          entry: Number(form.entry),
          exit: Number(form.exit),
          stopLoss: form.stopLoss ? Number(form.stopLoss) : null,
          takeProfit: form.takeProfit ? Number(form.takeProfit) : null,
          quantity: Number(form.quantity) || 1,
          entryTime: new Date(form.entryTime).toISOString(),
          exitTime: new Date(form.exitTime).toISOString(),
          session: form.session || null,
          timeframe: form.timeframe || null,
          emotion: form.emotion || null,
          confidence: form.confidence ? Number(form.confidence) : null,
          mistakes: form.mistakes,
          notes: form.notes || null,
          strategyId: form.strategyId || null,
          setupId: form.setupId || null,
          tagNames: form.tagNames,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to save');
      setForm(emptyForm());
      setAdding(false);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: string) => {
    if (!confirm('Delete this trade?')) return;
    const res = await fetch(`/api/journal/trades/${id}`, { method: 'DELETE' });
    if (res.ok) onChanged();
  };

  const inputCls = 'w-full rounded-lg bg-background/60 border border-border/40 hover:border-primary/50 px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-primary outline-none';

  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const startAdding = () => { setAdding(true); setForm(emptyForm()); };
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
            onClick={() => { if (adding) setAdding(false); else startAdding(); }}
            className="inline-flex items-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 text-primary px-3 py-1.5 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer"
          >
            {adding ? <X size={13} /> : <Plus size={13} />} {adding ? 'Cancel' : 'Add Trade'}
          </button>
        </div>
      </div>

      {/* Fast-add form */}
      {adding && (
        <form onSubmit={submit} className="rounded-2xl glass-card border border-primary/20 p-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            <Field label="Symbol" required>
              <input value={form.symbol} onChange={(e) => set({ symbol: e.target.value.toUpperCase() })} placeholder="XAUUSD" className={inputCls} required />
            </Field>
            <Field label="Direction">
              <select value={form.direction} onChange={(e) => set({ direction: e.target.value as 'LONG' | 'SHORT' })} className={inputCls}>
                <option value="LONG">LONG</option>
                <option value="SHORT">SHORT</option>
              </select>
            </Field>
            <Field label="Entry" required>
              <input type="number" step="any" value={form.entry} onChange={(e) => set({ entry: e.target.value })} className={inputCls} required />
            </Field>
            <Field label="Exit" required>
              <input type="number" step="any" value={form.exit} onChange={(e) => set({ exit: e.target.value })} className={inputCls} required />
            </Field>
            <Field label="Stop Loss">
              <input type="number" step="any" value={form.stopLoss} onChange={(e) => set({ stopLoss: e.target.value })} className={inputCls} />
            </Field>
            <Field label="Take Profit">
              <input type="number" step="any" value={form.takeProfit} onChange={(e) => set({ takeProfit: e.target.value })} className={inputCls} />
            </Field>
            <Field label="Quantity">
              <input type="number" step="any" value={form.quantity} onChange={(e) => set({ quantity: e.target.value })} className={inputCls} />
            </Field>
            <Field label="Session">
              <select value={form.session} onChange={(e) => set({ session: e.target.value })} className={inputCls}>
                {SESSIONS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Entry Time" required>
              <input type="datetime-local" value={form.entryTime} onChange={(e) => set({ entryTime: e.target.value })} className={inputCls} required />
            </Field>
            <Field label="Exit Time" required>
              <input type="datetime-local" value={form.exitTime} onChange={(e) => set({ exitTime: e.target.value })} className={inputCls} required />
            </Field>
            <Field label="Timeframe">
              <select value={form.timeframe} onChange={(e) => set({ timeframe: e.target.value })} className={inputCls}>
                {TIMEFRAMES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </Field>
            <Field label="Emotion">
              <select value={form.emotion} onChange={(e) => set({ emotion: e.target.value })} className={inputCls}>
                {EMOTIONS.map((em) => <option key={em} value={em}>{em}</option>)}
              </select>
            </Field>
            <Field label="Confidence (1-5)">
              <input type="number" min={1} max={5} value={form.confidence} onChange={(e) => set({ confidence: e.target.value })} className={inputCls} />
            </Field>
            <Field label="Notes">
              <input value={form.notes} onChange={(e) => set({ notes: e.target.value })} className={inputCls} />
            </Field>
            <Field label="Strategy / Playbook">
              <select value={form.strategyId} onChange={(e) => set({ strategyId: e.target.value })} className={inputCls}>
                <option value="">— None —</option>
                {strategies.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </Field>
            <Field label="Setup">
              <select value={form.setupId} onChange={(e) => set({ setupId: e.target.value })} className={inputCls}>
                <option value="">— None —</option>
                {setups.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </Field>
          </div>

          {/* Tags */}
          <div className="mt-3">
            <p className="mb-1.5 text-[9px] uppercase tracking-widest font-bold text-muted-foreground">Tags</p>
            <div className="flex flex-wrap gap-1.5">
              {tags.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setForm((f) => ({
                    ...f,
                    tagNames: f.tagNames.includes(t.name) ? f.tagNames.filter((x) => x !== t.name) : [...f.tagNames, t.name],
                  }))}
                  className={cn(
                    'rounded-lg border px-2 py-1 text-[10px] font-semibold transition-all cursor-pointer',
                    form.tagNames.includes(t.name) ? 'border-primary/40 bg-primary/15 text-primary' : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:text-foreground',
                  )}
                >
                  {t.name}
                </button>
              ))}
              {tags.length === 0 && <span className="text-[10px] text-muted-foreground/60 italic">No tags yet — create them in the Playbook tab.</span>}
            </div>
          </div>

          {/* Mistakes */}
          <div className="mt-3">
            <p className="mb-1.5 text-[9px] uppercase tracking-widest font-bold text-muted-foreground">Mistakes</p>
            <div className="flex flex-wrap gap-1.5">
              {MISTAKES.map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => toggleMistake(m)}
                  className={cn(
                    'rounded-lg border px-2 py-1 text-[10px] font-semibold transition-all cursor-pointer',
                    form.mistakes.includes(m) ? 'border-rose-500/40 bg-rose-500/10 text-rose-400' : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:text-foreground',
                  )}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>

          {error && <p className="mt-3 text-xs text-rose-400 font-semibold">{error}</p>}

          <div className="mt-4 flex items-center gap-2">
            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 text-primary px-4 py-2 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer disabled:opacity-50"
            >
              {saving ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary/30 border-t-primary" /> : <Check size={13} />}
              {saving ? 'Saving…' : 'Save Trade'}
            </button>
            <span className="text-[10px] text-muted-foreground font-mono">P&L, R-multiple, risk & duration are computed automatically.</span>
          </div>
        </form>
      )}

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

function Field({ label, children, required }: { label: string; children: React.ReactNode; required?: boolean }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{label}{required && <span className="text-rose-400"> *</span>}</span>
      {children}
    </label>
  );
}
