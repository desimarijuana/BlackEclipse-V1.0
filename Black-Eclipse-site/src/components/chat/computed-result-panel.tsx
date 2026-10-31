'use client';

import { useState } from 'react';
import { Calculator, ChevronDown, ChevronRight } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n/use-t';
import { ArtifactView, entryFor, useRunArtifactIndex } from './artifact-view';
import {
  coerceComputedResult,
  provenanceStatusKey,
  renderComputedValue,
} from '@/lib/harness/analysis-types';

// ─── Phase 8 computed-result panel ──────────────────────────────────────────
// Shows a result that Eclipse WORKED OUT, clearly distinct from retrieved data:
// an always-visible "Worked out by Eclipse" label plus the method line, and a
// "how did you get this" affordance behind which the inputs and method live. A
// computed number without a provenance record renders UNAVAILABLE, never bare.
//
// Phase 15/18: the artifacts this run produced render through `ArtifactView`
// (an image inline via the Artifact Center route, everything else a download),
// and a FIGURE (Phase 18) shows its plotted series and seed beside the image —
// always under the computed label, never presented as evidence.

const MAX_ROWS = 20;

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

/**
 * A method line a person can read. The runtime sometimes hands us a debug dump
 * (`type <class 'dict'> · keys ["asOf", …]`), which tells the reader nothing —
 * it describes the Python object, not the calculation. Such a detail is DROPPED
 * rather than shown; the panel still names the result and its values.
 */
export function humanMethodLine(detail: string | null | undefined): string | null {
  if (typeof detail !== 'string') return null;
  const text = detail.trim();
  if (!text) return null;
  if (/^type\s*<class/i.test(text)) return null;
  if (/^<class\s/i.test(text)) return null;
  if (/\bkeys\s*\[/i.test(text)) return null;
  // A bare serialized object is not a method ("{'a': 1, ...}", '[{...}]').
  if (/^[[{]/.test(text) && /[:]\s/.test(text) && text.length > 24) return null;
  return text;
}

export function ComputedResultPanel({
  result,
  compact = false,
  runId,
}: {
  result: unknown;
  compact?: boolean;
  runId?: string;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const entries = useRunArtifactIndex(runId);
  const data = coerceComputedResult(result);
  if (!data) return null;

  const statusKey = provenanceStatusKey(data.provenance);
  const status = renderComputedValue(data.outputs, data.provenance).status;
  const method = humanMethodLine(data.provenance?.detail);
  const rows = Object.entries(data.outputs)
    .filter(([key]) => !key.startsWith('_'))
    .slice(0, MAX_ROWS);
  const figure = data.figure;
  const figureArtifact = figure?.artifact
    ? data.artifacts.find((a) => a.name === figure.artifact) ?? null
    : null;

  const preview = rows
    .slice(0, 2)
    .map(([key, value]) => `${key} ${formatValue(value)}`)
    .join(' · ');

  return (
    <div className={cn('mt-3 rounded-xl border border-border/30', compact ? 'p-2.5' : 'p-3')}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-start gap-2 text-left text-[11px] text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
      >
        <span className="mt-px shrink-0">{open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}</span>
        <Calculator size={11} className="mt-px shrink-0 text-primary" />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
            <span className="font-medium text-foreground/90">{t(statusKey)}</span>
            {!open && preview ? (
              <span className="truncate font-mono text-[10px] text-muted-foreground/70">{preview}</span>
            ) : null}
          </span>
          {method ? (
            <span className={cn('mt-0.5 block break-words text-muted-foreground/70', !open && 'line-clamp-2')}>
              {method}
            </span>
          ) : null}
        </span>
      </button>

      {open ? (
        <div className="mt-3 space-y-2.5 text-[10px]">
          {figure ? (
            <div className="space-y-1">
              {figureArtifact ? (
                <ArtifactView
                  artifact={figureArtifact}
                  entry={entryFor(entries, figureArtifact)}
                />
              ) : null}
              {figure.series.length > 0 ? (
                <p className="text-[9px] text-muted-foreground/80">
                  {t('analysis.figureDrawnFrom', {
                    what: figure.series.map((s) => `${s.name} (${s.points})`).join(', '),
                  })}
                </p>
              ) : null}
              {figure.seed !== null ? (
                <p className="text-[9px] text-muted-foreground/60">
                  {t('analysis.figureSeed', { seed: String(figure.seed) })}
                </p>
              ) : null}
            </div>
          ) : null}

          {data.recipe ? (
            <p className="text-[9px] text-muted-foreground/80">
              {t('analysis.recipe')}: <span className="font-mono text-foreground/80">{data.recipe}</span>
            </p>
          ) : null}

          {rows.length > 0 ? (
            <ul className="space-y-1">
              {rows.map(([key, value]) => (
                <li key={key} className="flex items-baseline justify-between gap-3 text-muted-foreground">
                  <span className="min-w-0 break-words">{key}</span>
                  <span className="min-w-0 break-words text-right font-mono text-foreground/90">{formatValue(value)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground/80">{t('analysis.noOutputs')}</p>
          )}

          {data.artifacts.length > 0 ? (
            <div>
              <p className="font-semibold text-foreground">{t('analysis.saved')}</p>
              <ul className="space-y-0.5 text-muted-foreground/80">
                {data.artifacts
                  .filter((a) => !figureArtifact || a.name !== figureArtifact.name)
                  .map((a) => (
                    <li key={a.sha256}>
                      <ArtifactView artifact={a} entry={entryFor(entries, a)} compact={compact} />
                    </li>
                  ))}
              </ul>
            </div>
          ) : null}

          {status === 'unavailable' ? (
            <p className="text-amber-500/90">{t('analysis.unavailable')}</p>
          ) : null}
          {data.provenance ? (
            <p className="text-[9px] text-muted-foreground/60">{t('analysis.notASource')}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
