'use client';

// ── Daily Journal — per-day pre-market plan + post-market review ──────────────
// Loads a day's review, emotion and trades. Editing saves via the days API.

import React, { useCallback, useEffect, useState, useRef } from 'react';
import { usePageShortcuts } from '@/hooks/use-page-shortcuts';
import { Save, Check, ArrowLeft } from 'lucide-react';
import { cn } from '@/lib/utils';
import { fmtR, fmtMoney } from './charts';

interface DayTrade {
  id: string;
  symbol: string;
  direction: string;
  entry: number;
  exit: number;
  rMultiple: number;
  pnl: number;
  session: string | null;
  setup?: { name: string } | null;
  emotion: string | null;
}

interface DayData {
  id: string;
  date: string;
  review: {
    marketBias?: string | null;
    tradingPlan?: string | null;
    marketsWatching?: string | null;
    keyLevels?: string | null;
    wentWell?: string | null;
    wentWrong?: string | null;
    followedStrategy?: string | null;
    biggestMistake?: string | null;
    lesson?: string | null;
    tomorrow?: string | null;
  } | null;
  emotion: { state?: string | null; confidence?: number | null; discipline?: number | null; notes?: string | null } | null;
  trades: DayTrade[];
}

interface DailyJournalProps {
  date: string;
  onBack: () => void;
}

const BIASES = ['Bullish', 'Bearish', 'Neutral', 'Sideways'];
const STATES = ['Calm', 'Focused', 'Nervous', 'Confident', 'Anxious', 'Tired', 'Excited'];

export function DailyJournal({ date, onBack }: DailyJournalProps) {
  const [day, setDay] = useState<DayData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/journal/days/${date}`);
      const data = await res.json();
      setDay(data.day);
      const r = data.day?.review ?? {};
      const e = data.day?.emotion ?? {};
      setForm({
        marketBias: r.marketBias ?? '',
        tradingPlan: r.tradingPlan ?? '',
        marketsWatching: r.marketsWatching ? JSON.parse(r.marketsWatching).join(', ') : '',
        keyLevels: r.keyLevels ?? '',
        wentWell: r.wentWell ?? '',
        wentWrong: r.wentWrong ?? '',
        followedStrategy: r.followedStrategy ?? '',
        biggestMistake: r.biggestMistake ?? '',
        lesson: r.lesson ?? '',
        tomorrow: r.tomorrow ?? '',
        state: e.state ?? '',
        confidence: e.confidence != null ? String(e.confidence) : '',
        discipline: e.discipline != null ? String(e.discipline) : '',
        notes: e.notes ?? '',
      });
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => { void load(); }, [load]);

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const res = await fetch(`/api/journal/days/${date}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          marketBias: form.marketBias || null,
          tradingPlan: form.tradingPlan || null,
          marketsWatching: form.marketsWatching ? form.marketsWatching.split(',').map((s) => s.trim()).filter(Boolean) : [],
          keyLevels: form.keyLevels || null,
          wentWell: form.wentWell || null,
          wentWrong: form.wentWrong || null,
          followedStrategy: form.followedStrategy || null,
          biggestMistake: form.biggestMistake || null,
          lesson: form.lesson || null,
          tomorrow: form.tomorrow || null,
          state: form.state || null,
          confidence: form.confidence ? Number(form.confidence) : null,
          discipline: form.discipline ? Number(form.discipline) : null,
          notes: form.notes || null,
        }),
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      }
    } finally {
      setSaving(false);
    }
  };

  const trades = day?.trades ?? [];
  const netR = trades.reduce((s, t) => s + t.rMultiple, 0);
  const netPnl = trades.reduce((s, t) => s + t.pnl, 0);
  const wins = trades.filter((t) => t.rMultiple > 0).length;
  const winRate = trades.length > 0 ? (wins / trades.length) * 100 : 0;

  const inputCls = 'w-full rounded-lg bg-background/60 border border-border/40 hover:border-primary/50 px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-primary outline-none';
  const textareaCls = 'w-full rounded-lg bg-background/60 border border-border/40 hover:border-primary/50 px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-primary outline-none min-h-[70px] resize-y';

  const rootRef = useRef<HTMLDivElement>(null);
  const planRef = useRef<HTMLTextAreaElement>(null);
  usePageShortcuts(rootRef, [
    { id: 'daily.edit', label: 'Edit trading plan', keys: 'Shift+E', run: () => planRef.current?.focus(), enabled: !loading && !saving },
  ]);

  return (
    <div ref={rootRef} data-keyboard-scope="Daily journal" className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-primary border border-white/15 bg-accent/30 hover:bg-accent/60 rounded-xl px-3 py-1.5 transition-all cursor-pointer">
            <ArrowLeft size={13} /> Back
          </button>
          <div>
            <h2 className="font-serif text-lg font-semibold text-foreground">Daily Journal</h2>
            <p className="text-xs text-muted-foreground mt-0.5">{formatDate(date)}</p>
          </div>
        </div>
        <button
          onClick={save}
          disabled={saving}
          className="inline-flex items-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 text-primary px-4 py-2 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer disabled:opacity-50"
        >
          {saving ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary/30 border-t-primary" /> : saved ? <Check size={13} /> : <Save size={13} />}
          {saving ? 'Saving…' : saved ? 'Saved' : 'Save'}
        </button>
      </div>

      {loading ? (
        <div className="rounded-2xl glass-card p-8 text-center text-xs text-muted-foreground">Loading…</div>
      ) : (
        <>
          {/* Performance summary */}
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
            <Stat label="Net R" value={fmtR(netR)} tone={netR >= 0 ? 'text-emerald-400' : 'text-rose-400'} />
            <Stat label="Trades" value={String(trades.length)} />
            <Stat label="Win Rate" value={trades.length > 0 ? `${winRate.toFixed(0)}%` : '—'} />
            <Stat label="Net P&L" value={fmtMoney(netPnl)} tone={netPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'} />
          </div>

          {/* Pre-market */}
          <Section title="Pre-Market">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Market Bias">
                <div className="flex flex-wrap gap-1.5">
                  {BIASES.map((b) => (
                    <button key={b} type="button" onClick={() => set('marketBias', b)} className={cn('rounded-lg border px-2.5 py-1 text-[10px] font-semibold transition-all cursor-pointer', form.marketBias === b ? 'border-primary/40 bg-primary/15 text-primary' : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:text-foreground')}>
                      {b}
                    </button>
                  ))}
                </div>
              </Field>
              <Field label="Markets Watching">
                <input value={form.marketsWatching} onChange={(e) => set('marketsWatching', e.target.value)} placeholder="XAUUSD, NQ, BTCUSD" className={inputCls} />
              </Field>
            </div>
            <Field label="Trading Plan">
              <textarea ref={planRef} value={form.tradingPlan} onChange={(e) => set('tradingPlan', e.target.value)} className={textareaCls} placeholder="What's the plan for today?" />
            </Field>
            <Field label="Key Levels">
              <textarea value={form.keyLevels} onChange={(e) => set('keyLevels', e.target.value)} className={textareaCls} placeholder="Support / resistance / liquidity levels…" />
            </Field>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <Field label="Emotional State">
                <select value={form.state} onChange={(e) => set('state', e.target.value)} className={inputCls}>
                  <option value="">—</option>
                  {STATES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <Field label="Confidence (1-5)">
                <input type="number" min={1} max={5} value={form.confidence} onChange={(e) => set('confidence', e.target.value)} className={inputCls} />
              </Field>
              <Field label="Discipline (1-5)">
                <input type="number" min={1} max={5} value={form.discipline} onChange={(e) => set('discipline', e.target.value)} className={inputCls} />
              </Field>
            </div>
          </Section>

          {/* Trades */}
          <Section title={`Trades (${trades.length})`}>
            {trades.length === 0 ? (
              <p className="text-xs text-muted-foreground italic">No trades recorded for this day.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="border-b border-white/10">
                    <tr>
                      {['Symbol', 'Dir', 'Entry', 'Exit', 'R', 'P&L', 'Session', 'Setup', 'Emotion'].map((h) => (
                        <th key={h} className="px-3 py-2 text-[9px] uppercase tracking-widest text-muted-foreground font-bold">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((t) => (
                      <tr key={t.id} className="border-b border-white/5 last:border-0">
                        <td className="px-3 py-2 font-bold text-foreground">{t.symbol}</td>
                        <td className="px-3 py-2">{t.direction === 'LONG' ? <span className="text-emerald-400">LONG</span> : <span className="text-rose-400">SHORT</span>}</td>
                        <td className="px-3 py-2 text-muted-foreground">{t.entry}</td>
                        <td className="px-3 py-2 text-muted-foreground">{t.exit}</td>
                        <td className={cn('px-3 py-2 font-bold', t.rMultiple >= 0 ? 'text-emerald-400' : 'text-rose-400')}>{fmtR(t.rMultiple)}</td>
                        <td className={cn('px-3 py-2 font-bold', t.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400')}>{fmtMoney(t.pnl)}</td>
                        <td className="px-3 py-2 text-muted-foreground">{t.session ?? '—'}</td>
                        <td className="px-3 py-2 text-muted-foreground">{t.setup?.name ?? '—'}</td>
                        <td className="px-3 py-2 text-muted-foreground">{t.emotion ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          {/* Post-market review */}
          <Section title="Post-Market Review">
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              <Field label="What went well?">
                <textarea value={form.wentWell} onChange={(e) => set('wentWell', e.target.value)} className={textareaCls} />
              </Field>
              <Field label="What went wrong?">
                <textarea value={form.wentWrong} onChange={(e) => set('wentWrong', e.target.value)} className={textareaCls} />
              </Field>
              <Field label="Did I follow my strategy?">
                <textarea value={form.followedStrategy} onChange={(e) => set('followedStrategy', e.target.value)} className={textareaCls} />
              </Field>
              <Field label="What was my biggest mistake?">
                <textarea value={form.biggestMistake} onChange={(e) => set('biggestMistake', e.target.value)} className={textareaCls} />
              </Field>
              <Field label="What did I learn?">
                <textarea value={form.lesson} onChange={(e) => set('lesson', e.target.value)} className={textareaCls} />
              </Field>
              <Field label="What should I do differently tomorrow?">
                <textarea value={form.tomorrow} onChange={(e) => set('tomorrow', e.target.value)} className={textareaCls} />
              </Field>
            </div>
          </Section>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-2xl glass-card p-3">
      <p className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{label}</p>
      <p className={cn('mt-1 font-mono text-sm font-bold', tone ?? 'text-foreground')}>{value}</p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl glass-card p-4">
      <h3 className="mb-3 font-serif text-sm font-semibold text-foreground uppercase tracking-wider text-[11px]">{title}</h3>
      <div className="flex flex-col gap-3">{children}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function formatDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00Z');
  return d.toLocaleDateString('en', { year: 'numeric', month: 'long', day: 'numeric' });
}
