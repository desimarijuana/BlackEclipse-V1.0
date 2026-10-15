'use client';

// ── TradeForm — the shared trade entry form ──────────────────────────────────
// Rendered inside `QuickAddTrade` (the Journal's single add-trade dialog), which
// is mounted once in the Journal header and reachable from every sub-tab.

import React, { useEffect, useMemo, useState } from 'react';
import { Check, X } from '@/lib/icons';
import { cn } from '@/lib/utils';

export const SESSIONS = ['Asia', 'London', 'New York', 'Sydney', 'Tokyo'];
export const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d'];
export const EMOTIONS = ['Calm', 'Focused', 'Confident', 'Fearful', 'FOMO', 'Revenge', 'Bored', 'Overconfident', 'Hesitant'];
export const MISTAKES = ['Early exit', 'Moved stop', 'Moved target', 'Partial exit', 'Overtraded', 'Revenge', 'No stop', 'Chased entry'];
export const GRADES = ['A', 'B', 'C', 'D', 'F'];

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
  grade: string;
  strategyId: string;
  setupId: string;
  accountId: string;
  tagNames: string[];
  /** Pre-trade checklist state keyed by rule id. */
  checklist: Record<string, boolean>;
  commission: string;
  fee: string;
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
  grade: '',
  strategyId: '',
  setupId: '',
  accountId: '',
  tagNames: [],
  checklist: {},
  commission: '',
  fee: '',
});

interface StrategyWithRules { id: string; name: string; rules?: { id: string; text: string; category?: string | null }[] }

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
  const [strategies, setStrategies] = useState<StrategyWithRules[]>([]);
  const [setups, setSetups] = useState<{ id: string; name: string }[]>([]);
  const [tags, setTags] = useState<{ id: string; name: string }[]>([]);
  const [accounts, setAccounts] = useState<{ id: string; name: string; currency: string }[]>([]);
  const [newTag, setNewTag] = useState('');

  useEffect(() => {
    void (async () => {
      const [sRes, suRes, tRes, aRes] = await Promise.all([
        fetch('/api/journal/strategies'),
        fetch('/api/journal/setups'),
        fetch('/api/journal/tags'),
        fetch('/api/journal/accounts'),
      ]);
      const sData = await sRes.json();
      const suData = await suRes.json();
      const tData = await tRes.json();
      const aData = await aRes.json();
      setStrategies(sData.strategies ?? []);
      setSetups(suData.setups ?? []);
      setTags(tData.tags ?? []);
      setAccounts(aData.accounts ?? []);
    })();
  }, []);

  const inputCls = 'w-full rounded-lg bg-background/60 border border-border/40 hover:border-primary/50 px-3 py-2 text-xs font-mono focus:ring-1 focus:ring-primary outline-none transition-colors';

  const activeStrategy = useMemo(
    () => strategies.find((s) => s.id === form.strategyId),
    [strategies, form.strategyId],
  );
  const rules = activeStrategy?.rules ?? [];

  const createTag = () => {
    const name = newTag.trim();
    if (!name) return;
    if (!tags.some((t) => t.name.toLowerCase() === name.toLowerCase())) {
      setTags((prev) => [...prev, { id: `new:${name}`, name }]);
    }
    if (!form.tagNames.includes(name)) onChange({ tagNames: [...form.tagNames, name] });
    setNewTag('');
  };

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
        <Field label="Account">
          <select value={form.accountId} onChange={(e) => onChange({ accountId: e.target.value })} className={inputCls}>
            <option value="">— None —</option>
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.name} ({a.currency})</option>)}
          </select>
        </Field>
        <Field label="Commission">
          <input type="number" step="any" min={0} value={form.commission} onChange={(e) => onChange({ commission: e.target.value })} placeholder="0" className={inputCls} />
        </Field>
        <Field label="Fees / Swap">
          <input type="number" step="any" min={0} value={form.fee} onChange={(e) => onChange({ fee: e.target.value })} placeholder="0" className={inputCls} />
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
        <Field label="Grade (A–F)">
          <select value={form.grade} onChange={(e) => onChange({ grade: e.target.value })} className={inputCls}>
            <option value="">— None —</option>
            {GRADES.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </Field>
        <Field label="Strategy / Playbook">
          <select value={form.strategyId} onChange={(e) => onChange({ strategyId: e.target.value, checklist: {} })} className={inputCls}>
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

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
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
          </div>
          <div className="mt-2 flex items-center gap-2">
            <input
              value={newTag}
              onChange={(e) => setNewTag(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); createTag(); } }}
              placeholder="New tag…"
              className="flex-1 rounded-lg bg-background/60 border border-border/40 px-2.5 py-1.5 text-[11px] font-mono focus:ring-1 focus:ring-primary outline-none"
            />
            <button type="button" onClick={createTag} className="rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-[11px] font-semibold text-muted-foreground hover:text-foreground cursor-pointer">Add</button>
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

        {/* Pre-trade checklist from the selected strategy's rules */}
        <div>
          <p className="mb-2 text-[9px] uppercase tracking-widest font-bold text-muted-foreground">Pre-trade checklist</p>
          {rules.length === 0 ? (
            <span className="text-[11px] text-muted-foreground/60 italic">Select a strategy with rules to get a checklist.</span>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {rules.map((r) => (
                <li key={r.id}>
                  <label className="flex items-start gap-2 text-[11px] text-muted-foreground cursor-pointer">
                    <input
                      type="checkbox"
                      checked={!!form.checklist[r.id]}
                      onChange={(e) => onChange({ checklist: { ...form.checklist, [r.id]: e.target.checked } })}
                      className="mt-0.5 accent-primary"
                    />
                    <span className={form.checklist[r.id] ? 'text-foreground' : ''}>{r.text}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="mt-5">
        <Field label="Notes">
          <textarea
            value={form.notes}
            onChange={(e) => onChange({ notes: e.target.value })}
            rows={3}
            placeholder="What did you see? What was your plan and how did the trade play out?"
            className={cn(inputCls, 'resize-y font-sans')}
          />
        </Field>
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
        <span className="ml-auto text-[10px] text-muted-foreground font-mono text-right">P&amp;L net of costs, R-multiple &amp; duration<br className="hidden sm:block" /> are computed automatically.</span>
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
