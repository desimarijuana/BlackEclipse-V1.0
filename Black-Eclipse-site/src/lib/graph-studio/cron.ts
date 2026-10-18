// ── Timezone-aware cron (5 fields) ───────────────────────────────────────────
// Workflow schedules must fire at a wall-clock time in the OWNER's timezone, not
// the server's. This computes the next instant a 5-field cron expression matches
// IN a named IANA timezone, using Intl's zone database — no dependency, no
// server-local assumptions.
//
// Supported syntax (standard crontab): `*`, `a`, `a-b`, `*/n`, `a-b/n`, lists.
// Day-of-month + day-of-week follow cron's OR rule when BOTH are restricted.
//
// Bounded by construction: the search scans minute by minute for at most
// MAX_SEARCH_MINUTES (40 days), then gives up — a schedule that cannot fire in
// 40 days (e.g. Feb 30) reports null rather than spinning.

const MAX_SEARCH_MINUTES = 40 * 24 * 60;
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

interface Field {
  min: number;
  max: number;
  allowed: Set<number>;
  restricted: boolean;
}

export interface ParsedCron {
  minute: Field;
  hour: Field;
  dayOfMonth: Field;
  month: Field;
  dayOfWeek: Field;
}

function parseField(raw: string, min: number, max: number, label: string): Field {
  const text = raw.trim();
  if (!text) throw new Error(`cron: empty ${label} field`);
  const allowed = new Set<number>();
  const restricted = text !== '*';
  for (const part of text.split(',')) {
    const [rangePart, stepPart] = part.split('/');
    const step = stepPart === undefined ? 1 : Number(stepPart);
    if (!Number.isInteger(step) || step < 1) throw new Error(`cron: bad step in ${label} field`);
    let start = min;
    let end = max;
    if (rangePart !== '*') {
      const bounds = rangePart.split('-');
      const lo = Number(bounds[0]);
      const hi = bounds.length > 1 ? Number(bounds[1]) : lo;
      if (!Number.isInteger(lo) || !Number.isInteger(hi) || lo < min || hi > max || lo > hi) {
        throw new Error(`cron: bad range in ${label} field`);
      }
      start = lo;
      end = hi;
    }
    for (let value = start; value <= end; value += step) allowed.add(value);
  }
  if (allowed.size === 0) throw new Error(`cron: ${label} field matches nothing`);
  return { min, max, allowed, restricted };
}

export function parseCron(expression: string): ParsedCron {
  const fields = expression.trim().split(/\s+/);
  if (fields.length !== 5) throw new Error('cron: expected 5 fields (minute hour day-of-month month day-of-week)');
  return {
    minute: parseField(fields[0], 0, 59, 'minute'),
    hour: parseField(fields[1], 0, 23, 'hour'),
    dayOfMonth: parseField(fields[2], 1, 31, 'day-of-month'),
    // Cron months are 1..12; Intl reports names, so map back below.
    month: parseField(fields[3], 1, 12, 'month'),
    dayOfWeek: parseField(fields[4], 0, 6, 'day-of-week'),
  };
}

export function isValidCron(expression: string): boolean {
  try {
    parseCron(expression);
    return true;
  } catch {
    return false;
  }
}

// `Intl.DateTimeFormat` construction is the expensive part of a timezone
// conversion (a minute-by-minute search does tens of thousands of them), so one
// formatter is cached per zone.
const FORMATTERS = new Map<string, Intl.DateTimeFormat>();

function formatterFor(timezone: string): Intl.DateTimeFormat {
  const cached = FORMATTERS.get(timezone);
  if (cached) return cached;
  let formatter: Intl.DateTimeFormat;
  try {
    formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      hour12: false,
      weekday: 'short',
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    throw new Error(`cron: unknown timezone "${timezone}"`);
  }
  FORMATTERS.set(timezone, formatter);
  return formatter;
}

function assertTimezone(timezone: string): void {
  formatterFor(timezone);
}

/** The civil parts of an instant in a named timezone. */
export function civilParts(instant: Date, timezone: string) {
  const parts = formatterFor(timezone).formatToParts(instant);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
  return {
    minute: Number(get('minute')),
    hour: Number(get('hour')) % 24,
    dayOfMonth: Number(get('day')),
    month: MONTHS.indexOf(get('month')) + 1,
    dayOfWeek: WEEKDAYS.indexOf(get('weekday')),
  };
}

function matches(cron: ParsedCron, instant: Date, timezone: string): boolean {
  const civil = civilParts(instant, timezone);
  if (!cron.minute.allowed.has(civil.minute)) return false;
  if (!cron.hour.allowed.has(civil.hour)) return false;
  if (!cron.month.allowed.has(civil.month)) return false;
  const domOk = cron.dayOfMonth.allowed.has(civil.dayOfMonth);
  const dowOk = cron.dayOfWeek.allowed.has(civil.dayOfWeek);
  if (cron.dayOfMonth.restricted && cron.dayOfWeek.restricted) return domOk || dowOk;
  if (cron.dayOfMonth.restricted) return domOk;
  if (cron.dayOfWeek.restricted) return dowOk;
  return true;
}

/**
 * The next instant STRICTLY AFTER `from` that the expression matches in
 * `timezone`, or null when it cannot fire within 40 days.
 */
export function nextRunAt(expression: string, timezone: string, from: Date): Date | null {
  const cron = parseCron(expression);
  assertTimezone(timezone);
  // Start at the next whole minute (cron granularity is minutes).
  const start = new Date(Math.floor(from.getTime() / 60_000) * 60_000 + 60_000);
  for (let i = 0; i < MAX_SEARCH_MINUTES; i += 1) {
    const candidate = new Date(start.getTime() + i * 60_000);
    if (matches(cron, candidate, timezone)) return candidate;
  }
  return null;
}
