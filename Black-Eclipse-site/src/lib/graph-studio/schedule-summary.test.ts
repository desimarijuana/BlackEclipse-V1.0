import { describe, expect, it } from 'vitest';
import { describeSchedule, formatNextFire } from './schedule-summary';

describe('schedule summary', () => {
  it('describes the common cron shapes', () => {
    expect(describeSchedule('0 9 * * *')).toBe('Daily at 09:00');
    expect(describeSchedule('30 8 * * 1,2,3,4,5')).toBe('Weekdays at 08:30');
    expect(describeSchedule('0 10 * * 0,6')).toBe('Weekends at 10:00');
    expect(describeSchedule('0 7 * * 1,3')).toBe('Mon, Wed at 07:00');
    expect(describeSchedule('15 6 12 * *')).toBe('Monthly on day 12 at 06:15');
    expect(describeSchedule('*/15 * * * *')).toBe('Every 15 min');
    expect(describeSchedule('5 * * * *')).toBe('Hourly at :05');
  });

  it('falls back to the raw expression for custom shapes', () => {
    expect(describeSchedule('0 9 1 * 1')).toBe('0 9 1 * 1');
  });

  it('formats the next fire in the given timezone', () => {
    const result = formatNextFire('2026-03-02T09:00:00.000Z', 'UTC');
    expect(result).toContain('Mar');
    expect(result).toContain('9:00');
    expect(formatNextFire(null, 'UTC')).toBeNull();
    expect(formatNextFire('not-a-date', 'UTC')).toBeNull();
  });
});
