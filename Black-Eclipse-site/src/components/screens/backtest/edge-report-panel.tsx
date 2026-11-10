'use client';

// ── Edge Report — pick a stored backtest and grade it ───────────────────────
// The report itself is rendered by the shared `EdgeReportView`; this panel only
// chooses which stored experiment (and optional Monte-Carlo) to grade.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  backtestClient,
  type EdgeReport,
  type ExperimentSummary,
} from '@/lib/backtest/backtest-client';
import { EdgeReportView } from './shared/edge-report-view';
import { QuantFigurePanel } from './shared/quant-figure-panel';
import { Loader2, ShieldCheck } from '@/lib/icons';

export interface EdgeReportPanelProps {
  experiments: ExperimentSummary[];
}

export function EdgeReportPanel({ experiments }: EdgeReportPanelProps) {
  const backtests = useMemo(
    () => experiments.filter((e) => e.kind === 'backtest' || e.kind === 'event_driven_backtest'),
    [experiments],
  );
  const monteCarlos = useMemo(
    () => experiments.filter((e) => e.kind === 'monte_carlo'),
    [experiments],
  );

  const [experimentId, setExperimentId] = useState('');
  const [monteCarloId, setMonteCarloId] = useState('');
  const [report, setReport] = useState<EdgeReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!experimentId && backtests.length > 0) setExperimentId(backtests[0].id);
  }, [backtests, experimentId]);

  useEffect(() => {
    if (!monteCarloId && monteCarlos.length > 0) setMonteCarloId(monteCarlos[0].id);
  }, [monteCarlos, monteCarloId]);

  const build = useCallback(async () => {
    if (!experimentId || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await backtestClient.edgeReport({
        experimentId,
        ...(monteCarloId ? { monteCarloExperimentId: monteCarloId } : {}),
      });
      setReport(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'the edge report could not be built');
    } finally {
      setBusy(false);
    }
  }, [experimentId, monteCarloId, busy]);

  return (
    <div className="glass-card rounded-2xl p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold text-foreground">Edge Report</h2>
        <span className="font-mono text-[10px] text-muted-foreground">
          grade · axes · overfit tells · figures
        </span>
        <div className="ml-auto flex items-center gap-2">
          <select
            value={experimentId}
            onChange={(e) => setExperimentId(e.target.value)}
            className="glass-card-subtle rounded-lg px-2 py-1 font-mono text-[10px] text-foreground outline-none"
            aria-label="experiment to grade"
          >
            {backtests.length === 0 ? <option value="">no backtest yet</option> : null}
            {backtests.map((e) => (
              <option key={e.id} value={e.id}>
                {e.id} · {e.strategyId ?? '—'} · {e.createdAt?.slice(0, 16)}
              </option>
            ))}
          </select>
          <select
            value={monteCarloId}
            onChange={(e) => setMonteCarloId(e.target.value)}
            className="glass-card-subtle rounded-lg px-2 py-1 font-mono text-[10px] text-foreground outline-none"
            aria-label="monte carlo to fold in"
          >
            <option value="">no Monte-Carlo</option>
            {monteCarlos.map((e) => (
              <option key={e.id} value={e.id}>
                {e.id} · {e.createdAt?.slice(0, 16)}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void build()}
            disabled={busy || !experimentId}
            className="glass-button flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            Build report
          </button>
        </div>
      </div>

      {error ? <p className="mb-2 font-mono text-[10px] text-rose-300">{error}</p> : null}

      {experimentId ? (
        <QuantFigurePanel
          experimentId={experimentId}
          monteCarloExperimentId={monteCarloId || undefined}
          className="mb-4 border-b border-border/40 pb-4"
        />
      ) : null}

      {!report && !error ? (
        <p className="text-[11px] text-muted-foreground">
          Grade a stored backtest: the runtime judges the evidence it measured, names the overfit tells, and draws the
          figures. Nothing is computed in the browser.
        </p>
      ) : null}

      {report ? <EdgeReportView report={report} /> : null}
    </div>
  );
}
