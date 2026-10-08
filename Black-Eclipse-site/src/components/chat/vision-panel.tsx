'use client';

import { useId, useState } from 'react';
import { ChevronDown, ChevronRight, ScanEye, Image as ImageIcon, FileCode2, AlertTriangle } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { coerceVisionRun, primaryVisionResult } from '@/lib/harness/vision-view';
import type { VisionResultInfo } from '@/lib/harness/types';

/**
 * The vision panel — attached metadata for a turn that used the vision
 * capability. Mirrors the visual language of `ResearchEvidencePanel`: one
 * always-visible summary line (mode, provider/model, confidence) that expands
 * to the recognized text, observations, regions, and chart/document/comparison
 * detail. Every value comes from the run's collected vision blob; nothing is
 * inferred, and an absent/odd blob renders nothing.
 */
export function VisionPanel({ vision, compact = false }: { vision: unknown; compact?: boolean }) {
  const run = coerceVisionRun(vision);
  const [open, setOpen] = useState(false);
  const bodyId = useId();
  if (!run) return null;
  const result = primaryVisionResult(run);
  if (!result && !run.failures?.length) return null;

  const failureCount = run.failures?.length ?? 0;
  const summary = result
    ? [
        result.mode ?? 'vision',
        result.model ? `${result.provider ?? 'model'}/${result.model}` : result.backend ?? undefined,
        typeof result.confidence === 'number' ? `confidence ${result.confidence.toFixed(2)}` : undefined,
        result.cached ? 'cached' : undefined,
      ]
        .filter(Boolean)
        .join(' · ')
    : `${failureCount} vision request${failureCount === 1 ? '' : 's'} unavailable`;

  return (
    <div className={cn('mt-3 w-full rounded-xl border border-border/20 glass-card-subtle', compact ? 'p-2' : 'p-2.5')}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={bodyId}
        className="flex w-full flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
      >
        {open ? <ChevronDown size={11} className="shrink-0" /> : <ChevronRight size={11} className="shrink-0" />}
        <ScanEye size={11} className="shrink-0 text-primary" />
        <span className="font-medium text-foreground/90">Vision</span>
        <span className="text-muted-foreground/80">{summary}</span>
        {failureCount > 0 ? <span className="text-amber-500/90">· {failureCount} unavailable</span> : null}
      </button>

      {open ? (
        <div id={bodyId} className="mt-2.5 space-y-3 text-[10px]">
          {result ? <ResultDetail result={result} /> : null}
          {failureCount > 0 && (
            <section>
              <div className="flex items-center gap-1.5 px-1">
                <AlertTriangle size={11} className="shrink-0 text-amber-500" />
                <span className="font-semibold text-foreground">Unavailable</span>
              </div>
              <ul className="mt-1.5 space-y-1 pl-4">
                {run.failures?.map((f, i) => {
                  const message = typeof f.error?.message === 'string' ? f.error.message : 'no result';
                  const code = typeof f.error?.errorClass === 'string' ? f.error.errorClass : 'ERROR';
                  return (
                    <li key={i} className="text-muted-foreground/90">
                      <span className="text-foreground/80">{f.mode ?? 'vision'}</span> — {code}: {message}
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
        </div>
      ) : null}
    </div>
  );
}

function ResultDetail({ result }: { result: VisionResultInfo }) {
  return (
    <>
      <section className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 px-1 text-muted-foreground/90">
        {result.assetId ? (
          <>
            <span className="text-muted-foreground/60">Asset</span>
            <span className="truncate font-mono text-foreground/80">{result.assetId}</span>
          </>
        ) : null}
        <span className="text-muted-foreground/60">Mode</span>
        <span className="text-foreground/80">{result.mode ?? 'analyze'}</span>
        {result.provider || result.model ? (
          <>
            <span className="text-muted-foreground/60">Model</span>
            <span className="text-foreground/80">
              {[result.provider, result.model].filter(Boolean).join(' / ')} ({result.backend ?? 'model'})
            </span>
          </>
        ) : null}
        {typeof result.latencyMs === 'number' ? (
          <>
            <span className="text-muted-foreground/60">Latency</span>
            <span className="text-foreground/80">{result.latencyMs} ms</span>
          </>
        ) : null}
      </section>

      {result.description ? (
        <section>
          <div className="flex items-center gap-1.5 px-1">
            <ImageIcon size={11} className="shrink-0 text-primary" />
            <span className="font-semibold text-foreground">Description</span>
          </div>
          <p className="mt-1 whitespace-pre-wrap break-words px-1 text-muted-foreground/90">{result.description}</p>
        </section>
      ) : null}

      {result.text && result.text.length > 0 ? (
        <section>
          <div className="flex items-center gap-1.5 px-1">
            <FileCode2 size={11} className="shrink-0 text-primary" />
            <span className="font-semibold text-foreground">Detected text</span>
            <span className="text-muted-foreground/70">· {result.text.length}</span>
          </div>
          <ul className="mt-1.5 max-h-40 space-y-0.5 overflow-y-auto overscroll-contain pr-1">
            {result.text.slice(0, 60).map((span, i) => (
              <li key={i} className="flex items-start gap-2 px-1">
                <span className="shrink-0 font-mono text-muted-foreground/60">
                  {span.bounds ? `[${span.bounds.x},${span.bounds.y}]` : ''}
                </span>
                <span className="break-words text-foreground/85">{span.text}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {result.observations && result.observations.length > 0 ? (
        <section>
          <div className="flex items-center gap-1.5 px-1">
            <ScanEye size={11} className="shrink-0 text-primary" />
            <span className="font-semibold text-foreground">Observations</span>
            <span className="text-muted-foreground/70">· {result.observations.length}</span>
          </div>
          <ul className="mt-1.5 max-h-56 space-y-1 overflow-y-auto overscroll-contain pr-1">
            {result.observations.slice(0, 40).map((obs, i) => (
              <li key={i} className="rounded-md px-1">
                <span className="break-words text-foreground/85">{obs.text}</span>
                <span className="ml-1 text-muted-foreground/60">
                  ({[obs.method, obs.kind, typeof obs.confidence === 'number' ? obs.confidence.toFixed(2) : null]
                    .filter(Boolean)
                    .join(', ')})
                  {obs.region ? ` [${obs.region.x},${obs.region.y},${obs.region.width},${obs.region.height}]` : ''}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {result.chart ? (
        <section className="px-1 text-muted-foreground/90">
          <span className="font-semibold text-foreground">Chart</span>{' '}
          {[result.chart.chart_type, result.chart.trend].filter(Boolean).join(' · ')}
          {result.chart.verification && typeof result.chart.verification === 'object' ? (
            <ValidationLine verification={result.chart.verification as Record<string, unknown>} />
          ) : null}
        </section>
      ) : null}

      {result.comparison ? (
        <section className="px-1 text-muted-foreground/90">
          <span className="font-semibold text-foreground">Comparison</span>{' '}
          {result.comparison.changed ? 'changed' : 'no change'}
          {typeof result.comparison.changedPixelsRatio === 'number'
            ? ` · ${(result.comparison.changedPixelsRatio * 100).toFixed(1)}% of cells`
            : ''}
        </section>
      ) : null}

      {result.document ? (
        <section className="px-1 text-muted-foreground/90">
          <span className="font-semibold text-foreground">Document</span>{' '}
          page {String(result.document.page ?? 0)}
          {result.document.hasTextLayer ? ' · text layer present' : ' · image-only'}
        </section>
      ) : null}

      {result.warnings && result.warnings.length > 0 ? (
        <ul className="space-y-0.5 px-1">
          {result.warnings.slice(0, 5).map((w, i) => (
            <li key={i} className="text-amber-500/90">
              {w}
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

function ValidationLine({ verification }: { verification: Record<string, unknown> }) {
  if (verification.available !== true) {
    return <span className="ml-1 text-muted-foreground/60">· not verified</span>;
  }
  const agrees = verification.agrees === true;
  return (
    <span className={cn('ml-1', agrees ? 'text-emerald-500/90' : 'text-amber-500/90')}>
      · {agrees ? 'matches' : 'disagrees with'} market data ({String(verification.actualTrend ?? 'unknown')})
    </span>
  );
}
