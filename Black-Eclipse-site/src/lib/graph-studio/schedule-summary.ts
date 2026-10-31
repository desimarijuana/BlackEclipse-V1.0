// ── Schedule summary (client) ────────────────────────────────────────────────
// A compact, human-readable description of a WorkflowSchedule for the node card.
// The Schedule tab remains the editor; this is read-only presentation.

import { draftFromCron, WEEKDAY_LABELS } from './schedule-presets';

export interface ScheduleNodeSummary {
  id: string;
  cron: string;
  timezone: string;
  enabled: boolean;
  nextRunAt: string | null;
  lastStatus: string | null;
  lastError: string | null;
  catchUp: 'skip' | 'coalesce';
}

const pad = (value: number): string => String(value).padStart(2, '0');

const isWeekdays = (days: number[]): boolean =>
  days.length === 5 && [1, 2, 3, 4, 5].every((day) => days.includes(day));

const isWeekends = (days: number[]): boolean =>
  days.length === 2 && days.includes(0) && days.includes(6);

/** "Weekdays at 09:00", "Every 15 min", "0 9 * * 1" for unparseable shapes. */
export function describeSchedule(cron: string): string {
  const draft = draftFromCron(cron);
  const time = `${pad(draft.hour)}:${pad(draft.minute)}`;
  switch (draft.frequency) {
    case 'minutes':
      return `Every ${draft.everyMinutes} min`;
    case 'hourly':
      return `Hourly at :${pad(draft.minute)}`;
    case 'daily':
      return `Daily at ${time}`;
    case 'weekly': {
      const days = [...new Set(draft.weekdays)].sort((a, b) => a - b);
      const label = isWeekdays(days)
        ? 'Weekdays'
        : isWeekends(days)
          ? 'Weekends'
          : days.map((day) => WEEKDAY_LABELS[day]).join(', ');
      return `${label || 'Weekly'} at ${time}`;
    }
    case 'monthly':
      return `Monthly on day ${draft.dayOfMonth} at ${time}`;
    default:
      return cron;
  }
}

/** The next fire in the schedule's own timezone, or null. */
export function formatNextFire(iso: string | null, timezone: string): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  try {
    return date.toLocaleString(undefined, {
      timeZone: timezone,
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}
