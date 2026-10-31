import { describe, expect, it } from 'vitest';
import { buildCron, draftFromCron, nextRuns, DEFAULT_DRAFT } from './schedule-presets';

describe('schedule builder', () => {
  it('maps every frequency to a 5-field cron', () => {
    expect(buildCron({ ...DEFAULT_DRAFT, frequency: 'minutes', everyMinutes: 15 })).toBe('*/15 * * * *');
    expect(buildCron({ ...DEFAULT_DRAFT, frequency: 'hourly', minute: 5 })).toBe('5 * * * *');
    expect(buildCron({ ...DEFAULT_DRAFT, frequency: 'daily', hour: 9, minute: 30 })).toBe('30 9 * * *');
    expect(buildCron({ ...DEFAULT_DRAFT, frequency: 'weekly', hour: 8, minute: 0, weekdays: [5, 1, 1] }))
      .toBe('0 8 * * 1,5');
    expect(buildCron({ ...DEFAULT_DRAFT, frequency: 'monthly', hour: 7, minute: 15, dayOfMonth: 3 }))
      .toBe('15 7 3 * *');
    expect(buildCron({ ...DEFAULT_DRAFT, frequency: 'custom', cron: '0 9 1 * 1' })).toBe('0 9 1 * 1');
  });

  it('round-trips the common shapes', () => {
    expect(draftFromCron('*/10 * * * *')).toMatchObject({ frequency: 'minutes', everyMinutes: 10 });
    expect(draftFromCron('15 * * * *')).toMatchObject({ frequency: 'hourly', minute: 15 });
    expect(draftFromCron('0 9 * * *')).toMatchObject({ frequency: 'daily', hour: 9, minute: 0 });
    expect(draftFromCron('30 8 * * 1,3,5')).toMatchObject({
      frequency: 'weekly',
      weekdays: [1, 3, 5],
      hour: 8,
      minute: 30,
    });
    expect(draftFromCron('0 7 12 * *')).toMatchObject({ frequency: 'monthly', dayOfMonth: 12 });
    expect(draftFromCron('0 9 1 * 1')).toMatchObject({ frequency: 'custom' });
  });

  it('previews the next fires in the schedule timezone', () => {
    const from = new Date('2026-03-02T00:00:00.000Z'); // Monday
    const fires = nextRuns('0 9 * * 1-5', 'UTC', 3, from);
    expect(fires).toHaveLength(3);
    expect(fires.map((fire) => fire.iso)).toEqual([
      '2026-03-02T09:00:00.000Z',
      '2026-03-03T09:00:00.000Z',
      '2026-03-04T09:00:00.000Z',
    ]);
  });
});
