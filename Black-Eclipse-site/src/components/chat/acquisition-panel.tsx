'use client';

import { AlertTriangle, CheckCircle2, Database } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n/use-t';
import { coerceAcquisitionManifest } from '@/lib/harness/acquisition-types';

// ─── Phase 16 acquisition panel ─────────────────────────────────────────────
// The readable receipt for a bulk collection the `acquire` tool performed:
// source, window, rows, completeness, licence and attribution — from the ONE
// manifest written beside the CSV (never a second rendering contract). A pull
// that stopped at a limit renders PARTIAL with its stated reason; a partial
// dataset is never presented as the dataset. A blob that does not coerce
// renders nothing (the tool text still carries the outcome).

export function AcquisitionPanel({
  manifest,
  compact = false,
}: {
  manifest: unknown;
  compact?: boolean;
}) {
  const t = useT();
  const data = coerceAcquisitionManifest(manifest);
  if (!data) return null;

  return (
    <div
      className={cn(
        'mt-2 w-full rounded-xl border border-border/30 glass-card-subtle',
        compact ? 'p-2' : 'p-2.5',
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
        <Database size={11} className="text-primary" />
        <span className="font-medium text-foreground/90">{t('acquire.title')}</span>
        {data.purpose ? <span className="text-muted-foreground/80">{data.purpose}</span> : null}
      </div>

      <ul className="mt-2 space-y-2 text-[10px]">
        {data.sources.map((source) => (
          <li key={source.id} className="space-y-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-medium text-foreground/90">
                {t('acquire.source')}: {source.label}
              </span>
              <span
                className={cn(
                  'inline-flex items-center gap-1 rounded-full border px-1.5 py-px font-mono text-[9px] uppercase tracking-wide',
                  source.complete
                    ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'
                    : 'border-amber-500/30 bg-amber-500/10 text-amber-300',
                )}
              >
                {source.complete ? <CheckCircle2 size={9} /> : <AlertTriangle size={9} />}
                {source.complete ? t('acquire.complete') : t('acquire.partial')}
              </span>
            </div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-muted-foreground">
              {source.windowFrom || source.windowTo ? (
                <>
                  <dt>{t('acquire.window')}</dt>
                  <dd className="font-mono text-foreground/90">
                    {source.windowFrom ?? '—'} → {source.windowTo ?? '—'}
                  </dd>
                </>
              ) : null}
              <dt>{t('acquire.rows')}</dt>
              <dd className="font-mono text-foreground/90">
                {source.rows === null ? t('acquire.rowsUnknown') : source.rows.toLocaleString()}
              </dd>
              {source.licence ? (
                <>
                  <dt>{t('acquire.licence')}</dt>
                  <dd className="break-words">{source.licence}</dd>
                </>
              ) : null}
              {source.attribution ? (
                <>
                  <dt>{t('acquire.attribution')}</dt>
                  <dd className="break-words">{source.attribution}</dd>
                </>
              ) : null}
            </dl>
            {!source.complete && source.stoppedReason ? (
              <p className="text-amber-500/90">
                {t('acquire.partialReason', { reason: source.stoppedReason })}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
