'use client';

// ── Journal Playbook — define trading strategies ───────────────────────────────

import React, { useCallback, useEffect, useState } from 'react';
import { Plus, Check, X } from '@/lib/icons';

interface StrategyRule { id: string; text: string; category?: string | null; }
interface Strategy { id: string; name: string; description?: string | null; markets: string; confirmation?: string | null; entry?: string | null; rules: StrategyRule[]; }

/** Parse the markets JSON string into an array. */
function parseMarkets(raw: string): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

export function JournalPlaybook() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [markets, setMarkets] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [entry, setEntry] = useState('');
  const [rules, setRules] = useState<string[]>(['']);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/journal/strategies');
      const data = await res.json();
      setStrategies(data.strategies ?? []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await fetch('/api/journal/strategies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          description,
          markets: markets.split(',').map((m) => m.trim()).filter(Boolean),
          confirmation,
          entry,
          rules: rules.map((r) => r.trim()).filter(Boolean),
        }),
      });
      if (res.ok) {
        setAdding(false);
        setName(''); setDescription(''); setMarkets(''); setConfirmation(''); setEntry(''); setRules(['']);
        await load();
      }
    } finally {
      setSaving(false);
    }
  };

  const inputCls = 'w-full rounded-lg bg-background/60 border border-border/40 hover:border-primary/50 px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-primary outline-none';

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-serif text-lg font-semibold text-foreground">Playbook</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Define your strategies. BlackEclipse analyzes performance by strategy.</p>
        </div>
        <button
          onClick={() => setAdding((v) => !v)}
          className="inline-flex items-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 text-primary px-3 py-1.5 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer"
        >
          {adding ? <X size={13} /> : <Plus size={13} />} {adding ? 'Cancel' : 'New Strategy'}
        </button>
      </div>

      {adding && (
        <form onSubmit={submit} className="rounded-2xl glass-card border border-primary/20 p-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Name" required>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="BOS + FVG" className={inputCls} required />
            </Field>
            <Field label="Markets (comma-separated)">
              <input value={markets} onChange={(e) => setMarkets(e.target.value)} placeholder="XAUUSD, NQ" className={inputCls} />
            </Field>
            <Field label="Confirmation Timeframe">
              <input value={confirmation} onChange={(e) => setConfirmation(e.target.value)} placeholder="15m" className={inputCls} />
            </Field>
            <Field label="Entry Timeframe">
              <input value={entry} onChange={(e) => setEntry(e.target.value)} placeholder="1m" className={inputCls} />
            </Field>
          </div>
          <Field label="Description">
            <input value={description} onChange={(e) => setDescription(e.target.value)} className={inputCls} />
          </Field>

          <div className="mt-3">
            <p className="mb-1.5 text-[9px] uppercase tracking-widest font-bold text-muted-foreground">Rules</p>
            <div className="flex flex-col gap-1.5">
              {rules.map((r, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    value={r}
                    onChange={(e) => setRules((prev) => prev.map((x, xi) => (xi === i ? e.target.value : x)))}
                    placeholder={`Rule ${i + 1}…`}
                    className={inputCls}
                  />
                  <button type="button" onClick={() => setRules((prev) => prev.filter((_, xi) => xi !== i))} className="text-muted-foreground hover:text-rose-400 cursor-pointer"><X size={13} /></button>
                </div>
              ))}
            </div>
            <button type="button" onClick={() => setRules((prev) => [...prev, ''])} className="mt-2 text-[11px] font-semibold text-primary hover:text-primary/80 cursor-pointer">+ Add rule</button>
          </div>

          <div className="mt-4">
            <button type="submit" disabled={saving} className="inline-flex items-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 text-primary px-4 py-2 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer disabled:opacity-50">
              {saving ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary/30 border-t-primary" /> : <Check size={13} />}
              {saving ? 'Saving…' : 'Save Strategy'}
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="rounded-2xl glass-card p-8 text-center text-xs text-muted-foreground">Loading…</div>
      ) : strategies.length === 0 ? (
        <div className="rounded-2xl glass-card p-8 text-center text-xs text-muted-foreground italic">No strategies yet. Create your first playbook.</div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {strategies.map((s) => (
            <div key={s.id} className="rounded-2xl glass-card p-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-serif text-sm font-semibold text-foreground">{s.name}</h3>
                <span className="font-mono text-[9px] text-muted-foreground">{s.rules.length} rules</span>
              </div>
              {s.description && <p className="text-xs text-muted-foreground mb-2">{s.description}</p>}
              <div className="flex flex-wrap gap-1.5 mb-3">
                {parseMarkets(s.markets).map((m) => <Chip key={m}>{m}</Chip>)}
                {s.confirmation && <Chip>Conf: {s.confirmation}</Chip>}
                {s.entry && <Chip>Entry: {s.entry}</Chip>}
              </div>
              <ul className="flex flex-col gap-1">
                {s.rules.map((r) => (
                  <li key={r.id} className="flex items-start gap-1.5 text-xs text-muted-foreground">
                    <Check size={12} className="text-primary mt-0.5 shrink-0" />
                    {r.text}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {/* Tags management */}
      <TagsManager />
    </div>
  );
}

function TagsManager() {
  const [tags, setTags] = useState<{ id: string; name: string }[]>([]);
  const [newTag, setNewTag] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    const res = await fetch('/api/journal/tags');
    const data = await res.json();
    setTags(data.tags ?? []);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const addTag = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTag.trim()) return;
    setSaving(true);
    try {
      const res = await fetch('/api/journal/tags', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newTag.trim() }),
      });
      if (res.ok) {
        setNewTag('');
        await load();
      }
    } finally {
      setSaving(false);
    }
  };

  const inputCls = 'w-full rounded-lg bg-background/60 border border-border/40 hover:border-primary/50 px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-primary outline-none';

  return (
    <div className="rounded-2xl glass-card p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-serif text-sm font-semibold text-foreground">Tags</h3>
        <span className="font-mono text-[9px] text-muted-foreground">{tags.length} tags</span>
      </div>
      <form onSubmit={addTag} className="flex items-center gap-2 mb-3">
        <input
          value={newTag}
          onChange={(e) => setNewTag(e.target.value)}
          placeholder="New tag name…"
          className={inputCls}
        />
        <button
          type="submit"
          disabled={saving || !newTag.trim()}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-primary/40 bg-primary/15 text-primary px-3 py-1.5 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer disabled:opacity-50"
        >
          <Plus size={13} /> Add
        </button>
      </form>
      {tags.length === 0 ? (
        <p className="text-xs text-muted-foreground italic">No tags yet. Create tags to categorize your trades.</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((t) => (
            <span key={t.id} className="rounded-lg border border-white/10 bg-white/[0.03] px-2 py-1 text-[10px] font-mono text-muted-foreground">
              {t.name}
            </span>
          ))}
        </div>
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

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="rounded-lg border border-white/10 bg-white/[0.03] px-2 py-0.5 text-[10px] font-mono text-muted-foreground">{children}</span>;
}
