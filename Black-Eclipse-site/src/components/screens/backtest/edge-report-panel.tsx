'use client';

// ── Edge Report — the grade, the evidence and the figures ───────────────────
// The report is built by the runtime (the quant engine grades the evidence,
// the chart engine draws the figures) and this panel shows exactly what came
// back. Nothing is computed in the browser: the grade, the axis scores, the
// flags and the pictures are the runtime's output.
//
// The figures are served from the Artifact Center, so the report is a durable
// document rather than a picture that evaporates with the tab.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  backtestClient,
  type EdgeReport,
  type ExperimentSummary,
} from '@/lib/backtest/backtest-client';
import { cn } from '@/lib/utils';
import { AlertTriangle, FileText, Loader2, ShieldCheck } from '@/lib/icons';

function artifactUrl(id: string): string {
  return `/api/artifacts/${encodeURIComponent(id)}/download`;
}

function gradeTone(grade: string): string {
  if (grade === 'A' || grade === 'B') return 'text-emerald-300 border-emerald-500/40';
  if (grade === 'C') return 'text-amber-300 border-amber-500/40';
  return 'text-rose-300 border-rose-500/40';
}

function severityTone(severity: string): string {
  if (severity === 'critical') return 'text-rose-300';
  if (severity === 'warning') return 'text-amber-300';
  return 'text-muted-foreground';
}

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

  const verdict = report?.verdict;

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

      {error && (
        <p className="mb-2 font-mono text-[10px] text-rose-300">{error}</p>
      )}

      {!report && !error && (
        <p className="text-[11px] text-muted-foreground">
          Grade a stored backtest: the runtime judges the evidence it measured, names the
          overfit tells, and draws the figures. Nothing is computed in the browser.
        </p>
      )}

      {report && verdict && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className={cn('rounded-xl border px-3 py-1 font-mono text-xl', gradeTone(verdict.grade))}>
              {verdict.grade}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[11px] text-foreground">{verdict.summary}</p>
              <p className="font-mono text-[10px] text-muted-foreground">
                score {verdict.score.toFixed(0)}/100 ·{' '}
                {verdict.flagCounts.critical} critical · {verdict.flagCounts.warning} warning
              </p>
            </div>
            {report.reportArtifactId && (
              <a
                href={artifactUrl(report.reportArtifactId)}
                target="_blank"
                rel="noreferrer"
                className="glass-button flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[10px]"
              >
                <FileText className="h-3 w-3" /> the document
              </a>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {Object.entries(verdict.components).map(([name, component]) => (
              <div key={name} className="glass-card-subtle rounded-lg px-2.5 py-1.5">
                <div className="text-[10px] text-muted-foreground">{name}</div>
                <div className="font-mono text-sm text-foreground">
                  {component.score == null ? '—' : `${component.score.toFixed(0)}`}
                  <span className="text-[9px] text-muted-foreground">/100</span>
                </div>
                <div className="text-[9px] leading-tight text-muted-foreground/70">
                  {component.basis}
                </div>
              </div>
            ))}
          </div>

          {verdict.flags.length > 0 && (
            <ul className="space-y-1">
              {verdict.flags.map((flag) => (
                <li key={flag.code} className="flex items-start gap-1.5 font-mono text-[10px]">
                  <AlertTriangle className={cn('mt-0.5 h-3 w-3 shrink-0', severityTone(flag.severity))} />
                  <span className={severityTone(flag.severity)}>
                    <b>{flag.code}</b>: {flag.message}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {report.charts.length > 0 && (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {report.charts.map((chart) => (
                <figure key={chart.name} className="glass-card-subtle rounded-xl p-2">
                  {chart.artifactId ? (
                    <img
                      src={artifactUrl(chart.artifactId)}
                      alt={chart.title}
                      className="w-full rounded-lg"
                      data-testid={`edge-report-chart-${chart.name}`}
                    />
                  ) : (
                    <p className="px-1 py-2 font-mono text-[10px] text-amber-300">
                      {chart.error
                        ? `${chart.error.code}: ${chart.error.reason}`
                        : 'the figure was drawn but could not be stored'}
                    </p>
                  )}
                  <figcaption className="mt-1 flex items-center gap-2 px-1 text-[10px] text-muted-foreground">
                    <span>{chart.title}</span>
                    <span className="rounded border border-white/10 px-1 font-mono text-[9px]">
                      computed
                    </span>
                  </figcaption>
                </figure>
              ))}
            </div>
          )}

          <p className="text-[9px] leading-relaxed text-muted-foreground/70">
            The grade judges the evidence the runtime measured. It is not investment advice,
            and past performance does not indicate future results.
          </p>
        </div>
      )}
    </div>
  );
}
