import { describe, it, expect, vi, afterEach } from 'vitest';
import { formatMonthLabel, formatDayLabel, weekdayShort } from './dates';

// ── UTC date formatting ──────────────────────────────────────────────────────
// Journal dates are UTC everywhere (day keys are the UTC slice of `exitTime`,
// `JournalDay.date` is UTC midnight). Formatting them in the browser's local
// zone made `Date.UTC(2026, 8, 1)` render as "August 2026" west of Greenwich —
// the month label sat one month behind the grid it described. These tests pin
// the UTC behaviour and prove it is independent of the machine's timezone.

const originalTz = process.env.TZ;
afterEach(() => {
  process.env.TZ = originalTz;
  vi.restoreAllMocks();
});

describe('formatMonthLabel', () => {
  it('renders the UTC month, not the local one', () => {
    expect(formatMonthLabel(2026, 8)).toBe('September 2026');
    expect(formatMonthLabel(2026, 0)).toBe('January 2026');
    expect(formatMonthLabel(2026, 11)).toBe('December 2026');
  });

  it('is stable across timezones that would otherwise shift the month', () => {
    for (const tz of ['UTC', 'America/Los_Angeles', 'Pacific/Honolulu', 'Asia/Karachi', 'Pacific/Kiritimati']) {
      process.env.TZ = tz;
      // Sept 1 UTC is Aug 31 in negative-offset zones — must still say September.
      expect(formatMonthLabel(2026, 8)).toBe('September 2026');
      // Jan 1 UTC is Dec 31 of the prior year in negative-offset zones.
      expect(formatMonthLabel(2026, 0)).toBe('January 2026');
    }
  });
});

describe('formatDayLabel', () => {
  it('renders a YYYY-MM-DD key verbatim in UTC', () => {
    expect(formatDayLabel('2026-09-16')).toBe('September 16, 2026');
    expect(formatDayLabel('2026-01-01')).toBe('January 1, 2026');
  });

  it('does not roll the day backwards across timezones', () => {
    for (const tz of ['UTC', 'America/Los_Angeles', 'Pacific/Honolulu', 'Asia/Karachi']) {
      process.env.TZ = tz;
      expect(formatDayLabel('2026-09-01')).toBe('September 1, 2026');
    }
  });

  it('returns the input unchanged when unparseable', () => {
    expect(formatDayLabel('not-a-date')).toBe('not-a-date');
    expect(formatDayLabel('')).toBe('');
  });
});

describe('weekdayShort', () => {
  it('names the UTC weekday for a day key', () => {
    // 2026-09-16 is a Wednesday.
    expect(weekdayShort('2026-09-16')).toBe('Wed');
    // 2026-09-20 is a Sunday.
    expect(weekdayShort('2026-09-20')).toBe('Sun');
  });

  it('is stable in a negative-offset timezone', () => {
    process.env.TZ = 'America/Los_Angeles';
    expect(weekdayShort('2026-09-16')).toBe('Wed');
  });
});
