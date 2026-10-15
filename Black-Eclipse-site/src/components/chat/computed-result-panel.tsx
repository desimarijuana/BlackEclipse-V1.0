'use client';

import { useState } from 'react';
import { Calculator, ChevronDown, ChevronRight } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n/use-t';
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

export function ComputedResultPanel({ result, compact = false }: { result: unknown; compact?: boolean }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const data = coerceComputedResult(result);
  if (!data) return null;

  const statusKey = provenanceStatusKey(data.provenance);
  const status = renderComputedValue(data.outputs, data.provenance).status;
  const rows = Object.entries(data.outputs)
    .filter(([key]) => !key.startsWith('_'))
    .slice(0, MAX_ROWS);

  return (
    <div className={cn('mt-2 rounded-xl border border-border/30 glass-card-subtle', compact ? 'p-2' : 'p-2.5')}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
      >
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        <Calculator size={11} className="text-primary" />
        <span className="font-medium text-foreground/90">{t(statusKey)}</span>
        {data.provenance ? <span className="text-muted-foreground/80">{data.provenance.detail}</span> : null}
      </button>

      {open ? (
        <div className="mt-2 space-y-2 text-[10px]">
          {rows.length > 0 ? (
            <ul className="space-y-0.5">
              {rows.map(([key, value]) => (
                <li key={key} className="flex items-baseline justify-between gap-2 text-muted-foreground">
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
                {data.artifacts.map((a) => (
                  <li key={a.sha256} className="flex items-center gap-1.5">
                    <span>{a.name}</span>
                    <span className="font-mono text-[9px] text-muted-foreground/60">{a.sha256.slice(0, 12)}</span>
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
