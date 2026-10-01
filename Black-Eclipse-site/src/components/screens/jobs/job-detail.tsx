'use client';

// ── Job detail: history + breaker (Phase 6) ──────────────────────────────────
// Delivery reads like a message ("Finished · Delivered"), never a log. The
// machine reason stays behind "details", and a paused job says so in one plain
// sentence with a next step.

import { useState } from 'react';
import { useT } from '@/lib/i18n/use-t';
import type { TranslationKey } from '@/lib/i18n/types';
import {
  deliveryReasonKey,
  jobRunStatusKey,
  type JobDefinitionView,
  type JobRunView,
} from '@/lib/harness/jobs-browser';

export interface JobDetailProps {
  job: JobDefinitionView;
  runs: JobRunView[];
  onEnable: () => void;
  onDisable: () => void;
  onRunNow: () => void;
  onReset: () => void;
  onDelete: () => void;
}

export function JobDetail({ job, runs, onEnable, onDisable, onRunNow, onReset, onDelete }: JobDetailProps) {
  const t = useT();
  const [showDetails, setShowDetails] = useState(false);
  const paused = job.breaker !== 'closed';

  return (
    <div className="glass-card rounded-2xl p-3.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-[14px] font-medium text-foreground">{job.name}</h3>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {job.enabled ? t('jobs.list.enabledOn') : t('jobs.list.enabledOff')}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
          {job.enabled ? (
            <button type="button" onClick={onDisable} className="glass-button rounded-lg px-2 py-1 text-[11px]">
              {t('jobs.list.disable')}
            </button>
          ) : (
            <button type="button" onClick={onEnable} className="glass-button rounded-lg px-2 py-1 text-[11px]">
              {t('jobs.list.enable')}
            </button>
          )}
          <button type="button" onClick={onRunNow} className="glass-button rounded-lg px-2 py-1 text-[11px]">
            {t('jobs.list.runNow')}
          </button>
        </div>
      </div>

      {paused && (
        <div className="glass-card-subtle mt-2.5 rounded-xl border border-amber-500/30 p-2.5 text-[12px] text-amber-200/90">
          <p>{t('jobs.breaker.pausedBy')}</p>
          <button type="button" onClick={onReset} className="glass-button mt-1.5 rounded-lg px-2 py-1 text-[11px]">
            {t('jobs.breaker.reset')}
          </button>
        </div>
      )}

      <p className="mt-3 text-[12px] text-muted-foreground">{t('jobs.list.history')}</p>
      {runs.length === 0 ? (
        <p className="mt-1 text-[11px] text-muted-foreground/70">{t('jobs.list.never')}</p>
      ) : (
        <ul className="mt-1 space-y-1">
          {runs.slice(0, 12).map((run) => (
            <li key={run.id} className="glass-card-subtle rounded-lg p-2 text-[11px]">
              <div className="flex items-center justify-between gap-2">
                <span className="text-foreground">{t(jobRunStatusKey(run.status) as TranslationKey)}</span>
                <span className="text-muted-foreground/70">{run.finishedAt ?? run.startedAt}</span>
              </div>
              {run.deliveries?.map((outcome) => (
                <span key={`${outcome.adapter}-${outcome.target ?? ''}`} className="mt-0.5 block text-muted-foreground">
                  {outcome.ok
                    ? `${outcome.target ?? ''} — ${t('jobs.run.delivered')}`
                    : t(deliveryReasonKey(outcome.reasonCode) as TranslationKey)}
                </span>
              ))}
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        onClick={() => setShowDetails((v) => !v)}
        className="mt-2 text-[11px] text-muted-foreground underline-offset-2 hover:underline"
      >
        {t('jobs.run.details')}
      </button>
      {showDetails && (
        <pre className="glass-card-subtle mt-1.5 max-h-40 overflow-auto rounded-lg p-2 text-[11px] text-muted-foreground">
          {JSON.stringify({ status: job.breaker, failures: job.consecutiveFailures, runs }, null, 2)}
        </pre>
      )}

      <button
        type="button"
        onClick={onDelete}
        className="mt-2 text-[11px] text-red-400/80 underline-offset-2 hover:underline"
      >
        {t('jobs.list.delete')}
      </button>
    </div>
  );
}
