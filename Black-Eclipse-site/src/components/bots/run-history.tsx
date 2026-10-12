'use client';

// Run history for a bot. Shows real persisted executions, their outcome,
// duration and errors, and — for a selected run — the recorded activity
// timeline and deliveries. Polls ONLY while a run is live and stops at a
// terminal state. No fabricated progress; states map 1:1 to the backend.

import { useCallback, useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import { CheckCircle2, History, Loader2, XCircle, AlertTriangle } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import {
  cancelAutomationExecution,
  getAutomationExecution,
  listAutomationHistory,
  resumeAutomationExecution,
  type ExecutionView,
} from '@/lib/harness/automation-browser';
import { formatDateTime, formatDuration, formatRelative, isTerminalExecution } from '@/lib/bots/state';

const POLL_MS = 4000;

function RunIcon({ state }: { state: ExecutionView['state'] }) {
  if (isTerminalExecution(state)) {
    return state === 'completed'
      ? <CheckCircle2 size={15} className="text-emerald-300" weight="fill" />
      : state === 'cancelled' || state === 'skipped'
        ? <XCircle size={15} className="text-muted-foreground" weight="fill" />
        : <XCircle size={15} className="text-rose-300" weight="fill" />;
  }
  return <Loader2 size={15} className="animate-spin text-sky-300" />;
}

export interface RunHistoryProps {
  botId: string;
  /** Bump to force a refetch after a run is triggered. */
  refreshKey?: number;
}

export function RunHistory({ botId, refreshKey = 0 }: RunHistoryProps) {
  const t = useT();
  const [runs, setRuns] = useState<ExecutionView[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ExecutionView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const next = await listAutomationHistory(botId);
      setRuns(next);
      setError(null);
      setSelectedId((prev) => prev ?? next[0]?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to load runs');
    } finally {
      setLoading(false);
    }
  }, [botId]);

  useEffect(() => {
    setLoading(true);
    setRuns([]);
    setSelectedId(null);
    setDetail(null);
    void load();
  }, [botId, refreshKey, load]);

  // Bounded polling: refetch only while a run is live.
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    const anyLive = runs.some((r) => !isTerminalExecution(r.state));
    if (anyLive) {
      timer.current = setTimeout(() => void load(), POLL_MS);
    }
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [runs, load]);

  const loadDetail = useCallback(async (id: string) => {
    try {
      setDetail(await getAutomationExecution(id));
    } catch {
      setDetail(null);
    }
  }, []);

  useEffect(() => {
    if (selectedId) void loadDetail(selectedId);
  }, [selectedId, loadDetail, runs]);

  const act = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
      await load();
      if (selectedId) await loadDetail(selectedId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'action failed');
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <p className="text-xs text-muted-foreground">{t('common.loading')}</p>;
  }
  if (error) {
    return <p className="text-xs text-rose-300">{error}</p>;
  }
  if (runs.length === 0) {
    return <p className="text-xs text-muted-foreground">{t('bots.noHistory')}</p>;
  }

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,18rem)_1fr]">
      <ul className="space-y-1.5">
        {runs.slice(0, 30).map((run) => {
          const active = run.id === selectedId;
          return (
            <li key={run.id}>
              <button
                type="button"
                onClick={() => setSelectedId(run.id)}
                className={cn(
                  'flex w-full items-start gap-2 rounded-xl px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  active ? 'glass-card-subtle' : 'hover:bg-white/[0.04]',
                )}
              >
                <span className="mt-0.5"><RunIcon state={run.state} /></span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="text-xs font-semibold capitalize">{run.state.replace('_', ' ')}</span>
                    {run.attempt > 1 && (
                      <span className="text-[10px] text-muted-foreground">#{run.attempt}</span>
                    )}
                  </span>
                  <span className="block text-[11px] text-muted-foreground">
                    {formatDateTime(run.startedAt)} · {run.triggerType}
                  </span>
                  {run.errorClass && (
                    <span className="block text-[11px] text-rose-300">{run.errorClass}</span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <RunDetail
        run={detail}
        busy={busy}
        onCancel={() => detail && act(async () => { await cancelAutomationExecution(detail.id); })}
        onResume={() => detail && act(async () => { await resumeAutomationExecution(detail.id); })}
      />
    </div>
  );
}

function RunDetail({
  run,
  busy,
  onCancel,
  onResume,
}: {
  run: ExecutionView | null;
  busy: boolean;
  onCancel: () => void;
  onResume: () => void;
}) {
  const t = useT();
  if (!run) {
    return <div className="glass-card-subtle rounded-xl p-4 text-xs text-muted-foreground">{t('bots.run.timeline')}</div>;
  }
  const live = !isTerminalExecution(run.state);
  const events = run.events ?? [];

  return (
    <div className="glass-card-subtle rounded-xl p-4">
      <div className="mb-3 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <span>{t('bots.run.started')}: <span className="text-foreground">{formatDateTime(run.startedAt)}</span></span>
        <span>{t('bots.run.duration')}: <span className="text-foreground">{formatDuration(run.startedAt, run.finishedAt)}</span></span>
        {run.tokens != null && <span>tokens: <span className="text-foreground">{run.tokens}</span></span>}
      </div>

      {(live || run.state === 'waiting') && (
        <div className="mb-3 flex flex-wrap gap-2">
          {live && (
            <Button variant="destructive" size="sm" disabled={busy} onClick={onCancel}>
              {t('bots.run.cancel')}
            </Button>
          )}
          {run.state === 'waiting' && (
            <Button size="sm" disabled={busy} onClick={onResume}>
              {t('bots.resume')}
            </Button>
          )}
        </div>
      )}

      {run.outcomeReason && (
        <div className="mb-3 rounded-lg border border-border/40 px-3 py-2 text-xs">
          <span className="font-semibold text-muted-foreground">{t('bots.run.outcome')}: </span>
          <span className="text-foreground">{run.outcomeReason}</span>
        </div>
      )}

      {run.errorClass && (
        <div className="mb-3 flex items-start gap-2 rounded-lg border border-rose-500/25 bg-rose-500/5 px-3 py-2 text-xs text-rose-200">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>{run.errorClass}</span>
        </div>
      )}

      <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <History size={12} /> {t('bots.run.timeline')}
      </div>
      {events.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t('bots.run.noActivity')}</p>
      ) : (
        <ol className="space-y-1.5">
          {events.map((ev) => (
            <li key={ev.seq} className="flex items-start gap-2 text-xs">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-white/30" />
              <span className="text-foreground/80">{ev.type.replace(/[._]/g, ' ')}</span>
              <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">{formatRelative(ev.at)}</span>
            </li>
          ))}
        </ol>
      )}

      {run.deliveries && run.deliveries.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            {t('bots.run.deliveries')}
          </div>
          <ul className="space-y-1">
            {run.deliveries.map((d, i) => (
              <li key={i} className="flex items-center gap-2 text-xs">
                <span className={d.ok ? 'text-emerald-300' : 'text-rose-300'}>
                  {d.ok ? t('bots.delivery.ok') : t('bots.delivery.failed')}
                </span>
                <span className="text-muted-foreground">{d.adapter}{d.destination ? ` → ${d.destination}` : ''}</span>
                {d.reason && <span className="text-[10px] text-muted-foreground">{d.reason}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
