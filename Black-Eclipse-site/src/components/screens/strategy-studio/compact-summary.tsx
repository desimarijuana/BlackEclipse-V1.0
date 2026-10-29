'use client';

// ── Compact summary (small screens) ─────────────────────────────────────────
// The studio is dense; on a phone the first screenful should still answer the
// question. This is a read-only summary that appears below the stage rail and
// only under `md`. The full workspace stays available underneath.

import React from 'react';
import {
  formatMetric,
  type BacktestResult,
  type EdgeReport,
  type StrategyRecord,
} from '@/lib/backtest/backtest-client';
import type { PaperHealth } from '@/lib/strategy-studio/paper-health';
import { cn } from '@/lib/utils';
import { FlaskConical } from '@/lib/icons';

const METRICS = ['total_return', 'sharpe', 'max_drawdown'] as const;

export function CompactSummary({
  saved,
  result,
  edge,
  health,
}: {
  saved: StrategyRecord | null;
  result: BacktestResult | null;
  edge: EdgeReport | null;
  health: PaperHealth;
}) {
  return (
    <section className="glass-card rounded-2xl p-3 md:hidden" aria-label="Strategy summary">
      <div className="flex items-center gap-2">
        <FlaskConical className="h-3.5 w-3.5 text-primary" />
        <span className="text-[11px] font-semibold text-foreground">Strategy summary</span>
        <span className="ml-auto font-mono text-[9px] text-muted-foreground">
          {saved ? `${saved.id} · v${saved.version ?? saved.latestVersion}` : 'unsaved draft'}
        </span>
      </div>

      {result ? (
        <div className="mt-2 grid grid-cols-3 gap-2">
          {METRICS.map((key) => (
            <div key={key} className="rounded-lg bg-black/20 px-2 py-1">
              <p className="text-[8px] uppercase text-muted-foreground">{key.replace(/_/g, ' ')}</p>
              <p className="font-mono text-[11px] text-foreground">
                {formatMetric(key, result.metrics[key])}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-2 text-[10px] text-muted-foreground">
          No run yet. The full editor is below.
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {edge ? (
          <span className="rounded-md border border-primary/40 bg-primary/10 px-1.5 py-0.5 font-mono text-[9px] text-primary">
            grade {edge.verdict.grade}
          </span>
        ) : null}
        <span
          className={cn(
            'rounded-md border px-1.5 py-0.5 font-mono text-[9px] uppercase',
            health.state === 'fresh'
              ? 'border-emerald-500/30 text-emerald-400'
              : health.state === 'stale'
                ? 'border-amber-500/30 text-amber-400'
                : health.state === 'drifting'
                  ? 'border-rose-500/30 text-rose-400'
                  : 'border-white/15 text-muted-foreground',
          )}
        >
          paper {health.state}
        </span>
        <span className="text-[9px] text-muted-foreground">{health.headline}</span>
      </div>
    </section>
  );
}
