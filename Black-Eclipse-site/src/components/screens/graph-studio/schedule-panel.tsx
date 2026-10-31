'use client';

// ── Schedule panel ───────────────────────────────────────────────────────────
// The trigger.schedule node's real controls. The node is zero-config; its cron,
// timezone and enabled state live on a WorkflowSchedule linked by `nodeId`.
// Everything is previewed with the same cron engine the tick uses, so what the
// panel shows is what will fire.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Clock, Play, Square, Trash2 } from '@/lib/icons';
import { cn } from '@/lib/utils';
import {
  createSchedule,
  deleteSchedule,
  listSchedules,
  runScheduleNow,
  ScheduleApiError,
  updateSchedule,
  type WorkflowSchedule,
} from '@/lib/graph-studio/schedule-client';
import { isValidCron, isValidTimezone, nextRunAt } from '@/lib/graph-studio/cron';
import {
  buildCron,
  draftFromCron,
  nextRuns,
  timezoneOptions,
  WEEKDAY_LABELS,
  DEFAULT_DRAFT,
  type ScheduleDraft,
  type ScheduleFrequency,
} from '@/lib/graph-studio/schedule-presets';

const pad = (value: number): string => String(value).padStart(2, '0');
const browserTimezone = (): string => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
};

function formatWhen(iso: string | null): string {
  if (!iso) return '—';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
}

export function SchedulePanel({
  workflowId,
  nodeId,
}: {
  workflowId: string | null;
  nodeId: string;
}) {
  const [schedules, setSchedules] = useState<WorkflowSchedule[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState('Schedule');
  const [draft, setDraft] = useState<ScheduleDraft>(DEFAULT_DRAFT);
  const [timezone, setTimezone] = useState(browserTimezone);
  const [catchUp, setCatchUp] = useState<'skip' | 'coalesce'>('skip');
  const [versionMode, setVersionMode] = useState<'current' | 'pinned'>('current');
  const [pinnedVersion, setPinnedVersion] = useState(1);

  // Prefer the schedule linked to this node. If there is none but the workflow
  // has exactly one unlinked schedule (created from the dock before the node
  // link existed), adopt that one instead of creating a duplicate. Saving then
  // stamps its `nodeId`.
  const schedule = useMemo(() => {
    const linked = schedules.find((item) => item.nodeId === nodeId);
    if (linked) return linked;
    const unlinked = schedules.filter((item) => !item.nodeId);
    return unlinked.length === 1 ? unlinked[0] : null;
  }, [schedules, nodeId]);

  const refresh = useCallback(async () => {
    if (!workflowId) {
      setSchedules([]);
      return;
    }
    setLoading(true);
    try {
      setSchedules(await listSchedules(workflowId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load schedules');
    } finally {
      setLoading(false);
    }
  }, [workflowId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Mirror the stored schedule into the builder. Keyed by id+updatedAt so a
  // local edit is not clobbered until the schedule actually changes.
  useEffect(() => {
    if (!schedule) return;
    setDraft(draftFromCron(schedule.cron));
    setName(schedule.name);
    setTimezone(schedule.timezone);
    setCatchUp(schedule.catchUp);
    setVersionMode(schedule.version == null ? 'current' : 'pinned');
    setPinnedVersion(schedule.version ?? 1);
  }, [schedule?.id, schedule?.updatedAt]); // eslint-disable-line react-hooks/exhaustive-deps

  const cron = buildCron(draft);
  const zones = useMemo(() => timezoneOptions(timezone), [timezone]);
  const timeValue = `${pad(draft.hour)}:${pad(draft.minute)}`;

  const preview = useMemo(() => {
    if (!isValidCron(cron) || !isValidTimezone(timezone)) return [];
    try {
      return nextRuns(cron, timezone, 3);
    } catch {
      return [];
    }
  }, [cron, timezone]);

  const validationError = useMemo(() => {
    if (!isValidCron(cron)) return 'That schedule is not a valid cron expression.';
    if (!isValidTimezone(timezone)) return `Unknown timezone "${timezone}".`;
    if (draft.frequency === 'weekly' && draft.weekdays.length === 0) {
      return 'Pick at least one weekday.';
    }
    try {
      if (!nextRunAt(cron, timezone, new Date())) {
        return 'That schedule never fires within the next 40 days.';
      }
    } catch {
      return 'That schedule could not be resolved.';
    }
    return null;
  }, [cron, timezone, draft.frequency, draft.weekdays]);

  const save = async () => {
    if (!workflowId || validationError) return;
    setBusy(true);
    setError(null);
    const payload = {
      name: name.trim() || 'Schedule',
      cron,
      timezone,
      catchUp,
      version: versionMode === 'pinned' ? Math.max(1, pinnedVersion) : null,
    };
    try {
      if (schedule) {
        // Adopt a legacy unlinked schedule into this node on first save.
        await updateSchedule(schedule.id, schedule.nodeId ? payload : { ...payload, nodeId });
      } else {
        await createSchedule(workflowId, { ...payload, nodeId });
      }
      await refresh();
    } catch (err) {
      setError(err instanceof ScheduleApiError ? err.message : err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setBusy(false);
    }
  };

  const toggleEnabled = async () => {
    if (!schedule) return;
    setBusy(true);
    setError(null);
    try {
      await updateSchedule(schedule.id, { enabled: !schedule.enabled });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update');
    } finally {
      setBusy(false);
    }
  };

  const runNow = async () => {
    if (!schedule) return;
    setBusy(true);
    setError(null);
    try {
      await runScheduleNow(schedule.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start the run');
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!schedule) return;
    setBusy(true);
    setError(null);
    try {
      await deleteSchedule(schedule.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete');
    } finally {
      setBusy(false);
    }
  };

  if (!workflowId) {
    return (
      <p className="px-3 py-3 text-[11px] text-muted-foreground">
        Save this workflow first — a schedule runs the persisted version.
      </p>
    );
  }

  return (
    <div className="space-y-3 px-3 py-3">
      <div className="rounded-md border border-white/10 bg-white/[0.02] p-2">
        <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          <Clock size={11} /> Schedule
        </div>
        <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
          Fires while the Eclipse server is running. Each fire executes the saved version in the
          read-only test envelope — schedules can read and compute, never write or trade.
        </p>
      </div>

      {error && <p className="rounded bg-rose-500/10 px-2 py-1 text-[10px] text-rose-200">{error}</p>}

      {schedule && (
        <div className="rounded-md border border-white/10 bg-white/[0.02] px-2 py-1.5">
          <div className="flex items-center gap-1.5">
            <span className={cn('h-1.5 w-1.5 rounded-full', schedule.enabled ? 'bg-emerald-400' : 'bg-slate-600')} />
            <span className="text-[10.5px] text-foreground">{schedule.enabled ? 'Active' : 'Paused'}</span>
            <span className="ml-auto text-[9.5px] text-muted-foreground">
              {schedule.lastStatus ? `last ${schedule.lastStatus}` : 'never fired'}
            </span>
          </div>
          <div className="mt-0.5 text-[9.5px] text-muted-foreground">
            next {formatWhen(schedule.nextRunAt)}
            {schedule.lastRunAt ? ` · last ${formatWhen(schedule.lastRunAt)}` : ''}
          </div>
          {schedule.lastError && <div className="text-[9.5px] text-rose-300">{schedule.lastError}</div>}
        </div>
      )}

      <label className="block">
        <span className="mb-0.5 block text-[10px] text-muted-foreground">Name</span>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[11px] outline-none focus:border-primary/50"
        />
      </label>

      <label className="block">
        <span className="mb-0.5 block text-[10px] text-muted-foreground">Repeat</span>
        <select
          value={draft.frequency}
          onChange={(event) => setDraft({ ...draft, frequency: event.target.value as ScheduleFrequency })}
          className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[11px] outline-none focus:border-primary/50"
        >
          <option value="minutes">Every N minutes</option>
          <option value="hourly">Every hour</option>
          <option value="daily">Every day</option>
          <option value="weekly">Every week</option>
          <option value="monthly">Every month</option>
          <option value="custom">Custom cron</option>
        </select>
      </label>

      {draft.frequency === 'minutes' && (
        <label className="block">
          <span className="mb-0.5 block text-[10px] text-muted-foreground">Every N minutes</span>
          <input
            type="number"
            min={1}
            max={59}
            value={draft.everyMinutes}
            onChange={(event) => setDraft({ ...draft, everyMinutes: Number(event.target.value) || 1 })}
            className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[11px] outline-none focus:border-primary/50"
          />
        </label>
      )}

      {draft.frequency === 'hourly' && (
        <label className="block">
          <span className="mb-0.5 block text-[10px] text-muted-foreground">Minute past the hour</span>
          <input
            type="number"
            min={0}
            max={59}
            value={draft.minute}
            onChange={(event) => setDraft({ ...draft, minute: Number(event.target.value) || 0 })}
            className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[11px] outline-none focus:border-primary/50"
          />
        </label>
      )}

      {draft.frequency !== 'minutes' && draft.frequency !== 'hourly' && draft.frequency !== 'custom' && (
        <label className="block">
          <span className="mb-0.5 block text-[10px] text-muted-foreground">Time</span>
          <input
            type="time"
            value={timeValue}
            onChange={(event) => {
              const [hour, minute] = event.target.value.split(':').map(Number);
              setDraft({ ...draft, hour: hour || 0, minute: minute || 0 });
            }}
            className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[11px] outline-none focus:border-primary/50"
          />
        </label>
      )}

      {draft.frequency === 'weekly' && (
        <div>
          <span className="mb-1 block text-[10px] text-muted-foreground">Days</span>
          <div className="flex flex-wrap gap-1">
            {WEEKDAY_LABELS.map((label, day) => {
              const on = draft.weekdays.includes(day);
              return (
                <button
                  key={label}
                  type="button"
                  onClick={() => setDraft({
                    ...draft,
                    weekdays: on
                      ? draft.weekdays.filter((value) => value !== day)
                      : [...draft.weekdays, day],
                  })}
                  className={cn(
                    'rounded-md border px-1.5 py-0.5 text-[10px]',
                    on
                      ? 'border-primary/40 bg-primary/15 text-foreground'
                      : 'border-white/10 text-muted-foreground hover:text-foreground',
                  )}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {draft.frequency === 'monthly' && (
        <label className="block">
          <span className="mb-0.5 block text-[10px] text-muted-foreground">Day of month</span>
          <input
            type="number"
            min={1}
            max={31}
            value={draft.dayOfMonth}
            onChange={(event) => setDraft({ ...draft, dayOfMonth: Number(event.target.value) || 1 })}
            className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[11px] outline-none focus:border-primary/50"
          />
        </label>
      )}

      {draft.frequency === 'custom' && (
        <label className="block">
          <span className="mb-0.5 block text-[10px] text-muted-foreground">Cron (minute hour day month weekday)</span>
          <input
            value={draft.cron}
            onChange={(event) => setDraft({ ...draft, cron: event.target.value })}
            placeholder="0 9 * * 1-5"
            className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 font-mono text-[11px] outline-none focus:border-primary/50"
          />
        </label>
      )}

      <label className="block">
        <span className="mb-0.5 block text-[10px] text-muted-foreground">Timezone</span>
        <select
          value={timezone}
          onChange={(event) => setTimezone(event.target.value)}
          className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[11px] outline-none focus:border-primary/50"
        >
          {zones.map((zone) => (
            <option key={zone} value={zone}>{zone}</option>
          ))}
        </select>
      </label>

      <div className="grid grid-cols-2 gap-2">
        <label className="block">
          <span className="mb-0.5 block text-[10px] text-muted-foreground">If a fire is missed</span>
          <select
            value={catchUp}
            onChange={(event) => setCatchUp(event.target.value as 'skip' | 'coalesce')}
            className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[11px] outline-none focus:border-primary/50"
          >
            <option value="skip">Skip it</option>
            <option value="coalesce">Run once when back</option>
          </select>
        </label>
        <label className="block">
          <span className="mb-0.5 block text-[10px] text-muted-foreground">Workflow version</span>
          <select
            value={versionMode}
            onChange={(event) => setVersionMode(event.target.value as 'current' | 'pinned')}
            className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[11px] outline-none focus:border-primary/50"
          >
            <option value="current">Current</option>
            <option value="pinned">Pinned</option>
          </select>
        </label>
      </div>

      {versionMode === 'pinned' && (
        <label className="block">
          <span className="mb-0.5 block text-[10px] text-muted-foreground">Pinned version</span>
          <input
            type="number"
            min={1}
            value={pinnedVersion}
            onChange={(event) => setPinnedVersion(Math.max(1, Number(event.target.value) || 1))}
            className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[11px] outline-none focus:border-primary/50"
          />
        </label>
      )}

      <div className="rounded-md border border-white/10 bg-white/[0.02] p-2">
        <div className="font-mono text-[10px] text-muted-foreground">{cron || '—'}</div>
        {validationError ? (
          <p className="mt-1 text-[10px] text-rose-300">{validationError}</p>
        ) : (
          <ul className="mt-1 space-y-0.5">
            {preview.map((fire) => (
              <li key={fire.iso} className="text-[10px] text-muted-foreground">next · {fire.local}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onClick={() => void save()}
          disabled={busy || loading || Boolean(validationError)}
          className="graph-accent rounded-md border px-2.5 py-1 text-[10.5px] disabled:opacity-40"
        >
          {schedule ? 'Save schedule' : 'Create schedule'}
        </button>
        {schedule && (
          <>
            <button
              type="button"
              onClick={() => void runNow()}
              disabled={busy}
              className="flex items-center gap-1 rounded-md border border-emerald-400/30 bg-emerald-500/10 px-2 py-1 text-[10.5px] text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-40"
            >
              <Play size={10} /> Run now
            </button>
            <button
              type="button"
              onClick={() => void toggleEnabled()}
              disabled={busy}
              className="flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[10.5px] text-muted-foreground hover:text-foreground disabled:opacity-40"
            >
              <Square size={10} /> {schedule.enabled ? 'Pause' : 'Resume'}
            </button>
            <button
              type="button"
              onClick={() => void remove()}
              disabled={busy}
              title="Delete schedule"
              className="ml-auto rounded-md border border-rose-500/25 p-1 text-rose-300 hover:bg-rose-500/10 disabled:opacity-40"
            >
              <Trash2 size={11} />
            </button>
          </>
        )}
      </div>
    </div>
  );
}
