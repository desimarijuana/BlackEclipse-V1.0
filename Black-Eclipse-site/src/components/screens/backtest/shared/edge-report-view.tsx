'use client';

// ── Edge Report view ────────────────────────────────────────────────────────
// The one renderer for a built Edge Report: the grade, the four axes, the
// flags, the figures and the durable document. Shared by the Backtest bench
// and the Strategy Studio so the two cannot disagree about what a grade means.
//
// Nothing is computed here. The runtime graded the evidence and the chart
// engine drew the figures; this shows what came back.

import React from 'react';
import type { EdgeReport } from '@/lib/backtest/backtest-client';
import { cn } from '@/lib/utils';
import { AlertTriangle, FileText } from '@/lib/icons';

export function artifactUrl(id: string): string {
  return `/api/artifacts/${encodeURIComponent(id)}/download`;
}

export function gradeTone(grade: string): string {
  if (grade === 'A' || grade === 'B') return 'text-emerald-300 border-emerald-500/40';
  if (grade === 'C') return 'text-amber-300 border-amber-500/40';
  return 'text-rose-300 border-rose-500/40';
}

export function severityTone(severity: string): string {
  if (severity === 'critical') return 'text-rose-300';
  if (severity === 'warning') return 'text-amber-300';
  return 'text-muted-foreground';
}

export function EdgeReportView({ report, compact = false }: { report: EdgeReport; compact?: boolean }) {
  const verdict = report.verdict;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className={cn('rounded-xl border px-3 py-1 font-mono text-xl', gradeTone(verdict.grade))}>
          {verdict.grade}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] text-foreground">{verdict.summary}</p>
          <p className="font-mono text-[10px] text-muted-foreground">
            score {verdict.score.toFixed(0)}/100 · {verdict.flagCounts.critical} critical ·{' '}
            {verdict.flagCounts.warning} warning
          </p>
        </div>
        {report.reportArtifactId ? (
          <a
            href={artifactUrl(report.reportArtifactId)}
            target="_blank"
            rel="noreferrer"
            className="glass-button flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[10px]"
          >
            <FileText className="h-3 w-3" /> the document
          </a>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {Object.entries(verdict.components).map(([name, component]) => (
          <div key={name} className="glass-card-subtle rounded-lg px-2.5 py-1.5" title={component.detail}>
            <div className="text-[10px] text-muted-foreground">{name}</div>
            <div className="font-mono text-sm text-foreground">
              {component.score == null ? '—' : component.score.toFixed(0)}
              <span className="text-[9px] text-muted-foreground">/100</span>
            </div>
            <div className="text-[9px] leading-tight text-muted-foreground/70">{component.basis}</div>
          </div>
        ))}
      </div>

      {verdict.flags.length > 0 ? (
        <div>
          <p className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Flags to clear</p>
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
        </div>
      ) : null}

      {report.charts.length > 0 ? (
        <div className={cn('grid grid-cols-1 gap-3', !compact && 'md:grid-cols-2')}>
          {report.charts.map((chart) => (
            <figure key={chart.name} className="glass-card-subtle rounded-xl p-2">
              {chart.artifactId ? (
                // The figure lives in the Artifact Center; the browser only shows it.
                // next/image cannot optimise a same-origin API download, so <img> is
                // the honest choice here.
                // eslint-disable-next-line @next/next/no-img-element
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
                <span className="rounded border border-white/10 px-1 font-mono text-[9px]">computed</span>
              </figcaption>
            </figure>
          ))}
        </div>
      ) : null}

      {report.markdown ? (
        <details className="text-[11px] text-muted-foreground">
          <summary className="cursor-pointer select-none">Full report document</summary>
          <pre className="mt-1 max-h-[260px] overflow-auto whitespace-pre-wrap rounded-lg bg-black/25 p-2 font-mono text-[10px] leading-relaxed">
            {report.markdown}
          </pre>
        </details>
      ) : null}

      <p className="text-[9px] leading-relaxed text-muted-foreground/70">
        The grade judges the evidence the runtime measured. It is not investment advice, and past performance does not
        indicate future results.
      </p>
    </div>
  );
}
