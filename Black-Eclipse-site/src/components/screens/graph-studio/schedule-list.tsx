'use client';

// ── Schedule list ────────────────────────────────────────────────────────────
// Unattended runs for the open workflow: cron + timezone, a live next-fire time,
// the last outcome, and enable/pause/delete. A schedule always runs the TEST-RUN
// envelope for now, so a scheduled workflow can inspect, never act.

import { useCallback, useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { Clock, Play, Plus, Trash2 } from '@/lib/icons';
import {
  createSchedule, deleteSchedule, listSchedules, updateSchedule,
  ScheduleApiError, type WorkflowSchedule,
} from '@/lib/graph-studio/schedule-client';

function formatWhen(iso: string | null): string {
  if (!iso) return '—';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
}

export function ScheduleList({ workflowId }: { workflowId: string | null }) {
  const [schedules, setSchedules] = useState<WorkflowSchedule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('Daily run');
  const [cron, setCron] = useState('0 9 * * 1-5');
  const [timezone, setTimezone] = useState(
    typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' : 'UTC',
  );

  const refresh = useCallback(async () => {
    if (!workflowId) {
      setSchedules([]);
      return;
    }
    try {
      setSchedules(await listSchedules(workflowId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load schedules');
    }
  }, [workflowId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const add = useCallback(async () => {
    if (!workflowId) return;
    try {
      await createSchedule(workflowId, { name, cron, timezone });
      setAdding(false);
      setError(null);
      await refresh();
    } catch (err) {
      setError(err instanceof ScheduleApiError ? err.message : 'Failed to create schedule');
    }
  }, [workflowId, name, cron, timezone, refresh]);

  if (!workflowId) {
    return (
      <p className="px-3 py-2 text-[10.5px] text-muted-foreground">
        Save this workflow to give it a schedule.
      </p>
    );
  }

  return (
    <div className="border-t border-white/10 px-3 py-2">
      <div className="mb-1.5 flex items-center gap-1.5">
        <Clock size={12} className="text-muted-foreground" />
        <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Schedules</span>
        <button
          type="button"
          onClick={() => setAdding((v) => !v)}
          className="ml-auto flex items-center gap-1 rounded-md border border-white/10 px-1.5 py-0.5 text-[10px] text-muted-foreground hover:text-foreground"
        >
          <Plus size={10} /> Add
        </button>
      </div>

      {adding && (
        <div className="mb-2 space-y-1.5 rounded-md border border-white/10 bg-white/[0.02] p-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name"
            className="w-full rounded border border-white/10 bg-background/60 px-1.5 py-1 text-[11px] outline-none focus:border-sky-400/50"
          />
          <input
            value={cron}
            onChange={(e) => setCron(e.target.value)}
            placeholder="0 9 * * 1-5"
            className="w-full rounded border border-white/10 bg-background/60 px-1.5 py-1 font-mono text-[11px] outline-none focus:border-sky-400/50"
          />
          <input
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            placeholder="America/New_York"
            className="w-full rounded border border-white/10 bg-background/60 px-1.5 py-1 text-[11px] outline-none focus:border-sky-400/50"
          />
          <div className="flex items-center justify-between">
            <span className="text-[9.5px] text-muted-foreground">minute hour day month weekday</span>
            <button
              type="button"
              onClick={() => void add()}
              className="rounded-md border border-sky-400/30 bg-sky-500/10 px-2 py-0.5 text-[10px] text-sky-200 hover:bg-sky-500/20"
            >
              Create
            </button>
          </div>
        </div>
      )}

      {error && <p className="mb-1.5 rounded bg-rose-500/10 px-1.5 py-1 text-[10px] text-rose-200">{error}</p>}

      {schedules.length === 0 && !adding && (
        <p className="text-[10.5px] text-muted-foreground">
          No schedules. A schedule runs this workflow automatically while Eclipse is open.
        </p>
      )}

      <ul className="space-y-1">
        {schedules.map((schedule) => (
          <li key={schedule.id} className="rounded-md border border-white/10 bg-white/[0.02] px-2 py-1.5">
            <div className="flex items-center gap-1.5">
              <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', schedule.enabled ? 'bg-emerald-400' : 'bg-slate-600')} />
              <span className="min-w-0 flex-1 truncate text-[11px] text-foreground">{schedule.name}</span>
              <button
                type="button"
                title={schedule.enabled ? 'Pause' : 'Resume'}
                onClick={() => void updateSchedule(schedule.id, { enabled: !schedule.enabled }).then(refresh)}
                className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground"
              >
                <Play size={11} />
              </button>
              <button
                type="button"
                title="Delete schedule"
                onClick={() => void deleteSchedule(schedule.id).then(refresh)}
                className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-rose-400"
              >
                <Trash2 size={11} />
              </button>
            </div>
            <div className="mt-0.5 font-mono text-[9.5px] text-muted-foreground">
              {schedule.cron} · {schedule.timezone}
            </div>
            <div className="text-[9.5px] text-muted-foreground">
              next {formatWhen(schedule.nextRunAt)}
              {schedule.lastStatus ? ` · last ${schedule.lastStatus}` : ''}
            </div>
            {schedule.lastError && <div className="text-[9.5px] text-rose-300">{schedule.lastError}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}
