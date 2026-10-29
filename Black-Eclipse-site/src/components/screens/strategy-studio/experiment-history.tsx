'use client';

// ── Experiment history ──────────────────────────────────────────────────────
// Every run the studio makes is saved by the runtime, but the studio never
// showed them. This lists a strategy's experiments, reopens one, and compares
// two to four like-for-like (the runtime reports comparability cautions).

import React, { useState } from 'react';
import {
  backtestClient,
  formatMetric,
  type ExperimentComparison,
  type ExperimentSummary,
} from '@/lib/backtest/backtest-client';
import { Activity, History, Loader2, Trash2 } from '@/lib/icons';
import { cn } from '@/lib/utils';

const COMPARE_LIMIT = 4;

export function ExperimentHistory({
  experiments,
  activeId,
  onOpen,
  onDelete,
  onError,
}: {
  experiments: ExperimentSummary[];
  activeId: string | null;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onError: (message: string | null) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [comparison, setComparison] = useState<ExperimentComparison | null>(null);
  const [busy, setBusy] = useState(false);

  const toggle = (id: string) => {
    setComparison(null);
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((item) => item !== id);
      if (prev.length >= COMPARE_LIMIT) return prev;
      return [...prev, id];
    });
  };

  const compare = async () => {
    if (selected.length < 2) return;
    setBusy(true);
    onError(null);
    try {
      setComparison(await backtestClient.compare(selected));
    } catch (err) {
      onError(err instanceof Error ? err.message : 'compare failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="glass-card rounded-2xl p-4" aria-label="Experiment history">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <History className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">Experiments</h2>
        <span className="font-mono text-[10px] text-muted-foreground">
          {experiments.length ? `${experiments.length} saved run${experiments.length === 1 ? '' : 's'}` : 'none yet'}
        </span>
        <button
          type="button"
          onClick={() => void compare()}
          disabled={selected.length < 2 || busy}
          className="glass-button ml-auto flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] disabled:opacity-40"
          title={`Select 2–${COMPARE_LIMIT} runs to compare`}
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Activity className="h-3 w-3" />}
          Compare ({selected.length})
        </button>
      </div>

      {experiments.length === 0 ? (
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          No runs yet. Save and run a strategy and every experiment will be listed here, with its metrics.
        </p>
      ) : (
        <div className="max-h-[240px] space-y-0.5 overflow-y-auto scrollbar-hide">
          {experiments.map((exp) => {
            const checked = selected.includes(exp.id);
            return (
              <div
                key={exp.id}
                className={cn(
                  'flex items-center gap-2 rounded-lg px-2 py-1',
                  exp.id === activeId ? 'bg-primary/10' : 'hover:bg-white/5',
                )}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggle(exp.id)}
                  aria-label={`Select experiment ${exp.id} for comparison`}
                  className="shrink-0"
                />
                <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onOpen(exp.id)}>
                  <span className="block truncate font-mono text-[11px] text-foreground">
                    {exp.strategyId ?? exp.kind}
                    {exp.strategyVersion ? <span className="text-muted-foreground"> v{exp.strategyVersion}</span> : null}
                    {exp.id === activeId ? <span className="text-primary"> · shown</span> : null}
                  </span>
                  <span className="block truncate font-mono text-[10px] text-muted-foreground">
                    {(exp.symbols || []).join(', ')} · ret {formatMetric('total_return', exp.metrics.total_return)} ·
                    sharpe {formatMetric('sharpe', exp.metrics.sharpe)} · {exp.createdAt?.slice(0, 16).replace('T', ' ')}
                  </span>
                </button>
                <button
                  type="button"
                  aria-label={`Delete experiment ${exp.id}`}
                  onClick={() => onDelete(exp.id)}
                  className="shrink-0 rounded p-1 text-muted-foreground hover:text-rose-400"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {comparison ? <ComparisonTable comparison={comparison} /> : null}
    </section>
  );
}

function ComparisonTable({ comparison }: { comparison: ExperimentComparison }) {
  const metrics = comparison.metrics?.length
    ? comparison.metrics
    : ['total_return', 'sharpe', 'max_drawdown', 'profit_factor', 'trade_count'];
  return (
    <div className="mt-3 rounded-xl border border-white/10 p-2">
      <div className="mb-1 flex items-center gap-2 font-mono text-[10px] text-muted-foreground">
        <span>Comparison</span>
        <span className="ml-auto">{comparison.experiments.length} runs</span>
      </div>
      <div className="overflow-auto">
        <table className="w-full text-left font-mono text-[10px]">
          <thead className="text-muted-foreground">
            <tr>
              <th className="px-1 py-0.5">Run</th>
              {metrics.map((metric) => (
                <th key={metric} className="px-1 py-0.5 text-right">
                  {metric.replace(/_/g, ' ')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {comparison.experiments.map((exp) => (
              <tr key={exp.experimentId} className="border-t border-white/5">
                <td className="px-1 py-0.5 text-foreground">{exp.experimentId}</td>
                {metrics.map((metric) => (
                  <td key={metric} className="px-1 py-0.5 text-right">
                    {formatMetric(metric, exp.metrics?.[metric])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {comparison.comparability?.length ? (
        <ul className="mt-1 space-y-0.5">
          {comparison.comparability.map((warning) => (
            <li key={warning.code} className="text-[10px] text-amber-200">
              <span className="font-mono">{warning.code}</span> {warning.message}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
