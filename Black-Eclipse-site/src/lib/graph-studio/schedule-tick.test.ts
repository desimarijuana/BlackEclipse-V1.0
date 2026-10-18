import { beforeEach, describe, expect, it, vi } from 'vitest';
import { runDueSchedules } from './schedule-tick';
import { dueSchedules, recordScheduleRun } from './schedule-store';
import { startPersistedRun } from './run-server';
import type { ScheduleRecord } from './schedule-store';

vi.mock('./schedule-store', () => ({
  dueSchedules: vi.fn(),
  recordScheduleRun: vi.fn(),
}));
vi.mock('./run-server', () => ({
  startPersistedRun: vi.fn(),
}));

const mockDue = vi.mocked(dueSchedules);
const mockRecord = vi.mocked(recordScheduleRun);
const mockStart = vi.mocked(startPersistedRun);

function schedule(overrides: Partial<ScheduleRecord> = {}): ScheduleRecord {
  return {
    id: 'sched_1',
    workflowId: 'wf_1',
    name: 'Daily',
    cron: '0 9 * * *',
    timezone: 'UTC',
    enabled: true,
    catchUp: 'skip',
    version: null,
    lastRunAt: null,
    lastRunId: null,
    lastStatus: null,
    lastError: null,
    nextRunAt: '2026-01-01T09:00:00.000Z',
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-01T00:00:00.000Z',
    ...overrides,
  };
}

const NOW = new Date('2026-01-01T09:00:30.000Z');

describe('schedule tick', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRecord.mockResolvedValue(null);
  });

  it('fires an on-time schedule through the test-run dispatch', async () => {
    mockDue.mockResolvedValue([schedule()]);
    mockStart.mockResolvedValue({ ok: true, status: 201, run: { id: 'grun_9' } });
    const outcomes = await runDueSchedules(NOW);
    expect(mockStart).toHaveBeenCalledWith({ workflowId: 'wf_1', version: null, testRun: true });
    expect(mockRecord).toHaveBeenCalledWith('sched_1', { runId: 'grun_9', status: 'started' }, NOW);
    expect(outcomes).toEqual([{ scheduleId: 'sched_1', workflowId: 'wf_1', action: 'started', runId: 'grun_9' }]);
  });

  it('skips a missed fire under the skip policy (no storm on boot)', async () => {
    mockDue.mockResolvedValue([
      schedule({ nextRunAt: '2026-01-01T08:00:00.000Z' }), // an hour late
    ]);
    const outcomes = await runDueSchedules(NOW);
    expect(mockStart).not.toHaveBeenCalled();
    expect(mockRecord).toHaveBeenCalledWith('sched_1', { status: 'skipped-missed' }, NOW);
    expect(outcomes[0].action).toBe('skipped-missed');
  });

  it('coalesces a missed fire when the schedule asks for it', async () => {
    mockDue.mockResolvedValue([
      schedule({ nextRunAt: '2026-01-01T08:00:00.000Z', catchUp: 'coalesce' }),
    ]);
    mockStart.mockResolvedValue({ ok: true, status: 201, run: { id: 'grun_10' } });
    const outcomes = await runDueSchedules(NOW);
    expect(mockStart).toHaveBeenCalledTimes(1);
    expect(outcomes[0]).toMatchObject({ action: 'started', runId: 'grun_10' });
  });

  it('records a failed fire instead of hiding it', async () => {
    mockDue.mockResolvedValue([schedule()]);
    mockStart.mockResolvedValue({ ok: false, status: 503, error: 'runtime unavailable' });
    const outcomes = await runDueSchedules(NOW);
    expect(mockRecord).toHaveBeenCalledWith(
      'sched_1',
      { status: 'error', error: 'runtime unavailable' },
      NOW,
    );
    expect(outcomes[0]).toMatchObject({ action: 'error', error: 'runtime unavailable' });
  });

  it('does nothing when no schedule is due', async () => {
    mockDue.mockResolvedValue([]);
    expect(await runDueSchedules(NOW)).toEqual([]);
    expect(mockStart).not.toHaveBeenCalled();
  });
});
