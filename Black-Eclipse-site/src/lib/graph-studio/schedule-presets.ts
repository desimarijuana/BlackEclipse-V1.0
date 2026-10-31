// ── Schedule builder ─────────────────────────────────────────────────────────
// The friendly time controls map to the SAME 5-field cron the scheduler already
// understands. This module is pure so the inspector can preview the next fires
// without a round trip, and so the mapping is unit-testable.

import { nextRunAt } from './cron';

export type ScheduleFrequency = 'minutes' | 'hourly' | 'daily' | 'weekly' | 'monthly' | 'custom';

export interface ScheduleDraft {
  frequency: ScheduleFrequency;
  /** minutes frequency: fire every N minutes (1–59). */
  everyMinutes: number;
  /** minute within the hour (hourly/daily/weekly/monthly). */
  minute: number;
  /** hour of day (daily/weekly/monthly). */
  hour: number;
  /** weekly: 0 = Sunday … 6 = Saturday. */
  weekdays: number[];
  /** monthly: 1–31. */
  dayOfMonth: number;
  /** custom expression; ignored by the other frequencies. */
  cron: string;
}

export const WEEKDAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export const DEFAULT_DRAFT: ScheduleDraft = {
  frequency: 'daily',
  everyMinutes: 15,
  minute: 0,
  hour: 9,
  weekdays: [1, 2, 3, 4, 5],
  dayOfMonth: 1,
  cron: '0 9 * * *',
};

const clamp = (value: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, Math.trunc(value)));

export function buildCron(draft: ScheduleDraft): string {
  const minute = clamp(draft.minute, 0, 59);
  const hour = clamp(draft.hour, 0, 23);
  switch (draft.frequency) {
    case 'minutes':
      return `*/${clamp(draft.everyMinutes, 1, 59)} * * * *`;
    case 'hourly':
      return `${minute} * * * *`;
    case 'daily':
      return `${minute} ${hour} * * *`;
    case 'weekly': {
      const days = [...new Set(draft.weekdays.map((day) => clamp(day, 0, 6)))].sort((a, b) => a - b);
      return `${minute} ${hour} * * ${days.length > 0 ? days.join(',') : '*'}`;
    }
    case 'monthly':
      return `${minute} ${hour} ${clamp(draft.dayOfMonth, 1, 31)} * *`;
    case 'custom':
    default:
      return draft.cron.trim();
  }
}

/** Best-effort inverse of `buildCron`; anything unusual stays `custom`. */
export function draftFromCron(cron: string): ScheduleDraft {
  const fields = cron.trim().split(/\s+/);
  if (fields.length !== 5) return { ...DEFAULT_DRAFT, frequency: 'custom', cron };
  const [min, hr, dom, mon, dow] = fields;
  const custom = (): ScheduleDraft => ({ ...DEFAULT_DRAFT, frequency: 'custom', cron });
  if (mon !== '*' || (dom !== '*' && dow !== '*')) return custom();

  const minuteMatch = /^\*\/(\d{1,2})$/.exec(min);
  if (minuteMatch && hr === '*' && dom === '*' && dow === '*') {
    return { ...DEFAULT_DRAFT, frequency: 'minutes', everyMinutes: Number(minuteMatch[1]) };
  }
  if (hr === '*' && dom === '*' && dow === '*' && /^\d{1,2}$/.test(min)) {
    return { ...DEFAULT_DRAFT, frequency: 'hourly', minute: Number(min) };
  }
  if (!/^\d{1,2}$/.test(min) || !/^\d{1,2}$/.test(hr)) return custom();
  const base = { ...DEFAULT_DRAFT, minute: Number(min), hour: Number(hr) };
  if (dom === '*' && dow === '*') return { ...base, frequency: 'daily' };
  if (dom === '*' && /^[0-6](,[0-6])*$/.test(dow)) {
    return { ...base, frequency: 'weekly', weekdays: dow.split(',').map(Number) };
  }
  if (/^\d{1,2}$/.test(dom) && dow === '*') {
    return { ...base, frequency: 'monthly', dayOfMonth: Number(dom) };
  }
  return custom();
}

export interface FireTime {
  iso: string;
  local: string;
}

/** The next `count` fires, formatted in the schedule's timezone. */
export function nextRuns(
  cron: string,
  timezone: string,
  count = 3,
  from = new Date(),
): FireTime[] {
  const fires: FireTime[] = [];
  let cursor = from;
  for (let index = 0; index < count; index += 1) {
    const next = nextRunAt(cron, timezone, cursor);
    if (!next) break;
    fires.push({
      iso: next.toISOString(),
      local: next.toLocaleString(undefined, { timeZone: timezone, dateStyle: 'medium', timeStyle: 'short' }),
    });
    cursor = next;
  }
  return fires;
}

/** Timezone options: the platform's full list plus a stable fallback. */
export function timezoneOptions(current?: string | null): string[] {
  const fallback = [
    'UTC', 'Africa/Cairo', 'Africa/Johannesburg', 'America/Chicago', 'America/Los_Angeles',
    'America/New_York', 'America/Sao_Paulo', 'Asia/Dubai', 'Asia/Karachi', 'Asia/Kolkata',
    'Asia/Shanghai', 'Asia/Singapore', 'Asia/Tokyo', 'Australia/Sydney', 'Europe/Berlin',
    'Europe/London', 'Europe/Paris', 'Pacific/Auckland',
  ];
  let zones: string[] = fallback;
  try {
    const supported = (Intl as unknown as { supportedValuesOf?: (key: string) => string[] })
      .supportedValuesOf?.('timeZone');
    if (supported && supported.length > 0) zones = supported;
  } catch {
    zones = fallback;
  }
  const all = new Set<string>(['UTC', ...zones]);
  if (current) all.add(current);
  return [...all].sort((a, b) => a.localeCompare(b));
}
