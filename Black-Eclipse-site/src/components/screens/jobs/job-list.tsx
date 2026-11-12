'use client';

// ── Jobs list (Phase 6) ──────────────────────────────────────────────────────
// One row per job: the user's own name, a plain on/off, and the last outcome.
// The mechanism (schedule, delivery adapter, failures) stays behind "details".

import { useT } from '@/lib/i18n/use-t';
import type { TranslationKey } from '@/lib/i18n/types';
import { cn } from '@/lib/utils';
import { breakerStateKey, jobRunStatusKey, type JobDefinitionView } from '@/lib/harness/clients/jobs-browser';

export interface JobListProps {
  jobs: JobDefinitionView[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}

export function JobList({ jobs, selectedId, onSelect }: JobListProps) {
  const t = useT();
  if (jobs.length === 0) {
    return <div className="glass-card-subtle rounded-xl p-3 text-[12px] text-muted-foreground">{t('jobs.empty')}</div>;
  }
  return (
    <ul className="space-y-1.5">
      {jobs.map((job) => {
        const paused = job.breaker !== 'closed';
        return (
          <li key={job.id}>
            <button
              type="button"
              onClick={() => onSelect?.(job.id)}
              className={cn(
                'glass-card-subtle flex w-full items-center gap-2 rounded-xl border border-border/40 p-2.5 text-left text-[12px] transition-colors',
                selectedId === job.id && 'border-primary/50',
              )}
            >
              <span className="min-w-0 flex-1 truncate text-foreground">{job.name}</span>
              {job.lastRun ? (
                <span className="shrink-0 text-muted-foreground/70">
                  {t(jobRunStatusKey(job.lastRun.status) as TranslationKey)}
                </span>
              ) : (
                <span className="shrink-0 text-muted-foreground/70">{t('jobs.list.never')}</span>
              )}
              {paused ? (
                <span className="shrink-0 text-amber-400/90">{t(breakerStateKey(job.breaker) as TranslationKey)}</span>
              ) : (
                <span className="shrink-0 text-muted-foreground">
                  {job.enabled ? t('jobs.list.enabledOn') : t('jobs.list.enabledOff')}
                </span>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
