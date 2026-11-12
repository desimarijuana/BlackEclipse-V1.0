'use client';

// ── Advisory Ledger — the decisions the agent recorded and how they turned out ──
// Every actionable recommendation the Fiduciary Gate saw is a durable decision,
// labelled computed / sourced / unverified, with an outcome once evaluated. This
// view reads the SAME ledger the agent and the routes use; nothing is recomputed
// here.

import React, { useCallback, useEffect, useState } from 'react';
import { ShieldCheck, RefreshCw } from '@/lib/icons';
import { cn } from '@/lib/utils';
import {
  advisoryScorecard,
  listDecisions,
  type AdvisoryDecisionView,
  type AdvisoryScorecardView,
} from '@/lib/harness/clients/advisory-browser';

const STATUS_STYLE: Record<string, string> = {
  computed: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300',
  sourced: 'border-sky-500/20 bg-sky-500/10 text-sky-300',
  unverified: 'border-amber-500/20 bg-amber-500/10 text-amber-300',
};

const VERDICT_STYLE: Record<string, string> = {
  right: 'text-emerald-400',
  wrong: 'text-rose-400',
  neutral: 'text-muted-foreground',
};

function fmtPct(value: number | null): string {
  return value === null ? '—' : `${(value * 100).toFixed(1)}%`;
}

export function AdvisoryDecisions() {
  const [decisions, setDecisions] = useState<AdvisoryDecisionView[]>([]);
  const [card, setCard] = useState<AdvisoryScorecardView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rows, score] = await Promise.all([listDecisions({ limit: 100 }), advisoryScorecard()]);
      setDecisions(rows);
      setCard(score);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load the advisory ledger');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-serif text-lg font-semibold text-foreground">Advisory Decisions</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Recommendations the agent recorded, and how they turned out. Computed ones rest on a
            portfolio calculation; unverified ones were disclosed as advice.
          </p>
        </div>
        <button
          onClick={() => void load()}
          className="flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground transition"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {card && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Decisions" value={String(card.total)} />
          <Stat label="Computed" value={String(card.byStatus.computed)}
            hint={`${card.byStatus.sourced} sourced · ${card.byStatus.unverified} unverified`} />
          <Stat label="Evaluated" value={String(card.evaluated)} />
          <Stat label="Hit rate" value={fmtPct(card.hitRate)}
            hint={card.avgRealizedReturn === null ? undefined : `avg ${fmtPct(card.avgRealizedReturn)}`} />
        </div>
      )}

      {error && <div className="rounded-2xl border border-rose-500/20 bg-rose-500/5 p-4 text-xs text-rose-300">{error}</div>}

      {!error && !loading && decisions.length === 0 && (
        <div className="rounded-2xl border border-white/10 glass-card p-6 text-center text-xs text-muted-foreground">
          No decisions recorded yet. When the agent gives you an actionable recommendation, it lands here.
        </div>
      )}

      <div className="space-y-2">
        {decisions.map((d) => (
          <div key={d.id} className="rounded-2xl border border-white/10 glass-card p-3.5">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 min-w-0">
                <ShieldCheck size={14} className="text-primary shrink-0" />
                <span className="font-serif text-sm font-semibold text-foreground truncate">
                  {d.thesis || `${d.action} ${d.symbols.join(' ')}`}
                </span>
              </div>
              <span className={cn('shrink-0 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide', STATUS_STYLE[d.status] ?? 'border-white/10 text-muted-foreground')}>
                {d.status}
              </span>
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
              <span>{new Date(d.createdAt).toLocaleDateString()}</span>
              {d.portfolioId && <span>{d.portfolioId}</span>}
              {d.outcome ? (
                <span className={VERDICT_STYLE[d.outcome.verdict] ?? ''}>
                  {d.outcome.verdict}
                  {d.outcome.realizedReturn !== null && ` · ${fmtPct(d.outcome.realizedReturn)}`}
                </span>
              ) : (
                <span>not yet evaluated</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-2xl border border-white/10 glass-card p-3">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="font-serif text-lg font-semibold text-foreground">{value}</div>
      {hint && <div className="text-[10px] text-muted-foreground mt-0.5">{hint}</div>}
    </div>
  );
}
