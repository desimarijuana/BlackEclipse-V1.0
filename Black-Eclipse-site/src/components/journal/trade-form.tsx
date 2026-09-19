'use client';

// ── TradeForm — the shared trade entry form ──────────────────────────────────
// Rendered inside `QuickAddTrade` (the Journal's single add-trade dialog), which
// is mounted once in the Journal header and reachable from every sub-tab.

import React, { useEffect, useState } from 'react';
import { Check, X } from 'lucide-react';
import { cn } from '@/lib/utils';

export const SESSIONS = ['Asia', 'London', 'New York', 'Sydney', 'Tokyo'];
export const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d'];
export const EMOTIONS = ['Calm', 'Focused', 'Confident', 'Fearful', 'FOMO', 'Revenge', 'Bored', 'Overconfident', 'Hesitant'];
export const MISTAKES = ['Early exit', 'Moved stop', 'Moved target', 'Partial exit', 'Overtraded', 'Revenge', 'No stop', 'Chased entry'];

export interface TradeFormState {
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

export const emptyTradeForm = (date?: string): TradeFormState => ({
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

interface TradeFormProps {
  form: TradeFormState;
  onChange: (patch: Partial<TradeFormState>) => void;
  onSubmit: () => Promise<void>;
  onCancel?: () => void;
  saving?: boolean;
  error?: string | null;
  submitLabel?: string;
}

export function TradeForm({ form, onChange, onSubmit, onCancel, saving, error, submitLabel = 'Save Trade' }: TradeFormProps) {
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

  const inputCls = 'w-full rounded-lg bg-background/60 border border-border/40 hover:border-primary/50 px-3 py-2 text-xs font-mono focus:ring-1 focus:ring-primary outline-none transition-colors';

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); void onSubmit(); }}
      className="rounded-2xl glass-card border border-primary/20 p-5 sm:p-6"
    >
      <div className="grid grid-cols-2 gap-x-5 gap-y-4 sm:grid-cols-3 lg:grid-cols-4">
        <Field label="Symbol" required>
          <input value={form.symbol} onChange={(e) => onChange({ symbol: e.target.value.toUpperCase() })} placeholder="XAUUSD" className={inputCls} required />
        </Field>
        <Field label="Direction">
          <select value={form.direction} onChange={(e) => onChange({ direction: e.target.value as 'LONG' | 'SHORT' })} className={inputCls}>
            <option value="LONG">LONG</option>
            <option value="SHORT">SHORT</option>
          </select>
        </Field>
        <Field label="Entry" required>
          <input type="number" step="any" value={form.entry} onChange={(e) => onChange({ entry: e.target.value })} className={inputCls} required />
        </Field>
        <Field label="Exit" required>
          <input type="number" step="any" value={form.exit} onChange={(e) => onChange({ exit: e.target.value })} className={inputCls} required />
        </Field>
        <Field label="Stop Loss">
          <input type="number" step="any" value={form.stopLoss} onChange={(e) => onChange({ stopLoss: e.target.value })} className={inputCls} />
        </Field>
        <Field label="Take Profit">
          <input type="number" step="any" value={form.takeProfit} onChange={(e) => onChange({ takeProfit: e.target.value })} className={inputCls} />
        </Field>
        <Field label="Quantity">
          <input type="number" step="any" value={form.quantity} onChange={(e) => onChange({ quantity: e.target.value })} className={inputCls} />
        </Field>
        <Field label="Session">
          <select value={form.session} onChange={(e) => onChange({ session: e.target.value })} className={inputCls}>
            {SESSIONS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </Field>
        <Field label="Entry Time" required>
          <input type="datetime-local" value={form.entryTime} onChange={(e) => onChange({ entryTime: e.target.value })} className={inputCls} required />
        </Field>
        <Field label="Exit Time" required>
          <input type="datetime-local" value={form.exitTime} onChange={(e) => onChange({ exitTime: e.target.value })} className={inputCls} required />
        </Field>
        <Field label="Timeframe">
          <select value={form.timeframe} onChange={(e) => onChange({ timeframe: e.target.value })} className={inputCls}>
            {TIMEFRAMES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </Field>
        <Field label="Emotion">
          <select value={form.emotion} onChange={(e) => onChange({ emotion: e.target.value })} className={inputCls}>
            {EMOTIONS.map((em) => <option key={em} value={em}>{em}</option>)}
          </select>
        </Field>
        <Field label="Confidence (1-5)">
          <input type="number" min={1} max={5} value={form.confidence} onChange={(e) => onChange({ confidence: e.target.value })} className={inputCls} />
        </Field>
        <Field label="Notes">
          <input value={form.notes} onChange={(e) => onChange({ notes: e.target.value })} className={inputCls} />
        </Field>
        <Field label="Strategy / Playbook">
          <select value={form.strategyId} onChange={(e) => onChange({ strategyId: e.target.value })} className={inputCls}>
            <option value="">— None —</option>
            {strategies.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
        <Field label="Setup">
          <select value={form.setupId} onChange={(e) => onChange({ setupId: e.target.value })} className={inputCls}>
            <option value="">— None —</option>
            {setups.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
      </div>

      <div className="mt-5 grid gap-5 sm:grid-cols-2">
        {/* Tags */}
        <div>
          <p className="mb-2 text-[9px] uppercase tracking-widest font-bold text-muted-foreground">Tags</p>
          <div className="flex flex-wrap gap-2">
            {tags.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => onChange({ tagNames: form.tagNames.includes(t.name) ? form.tagNames.filter((x) => x !== t.name) : [...form.tagNames, t.name] })}
                className={cn(
                  'rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition-all cursor-pointer',
                  form.tagNames.includes(t.name) ? 'border-primary/40 bg-primary/15 text-primary' : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:text-foreground',
                )}
              >
                {t.name}
              </button>
            ))}
            {tags.length === 0 && <span className="text-[11px] text-muted-foreground/60 italic">No tags yet — create them in the Playbook tab.</span>}
          </div>
        </div>

        {/* Mistakes */}
        <div>
          <p className="mb-2 text-[9px] uppercase tracking-widest font-bold text-muted-foreground">Mistakes</p>
          <div className="flex flex-wrap gap-2">
            {MISTAKES.map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => onChange({ mistakes: form.mistakes.includes(m) ? form.mistakes.filter((x) => x !== m) : [...form.mistakes, m] })}
                className={cn(
                  'rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition-all cursor-pointer',
                  form.mistakes.includes(m) ? 'border-rose-500/40 bg-rose-500/10 text-rose-400' : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:text-foreground',
                )}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && <p className="mt-4 text-xs text-rose-400 font-semibold">{error}</p>}

      <div className="mt-5 flex items-center gap-3 border-t border-border/10 pt-4">
        <button
          type="submit"
          disabled={saving}
          className="inline-flex items-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 text-primary px-5 py-2.5 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer disabled:opacity-50"
        >
          {saving ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary/30 border-t-primary" /> : <Check size={13} />}
          {saving ? 'Saving…' : submitLabel}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-accent/30 px-4 py-2.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition-all cursor-pointer">
            <X size={13} /> Cancel
          </button>
        )}
        <span className="ml-auto text-[10px] text-muted-foreground font-mono text-right">P&amp;L, R-multiple, risk &amp; duration<br className="hidden sm:block" /> are computed automatically.</span>
      </div>
    </form>
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
