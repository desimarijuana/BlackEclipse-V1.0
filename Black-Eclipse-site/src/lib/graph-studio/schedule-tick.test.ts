import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { runDueSchedules } from './schedule-tick';
import {
  claimScheduleFire,
  dueSchedules,
  pauseSchedule,
  pendingScheduleRuns,
  recordScheduleFire,
  recordScheduleOutcome,
  recordScheduleSkip,
} from './schedule-store';
import { startPersistedRun } from './run-server';
import { getWorkflow } from './server-store';
import type { ScheduleRecord } from './schedule-store';

vi.mock('./schedule-store', () => ({
  dueSchedules: vi.fn(),
  claimScheduleFire: vi.fn(),
  getSchedule: vi.fn(),
  pauseSchedule: vi.fn(),
  pendingScheduleRuns: vi.fn(),
  recordScheduleFire: vi.fn(),
  recordScheduleOutcome: vi.fn(),
  recordScheduleSkip: vi.fn(),
}));
vi.mock('./server-store', () => ({
  getWorkflow: vi.fn(),
}));
vi.mock('./run-server', () => ({
  startPersistedRun: vi.fn(),
}));

const mockDue = vi.mocked(dueSchedules);
const mockClaim = vi.mocked(claimScheduleFire);
const mockGetWorkflow = vi.mocked(getWorkflow);
const mockPause = vi.mocked(pauseSchedule);
const mockPending = vi.mocked(pendingScheduleRuns);
const mockRecordFire = vi.mocked(recordScheduleFire);
const mockRecordOutcome = vi.mocked(recordScheduleOutcome);
const mockRecordSkip = vi.mocked(recordScheduleSkip);
const mockStart = vi.mocked(startPersistedRun);

function schedule(overrides: Partial<ScheduleRecord> = {}): ScheduleRecord {
  return {
    id: 'sched_1',
    workflowId: 'wf_1',
    nodeId: null,
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
    mockPending.mockResolvedValue([]);
    mockClaim.mockResolvedValue(true);
    mockRecordFire.mockResolvedValue(null);
    mockRecordOutcome.mockResolvedValue(undefined);
    mockRecordSkip.mockResolvedValue(undefined);
    mockPause.mockResolvedValue(undefined);
    mockGetWorkflow.mockResolvedValue(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('claims and fires an on-time schedule through the test-run dispatch', async () => {
    mockDue.mockResolvedValue([schedule()]);
    mockStart.mockResolvedValue({ ok: true, status: 201, run: { id: 'grun_9' } });
    const outcomes = await runDueSchedules(NOW);
    expect(mockClaim).toHaveBeenCalledWith('sched_1', new Date('2026-01-01T09:00:00.000Z'), NOW);
    expect(mockStart).toHaveBeenCalledWith({ workflowId: 'wf_1', version: null, testRun: true });
    expect(mockRecordFire).toHaveBeenCalledWith('sched_1', { runId: 'grun_9', status: 'started' }, NOW);
    expect(outcomes).toEqual([{ scheduleId: 'sched_1', workflowId: 'wf_1', action: 'started', runId: 'grun_9' }]);
  });

  it('never fires a due row that another tick claimed first', async () => {
    mockDue.mockResolvedValue([schedule()]);
    mockClaim.mockResolvedValue(false);
    const outcomes = await runDueSchedules(NOW);
    expect(mockStart).not.toHaveBeenCalled();
    expect(mockRecordFire).not.toHaveBeenCalled();
    expect(outcomes).toEqual([]);
  });

  it('skips a missed fire under the skip policy (no storm on boot)', async () => {
    mockDue.mockResolvedValue([
      schedule({ nextRunAt: '2026-01-01T08:00:00.000Z' }), // an hour late
    ]);
    const outcomes = await runDueSchedules(NOW);
    expect(mockStart).not.toHaveBeenCalled();
    expect(mockRecordSkip).toHaveBeenCalledWith('sched_1');
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
    expect(mockRecordFire).toHaveBeenCalledWith(
      'sched_1',
      { status: 'error', error: 'runtime unavailable' },
      NOW,
    );
    expect(outcomes[0]).toMatchObject({ action: 'error', error: 'runtime unavailable' });
  });

  it('pauses a schedule whose trigger node was deleted instead of firing it', async () => {
    mockDue.mockResolvedValue([schedule({ nodeId: 'trig_1' })]);
    mockGetWorkflow.mockResolvedValue({ ir: { nodes: [] } } as never);
    const outcomes = await runDueSchedules(NOW);
    expect(mockPause).toHaveBeenCalledWith('sched_1', expect.stringContaining('removed'));
    expect(mockClaim).not.toHaveBeenCalled();
    expect(mockStart).not.toHaveBeenCalled();
    expect(outcomes[0]).toMatchObject({ action: 'error' });
  });

  it('does not pause a schedule on a transient workflow read failure', async () => {
    mockDue.mockResolvedValue([schedule({ nodeId: 'trig_1' })]);
    mockGetWorkflow.mockRejectedValue(new Error('database busy'));
    const outcomes = await runDueSchedules(NOW);
    expect(mockPause).not.toHaveBeenCalled();
    expect(mockClaim).not.toHaveBeenCalled();
    expect(outcomes[0]).toMatchObject({ action: 'error' });
  });

  it('fires when the linked trigger node still exists', async () => {
    mockDue.mockResolvedValue([schedule({ nodeId: 'trig_1' })]);
    mockGetWorkflow.mockResolvedValue({
      ir: { nodes: [{ id: 'trig_1', type: 'trigger.schedule' }] },
    } as never);
    mockStart.mockResolvedValue({ ok: true, status: 201, run: { id: 'grun_11' } });
    const outcomes = await runDueSchedules(NOW);
    expect(mockPause).not.toHaveBeenCalled();
    expect(mockStart).toHaveBeenCalledTimes(1);
    expect(outcomes[0]).toMatchObject({ action: 'started', runId: 'grun_11' });
  });

  it('reconciles a started run once the runtime reports a terminal state', async () => {
    mockPending.mockResolvedValue([schedule({
      lastStatus: 'started',
      lastRunId: 'grun_9',
      lastRunAt: '2026-01-01T08:59:00.000Z',
    })]);
    mockDue.mockResolvedValue([]);
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ run: { status: 'succeeded' } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    await runDueSchedules(NOW);
    expect(mockRecordOutcome).toHaveBeenCalledWith('sched_1', 'succeeded');
  });
});
