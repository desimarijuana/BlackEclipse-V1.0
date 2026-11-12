'use client';

// ── Landing checks (Phase 22 / S4) ──────────────────────────────────────────
// The ordered checks a change must pass, with the exit code as the judge. A
// check that did not run is shown as "Not run", never as a pass. Quick checks
// skip the long suite; full checks are the release gate.

import { useCallback, useEffect, useState } from 'react';
import { useT } from '@/lib/i18n/use-t';
import {
  getLandPlan,
  verifyLanding,
  type LandPlan,
  type LandResult,
} from '@/lib/harness/clients/code-browser';

const STATUS_KEY = {
  passed: 'code.land.status.passed',
  failed: 'code.land.status.failed',
  error: 'code.land.status.error',
  skipped: 'code.land.status.skipped',
} as const;

export function LandChecks({ taskId, onVerified }: { taskId: string; onVerified?: (result: LandResult) => void }) {
  const t = useT();
  const [plan, setPlan] = useState<LandPlan | null>(null);
  const [result, setResult] = useState<LandResult | null>(null);
  const [busy, setBusy] = useState<'quick' | 'full' | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    void getLandPlan(taskId)
      .then((next) => { if (alive) { setPlan(next); setError(false); } })
      .catch(() => { if (alive) setError(true); });
    return () => { alive = false; };
  }, [taskId]);

  const run = useCallback(async (full: boolean) => {
    setBusy(full ? 'full' : 'quick');
    setError(false);
    try {
      const next = await verifyLanding(taskId, full);
      setResult(next.result);
      onVerified?.(next.result);
    } catch {
      setError(true);
    } finally {
      setBusy(null);
    }
  }, [taskId, onVerified]);

  const statusOf = new Map((result?.results ?? []).map((item) => [item.id, item]));

  return (
    <div className="glass-card-subtle rounded-xl border border-border/40 p-3 text-[12px]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-medium text-foreground">{t('code.land.title')}</div>
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => { void run(false); }}
            className="glass-button rounded-lg px-2.5 py-1 text-[11px] text-foreground disabled:opacity-50"
          >
            {busy === 'quick' ? t('code.land.running') : t('code.land.quick')}
          </button>
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => { void run(true); }}
            className="glass-button rounded-lg px-2.5 py-1 text-[11px] text-foreground disabled:opacity-50"
          >
            {busy === 'full' ? t('code.land.running') : t('code.land.full')}
          </button>
        </div>
      </div>

      {plan?.warnings?.length ? (
        <p className="mt-1.5 text-[10.5px] text-amber-300/90">{plan.warnings.join(' · ')}</p>
      ) : null}

      {error && <div className="mt-2 text-red-300">{t('code.land.loadFailed')}</div>}

      {plan && plan.checks.length === 0 && (
        <div className="mt-2 text-muted-foreground">{t('code.land.empty')}</div>
      )}

      {plan && plan.checks.length > 0 && (
        <ul className="mt-2 space-y-1">
          {plan.checks.map((check) => {
            const done = statusOf.get(check.id);
            const status = done?.status ?? 'skipped';
            const detail = done?.outputTail?.trim();
            return (
              <li key={check.id} className="rounded-lg border border-border/30 px-2 py-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-foreground">{check.label}</span>
                  <span className={status === 'passed' ? 'text-emerald-300'
                    : status === 'skipped' ? 'text-muted-foreground' : 'text-red-300'}>
                    {t(STATUS_KEY[status])}
                  </span>
                </div>
                {detail && status !== 'passed' && (
                  <details className="mt-1">
                    <summary className="cursor-pointer text-muted-foreground">
                      {t('code.land.details')}
                    </summary>
                    <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-[10.5px] text-muted-foreground">
                      {detail}
                    </pre>
                  </details>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {result && (
        <div className={result.ok ? 'mt-2 text-emerald-300' : 'mt-2 text-red-300'}>
          {result.ok ? t('code.land.passed') : t('code.land.failed')}
        </div>
      )}
    </div>
  );
}
