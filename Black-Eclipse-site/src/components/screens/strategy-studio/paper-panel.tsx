'use client';

// ── Paper deployment + track record ─────────────────────────────────────────
// Two honest modes: FORWARD (from the day after the research window ends to
// today) and REPLAY (the research window, labelled as a replay). A forward run
// is refused when there is no forward period — never silently downgraded.
//
// Every run is a real backtest recorded through the governed approval path. It
// places no orders. The track record shows each run and its drift against the
// research window, so "paper" stops being a single unverifiable click.

import React, { useMemo } from 'react';
import { formatMetric, type ExperimentSummary, type PaperRunRecord } from '@/lib/backtest/backtest-client';
import type { PaperMode, PaperWindow } from '@/lib/strategy-studio/paper-window';
import { paperHealth } from '@/lib/strategy-studio/paper-health';
import { Loader2, Play } from '@/lib/icons';
import { cn } from '@/lib/utils';

export interface PaperRun {
  id: string;
  experimentId: string;
  status: string;
  symbols: string[];
  metrics: Record<string, number | null>;
  liveExecution: boolean;
}

const DRIFT_METRICS = ['total_return', 'sharpe', 'max_drawdown'] as const;

function delta(paper: number | null | undefined, research: number | null | undefined): number | null {
  return typeof paper === 'number' && typeof research === 'number' ? paper - research : null;
}

function fmtDelta(value: number | null): string {
  if (value === null) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}`;
}

export function PaperPanel({
  hasSaved,
  hasResult,
  approved,
  onApproved,
  busy,
  onPromote,
  paper,
  mode,
  onMode,
  window,
  track,
  trackExperiments,
  expected,
}: {
  hasSaved: boolean;
  hasResult: boolean;
  approved: boolean;
  onApproved: (approved: boolean) => void;
  busy: boolean;
  onPromote: () => void;
  paper: PaperRun | null;
  mode: PaperMode;
  onMode: (mode: PaperMode) => void;
  window: PaperWindow;
  track: PaperRunRecord[];
  trackExperiments: Record<string, ExperimentSummary>;
  expected: Record<string, number | null> | null;
}) {
  const health = useMemo(
    () =>
      paperHealth({
        lastRunAt: track[0]?.createdAt,
        paperMetrics: track[0]?.metrics ?? null,
        baselineMetrics: expected,
      }),
    [track, expected],
  );

  return (
    <div className="glass-card rounded-2xl p-4">
      <div className="mb-2 flex items-center gap-2">
        <Play className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">Paper deployment</h2>
        <span className="font-mono text-[10px] text-muted-foreground">no orders · paper only</span>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-[11px] text-foreground">
        <label className="flex items-center gap-1.5">
          <input
            type="radio"
            name="paper-mode"
            checked={mode === 'forward'}
            onChange={() => onMode('forward')}
          />
          Forward (since the backtest ended)
        </label>
        <label className="flex items-center gap-1.5">
          <input
            type="radio"
            name="paper-mode"
            checked={mode === 'replay'}
            onChange={() => onMode('replay')}
          />
          Replay the research window
        </label>
      </div>

      <p className="mt-1 font-mono text-[10px] text-muted-foreground">
        {window.available
          ? `${mode === 'forward' ? 'forward' : 'replay'} · ${window.start} → ${window.end} · ${window.days} day${window.days === 1 ? '' : 's'}`
          : window.reason}
      </p>

      {mode === 'replay' ? (
        <p className="mt-1 text-[10px] leading-relaxed text-amber-200/80">
          A replay re-runs the same window as the backtest; it is not forward-looking.
        </p>
      ) : null}

      {!window.available ? (
        <p className="mt-1 text-[10px] leading-relaxed text-amber-200/80">{window.reason}</p>
      ) : null}

      <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
        A paper deployment records a real backtest against that window. It places no orders. Eclipse refuses live
        routing; promotion is paper-only and requires an explicit approval record.
      </p>

      <label className="mt-3 flex items-start gap-2 text-[11px] text-foreground">
        <input
          type="checkbox"
          checked={approved}
          onChange={(event) => onApproved(event.target.checked)}
          className="mt-0.5"
        />
        I approve this strategy version for a paper shadow run. In this single-operator workspace my approval is
        recorded by the operator actor, not hidden.
      </label>

      <button
        type="button"
        onClick={onPromote}
        disabled={busy || !hasSaved || !hasResult || !approved || !window.available}
        className="glass-button-add mt-3 flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
      >
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
        Approve and deploy to paper
      </button>

      {paper ? (
        <div className="mt-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3">
          <p className="font-mono text-[10px] text-emerald-300">
            {paper.id} | experiment {paper.experimentId} | liveExecution: {String(paper.liveExecution)}
          </p>
          <div className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-5">
            {['total_return', 'sharpe', 'max_drawdown', 'trade_count', 'profit_factor'].map((key) => (
              <div key={key} className="rounded-lg bg-black/20 px-2 py-1">
                <p className="text-[9px] uppercase text-muted-foreground">{key.replace(/_/g, ' ')}</p>
                <p className="font-mono text-xs">{formatMetric(key, paper.metrics[key])}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-3 border-t border-white/10 pt-2">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold text-foreground">Paper track record</span>
          <span className="font-mono text-[10px] text-muted-foreground">
            {track.length ? `${track.length} run${track.length === 1 ? '' : 's'}` : 'none yet'}
          </span>
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
            {health.state}
          </span>
          <span className="text-[10px] text-muted-foreground">{health.headline}</span>
        </div>
        <p className="mb-1 text-[9px] leading-relaxed text-muted-foreground/70">{health.detail}</p>
        {track.length === 0 ? (
          <p className="text-[10px] leading-relaxed text-muted-foreground">
            No paper runs recorded. Each deployment appends a run here with its metrics and drift against the research
            window.
          </p>
        ) : (
          <div className="overflow-auto">
            <table className="w-full text-left font-mono text-[10px]">
              <thead className="text-muted-foreground">
                <tr>
                  <th className="px-1 py-0.5">Run</th>
                  <th className="px-1 py-0.5">Window</th>
                  {DRIFT_METRICS.map((metric) => (
                    <th key={metric} className="px-1 py-0.5 text-right">
                      {metric.replace(/_/g, ' ')}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {track.slice(0, 10).map((run) => {
                  const experiment = trackExperiments[run.experimentId];
                  const windowLabel = experiment?.start && experiment?.end
                    ? `${experiment.start.slice(0, 10)} → ${experiment.end.slice(0, 10)}`
                    : '—';
                  return (
                    <tr key={run.id} className="border-t border-white/5">
                      <td className="px-1 py-0.5 text-foreground">{run.createdAt?.slice(0, 16).replace('T', ' ')}</td>
                      <td className="px-1 py-0.5">{windowLabel}</td>
                      {DRIFT_METRICS.map((metric) => {
                        const diff = delta(run.metrics?.[metric], expected?.[metric]);
                        return (
                          <td key={metric} className="px-1 py-0.5 text-right">
                            <span>{formatMetric(metric, run.metrics?.[metric])}</span>
                            <span
                              className={cn(
                                'ml-1 text-[9px]',
                                diff === null
                                  ? 'text-muted-foreground/60'
                                  : diff >= 0
                                    ? 'text-emerald-400'
                                    : 'text-rose-400',
                              )}
                              title="paper minus the latest backtest"
                            >
                              ({fmtDelta(diff)})
                            </span>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-1 text-[9px] leading-relaxed text-muted-foreground/60">
          Δ vs the latest backtest is shown per metric (paper minus research) — descriptive, not a significance test.
          Return, Sharpe and drawdown are not combined into one score because they are different units.
        </p>
      </div>
    </div>
  );
}
