'use client';

// Investment Thesis Tracker — client UI. Talks only to /api/theses*.
// The original hypothesis is versioned; every edit appends a revision. Adding
// evidence is deterministic (no model): the impact panel shows which stated
// assumptions the evidence supports or contradicts, and never rewrites the text.

import { useCallback, useEffect, useState } from 'react';
import { confirmDialog } from '@/lib/ui/confirm-dialog';
import { cn } from '@/lib/utils';
import { assessAssumptionImpacts, summarizeThesis } from '@/lib/theses/analysis';
import { THESIS_STATUSES, type ThesisEvidenceRecord, type ThesisRecord, type ThesisRevisionRecord, type ThesisStatus } from '@/lib/theses/types';

const STATUS_STYLE: Record<ThesisStatus, string> = {
  active: 'text-emerald-400 border-emerald-400/30',
  weakening: 'text-amber-400 border-amber-400/30',
  broken: 'text-rose-400 border-rose-400/30',
  closed: 'text-muted-foreground border-border/40',
};

function linesToArray(s: string): string[] {
  return s.split('\n').map((l) => l.trim()).filter(Boolean);
}

export function ThesesClient() {
  const [theses, setTheses] = useState<ThesisRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [revisions, setRevisions] = useState<ThesisRevisionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/theses');
      const data = await res.json();
      setTheses(Array.isArray(data.theses) ? data.theses : []);
    } catch {
      setError('Could not load theses.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const selected = theses.find((t) => t.id === selectedId) ?? null;

  const loadRevisions = useCallback(async (id: string) => {
    try {
      const res = await fetch(`/api/theses/${id}/revisions`);
      const data = await res.json();
      setRevisions(Array.isArray(data.revisions) ? data.revisions : []);
    } catch {
      setRevisions([]);
    }
  }, []);

  useEffect(() => {
    if (selectedId) void loadRevisions(selectedId);
    else setRevisions([]);
  }, [selectedId, loadRevisions]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-6">
        <h1 className="font-serif text-2xl font-bold">Investment Theses</h1>
        <p className="text-xs text-muted-foreground mt-1">
          Versioned hypotheses with supporting and contradicting evidence. The original thesis is never silently rewritten.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <aside className="space-y-4">
          <NewThesisForm onCreated={() => void load()} />
          <div className="glass-card rounded-2xl p-3">
            <h2 className="text-[11px] font-mono uppercase text-muted-foreground mb-2">Saved theses</h2>
            {loading && <p className="text-xs text-muted-foreground">Loading…</p>}
            {error && <p className="text-xs text-rose-400">{error}</p>}
            {!loading && theses.length === 0 && (
              <p className="text-xs text-muted-foreground">No theses yet.</p>
            )}
            <ul className="space-y-1">
              {theses.map((t) => (
                <li key={t.id}>
                  <button
                    onClick={() => setSelectedId(t.id)}
                    className={cn(
                      'w-full text-left rounded-lg px-2 py-2 text-xs transition-colors',
                      selectedId === t.id ? 'bg-primary/10' : 'hover:bg-muted/40',
                    )}
                  >
                    <span className="font-mono font-bold">{t.symbol}</span>
                    <span className="text-muted-foreground"> · {t.marketId}</span>
                    <span className={cn('ml-2 rounded border px-1 text-[9px] uppercase', STATUS_STYLE[t.status])}>{t.status}</span>
                    <p className="text-muted-foreground/80 truncate">{t.title}</p>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </aside>

        <main>
          {!selected && <p className="text-sm text-muted-foreground">Select or create a thesis to begin.</p>}
          {selected && (
            <ThesisDetail
              thesis={selected}
              revisions={revisions}
              onChanged={() => void load()}
              onReloadRevisions={() => void loadRevisions(selected.id)}
            />
          )}
        </main>
      </div>
    </div>
  );
}

function NewThesisForm({ onCreated }: { onCreated: () => void }) {
  const [symbol, setSymbol] = useState('');
  const [marketId, setMarketId] = useState('US');
  const [title, setTitle] = useState('');
  const [hypothesis, setHypothesis] = useState('');
  const [assumptions, setAssumptions] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch('/api/theses', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, marketId, title, hypothesis, assumptions: linesToArray(assumptions) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed');
      setSymbol(''); setTitle(''); setHypothesis(''); setAssumptions('');
      onCreated();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="glass-card rounded-2xl p-3 space-y-2">
      <h2 className="text-[11px] font-mono uppercase text-muted-foreground">New thesis</h2>
      <div className="flex gap-2">
        <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="Symbol" required
          className="w-1/2 rounded-md border border-border/40 bg-background/40 px-2 py-1 text-xs" />
        <input value={marketId} onChange={(e) => setMarketId(e.target.value)} placeholder="Market" required
          className="w-1/2 rounded-md border border-border/40 bg-background/40 px-2 py-1 text-xs" />
      </div>
      <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" required
        className="w-full rounded-md border border-border/40 bg-background/40 px-2 py-1 text-xs" />
      <textarea value={hypothesis} onChange={(e) => setHypothesis(e.target.value)} placeholder="Investment hypothesis" required rows={3}
        className="w-full rounded-md border border-border/40 bg-background/40 px-2 py-1 text-xs" />
      <textarea value={assumptions} onChange={(e) => setAssumptions(e.target.value)} placeholder="Key assumptions (one per line)" rows={2}
        className="w-full rounded-md border border-border/40 bg-background/40 px-2 py-1 text-xs" />
      {err && <p className="text-[10px] text-rose-400">{err}</p>}
      <button type="submit" disabled={busy}
        className="w-full rounded-md bg-primary/90 px-2 py-1.5 text-xs font-bold text-primary-foreground disabled:opacity-50">
        {busy ? 'Creating…' : 'Create thesis'}
      </button>
    </form>
  );
}

function ThesisDetail({
  thesis, revisions, onChanged, onReloadRevisions,
}: {
  thesis: ThesisRecord;
  revisions: ThesisRevisionRecord[];
  onChanged: () => void;
  onReloadRevisions: () => void;
}) {
  const health = summarizeThesis(thesis);
  const impacts = assessAssumptionImpacts(thesis.assumptions, thesis.evidence);
  const [status, setStatus] = useState<ThesisStatus>(thesis.status);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setStatus(thesis.status); }, [thesis.id, thesis.status]);

  const changeStatus = async (next: ThesisStatus) => {
    setStatus(next);
    setBusy(true);
    try {
      await fetch(`/api/theses/${thesis.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: next, note: `Status → ${next}` }),
      });
      onChanged();
      onReloadRevisions();
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!(await confirmDialog({ title: `Delete thesis for ${thesis.symbol}?`, tone: 'danger' }))) return;
    await fetch(`/api/theses/${thesis.id}`, { method: 'DELETE' });
    onChanged();
  };

  return (
    <div className="space-y-4">
      <section className="glass-card rounded-2xl p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="font-serif text-lg font-bold">{thesis.title}</h2>
            <p className="text-xs text-muted-foreground font-mono">
              {thesis.symbol} · {thesis.marketId} · v{thesis.version}
              {thesis.reviewDate ? ` · review ${thesis.reviewDate.slice(0, 10)}` : ''}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select value={status} disabled={busy} onChange={(e) => void changeStatus(e.target.value as ThesisStatus)}
              className={cn('rounded-md border bg-background/40 px-2 py-1 text-xs', STATUS_STYLE[status])}>
              {THESIS_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <button onClick={remove} className="rounded-md border border-rose-400/30 px-2 py-1 text-xs text-rose-400">Delete</button>
          </div>
        </div>
        <p className="mt-3 text-sm">{thesis.hypothesis}</p>
      </section>

      <section className="grid gap-3 sm:grid-cols-3">
        <HealthCard label="Evidence" value={`${health.supporting} support / ${health.contradicting} contra`} />
        <HealthCard label="Coverage" value={health.coverage} />
        <HealthCard label="Suggested status" value={`${health.suggestedStatus} (not auto-applied)`} />
      </section>

      <section className="glass-card rounded-2xl p-4">
        <h3 className="text-[11px] font-mono uppercase text-muted-foreground mb-2">Assumption impact</h3>
        {impacts.length === 0 && <p className="text-xs text-muted-foreground">No assumptions recorded.</p>}
        <ul className="space-y-1.5">
          {impacts.map((im, i) => (
            <li key={i} className="flex items-start justify-between gap-3 text-xs">
              <span className="flex-1">{im.assumption}</span>
              <span className={cn('rounded border px-1.5 text-[10px] uppercase',
                im.verdict === 'supported' ? 'text-emerald-400 border-emerald-400/30'
                  : im.verdict === 'contradicted' ? 'text-rose-400 border-rose-400/30'
                    : im.verdict === 'weakened' ? 'text-amber-400 border-amber-400/30'
                      : 'text-muted-foreground border-border/40')}>
                {im.verdict}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <EvidencePanel thesis={thesis} onAdded={() => { onChanged(); onReloadRevisions(); }} />

      <section className="glass-card rounded-2xl p-4">
        <h3 className="text-[11px] font-mono uppercase text-muted-foreground mb-2">Version history</h3>
        {revisions.length === 0 && <p className="text-xs text-muted-foreground">No revisions.</p>}
        <ul className="space-y-1">
          {revisions.map((r) => (
            <li key={r.id} className="text-xs flex items-center justify-between border-b border-border/10 pb-1">
              <span className="font-mono">v{r.version}</span>
              <span className="text-muted-foreground truncate max-w-[60%]">{r.note ?? 'snapshot'}</span>
              <span className="text-muted-foreground/60">{r.createdAt.slice(0, 10)}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function HealthCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="glass-card-subtle rounded-xl p-3">
      <p className="text-[10px] font-mono uppercase text-muted-foreground">{label}</p>
      <p className="text-sm font-bold mt-1">{value}</p>
    </div>
  );
}

function EvidencePanel({ thesis, onAdded }: { thesis: ThesisRecord; onAdded: () => void }) {
  const [stance, setStance] = useState<'supporting' | 'contradicting'>('supporting');
  const [summary, setSummary] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [busy, setBusy] = useState(false);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await fetch(`/api/theses/${thesis.id}/evidence`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stance, summary, sourceUrl: sourceUrl || null, sourceType: 'user' }),
      });
      if (res.ok) { setSummary(''); setSourceUrl(''); onAdded(); }
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="glass-card rounded-2xl p-4">
      <h3 className="text-[11px] font-mono uppercase text-muted-foreground mb-2">Evidence</h3>
      <ul className="space-y-1.5 mb-3">
        {thesis.evidence.length === 0 && <li className="text-xs text-muted-foreground">No evidence recorded.</li>}
        {thesis.evidence.map((ev: ThesisEvidenceRecord) => (
          <li key={ev.id} className="text-xs border-b border-border/10 pb-1">
            <span className={cn('mr-2 text-[10px] uppercase', ev.stance === 'supporting' ? 'text-emerald-400' : 'text-rose-400')}>
              {ev.stance}
            </span>
            {ev.sourceUrl
              ? <a href={ev.sourceUrl} target="_blank" rel="noreferrer" className="underline decoration-dotted">{ev.summary}</a>
              : ev.summary}
          </li>
        ))}
      </ul>
      <form onSubmit={add} className="space-y-2">
        <div className="flex gap-2">
          <select value={stance} onChange={(e) => setStance(e.target.value as 'supporting' | 'contradicting')}
            className="rounded-md border border-border/40 bg-background/40 px-2 py-1 text-xs">
            <option value="supporting">supporting</option>
            <option value="contradicting">contradicting</option>
          </select>
          <input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="Source URL (optional)"
            className="flex-1 rounded-md border border-border/40 bg-background/40 px-2 py-1 text-xs" />
        </div>
        <textarea value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="Evidence summary" required rows={2}
          className="w-full rounded-md border border-border/40 bg-background/40 px-2 py-1 text-xs" />
        <button type="submit" disabled={busy}
          className="rounded-md bg-primary/90 px-3 py-1 text-xs font-bold text-primary-foreground disabled:opacity-50">
          {busy ? 'Adding…' : 'Add evidence'}
        </button>
      </form>
    </section>
  );
}
