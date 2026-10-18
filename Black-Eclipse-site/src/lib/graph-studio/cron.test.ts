import { describe, expect, it } from 'vitest';
import { civilParts, isValidCron, nextRunAt, parseCron } from './cron';

const ISO = (d: Date | null) => (d ? d.toISOString() : null);

describe('cron parsing', () => {
  it('accepts standard 5-field expressions', () => {
    for (const expr of ['0 9 * * 1-5', '*/15 0-23/2 1,15 * *', '0 0 1 1 *', '* * * * *']) {
      expect(isValidCron(expr), expr).toBe(true);
    }
  });

  it('rejects malformed expressions', () => {
    for (const expr of ['0 9 * *', '60 9 * * *', '0 24 * * *', '0 0 0 * *', '0 0 * 13 *', '0 0 * * 7', 'a b c d e', '*/0 * * * *', '']) {
      expect(isValidCron(expr), expr).toBe(false);
    }
  });

  it('parses ranges, lists and steps', () => {
    const parsed = parseCron('*/15 1,3 5-7 * *');
    expect([...parsed.minute.allowed].sort((a, b) => a - b)).toEqual([0, 15, 30, 45]);
    expect([...parsed.hour.allowed].sort((a, b) => a - b)).toEqual([1, 3]);
    expect([...parsed.dayOfMonth.allowed]).toEqual([5, 6, 7]);
    expect(parsed.dayOfMonth.restricted).toBe(true);
    expect(parsed.dayOfWeek.restricted).toBe(false);
  });
});

describe('next run time', () => {
  const from = new Date('2026-01-01T00:00:00Z'); // a Thursday

  it('finds the next matching minute in UTC', () => {
    expect(ISO(nextRunAt('0 9 * * *', 'UTC', from))).toBe('2026-01-01T09:00:00.000Z');
    expect(ISO(nextRunAt('*/15 * * * *', 'UTC', from))).toBe('2026-01-01T00:15:00.000Z');
    expect(ISO(nextRunAt('30 14 * * *', 'UTC', from))).toBe('2026-01-01T14:30:00.000Z');
  });

  it('respects the schedule timezone, not the server clock', () => {
    const next = nextRunAt('0 9 * * *', 'America/New_York', from);
    const parts = civilParts(next as Date, 'America/New_York');
    expect(parts.hour).toBe(9);
    expect(parts.minute).toBe(0);
    // 09:00 EST is 14:00 UTC.
    expect(ISO(next)).toBe('2026-01-01T14:00:00.000Z');

    // 00:00Z is already 09:00 in Tokyo, so the NEXT 09:00 is the following day.
    const tokyo = nextRunAt('0 9 * * *', 'Asia/Tokyo', from);
    expect(civilParts(tokyo as Date, 'Asia/Tokyo').hour).toBe(9);
    expect(ISO(tokyo)).toBe('2026-01-02T00:00:00.000Z');
  });

  it('handles weekdays and the day-of-month / day-of-week OR rule', () => {
    const monday = nextRunAt('0 9 * * 1', 'UTC', from);
    expect(civilParts(monday as Date, 'UTC').dayOfWeek).toBe(1); // Mon
    expect(ISO(monday)).toBe('2026-01-05T09:00:00.000Z');

    // 1st of the month OR Monday → the earlier of the two.
    const orRule = nextRunAt('0 0 1 * 1', 'UTC', from);
    expect(ISO(orRule)).toBe('2026-01-05T00:00:00.000Z');
  });

  it('returns null for an expression that can never fire', () => {
    expect(nextRunAt('0 0 31 2 *', 'UTC', from)).toBeNull();
  });

  it('is strictly after the reference instant', () => {
    const at = new Date('2026-01-01T09:00:00Z');
    expect(ISO(nextRunAt('0 9 * * *', 'UTC', at))).toBe('2026-01-02T09:00:00.000Z');
  });

  it('rejects an unknown timezone', () => {
    expect(() => nextRunAt('0 9 * * *', 'Mars/Olympus', from)).toThrow();
  });
});
