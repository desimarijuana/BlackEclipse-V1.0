// ── Schedule tick ────────────────────────────────────────────────────────────
// Fires every workflow schedule whose time has come. Called by the boot timer
// (60 s) and by the operator tick route, so unattended runs work while the app
// is up without any external scheduler.
//
// Missed fires (the app was closed) never storm: a fire more than GRACE_MS late
// is either SKIPPED (just advance to the next occurrence) or COALESCED (run once
// now) per the schedule's policy.
//
// Server-only.

import { dueSchedules, recordScheduleRun } from './schedule-store';
import { startPersistedRun } from './run-server';

const GRACE_MS = 120_000;

export interface TickOutcome {
  scheduleId: string;
  workflowId: string;
  action: 'started' | 'skipped-missed' | 'error';
  runId?: string;
  error?: string;
}

export async function runDueSchedules(now = new Date()): Promise<TickOutcome[]> {
  const due = await dueSchedules(now);
  const outcomes: TickOutcome[] = [];

  for (const schedule of due) {
    const scheduledFor = schedule.nextRunAt ? new Date(schedule.nextRunAt) : null;
    const late = scheduledFor ? now.getTime() - scheduledFor.getTime() > GRACE_MS : false;

    if (late && schedule.catchUp === 'skip') {
      await recordScheduleRun(schedule.id, { status: 'skipped-missed' }, now);
      outcomes.push({ scheduleId: schedule.id, workflowId: schedule.workflowId, action: 'skipped-missed' });
      continue;
    }

    const result = await startPersistedRun({
      workflowId: schedule.workflowId,
      version: schedule.version,
      testRun: true,
    });
    if (result.ok) {
      const runId = (result.run as { id?: string } | undefined)?.id;
      await recordScheduleRun(schedule.id, { runId, status: 'started' }, now);
      outcomes.push({ scheduleId: schedule.id, workflowId: schedule.workflowId, action: 'started', runId });
    } else {
      await recordScheduleRun(schedule.id, { status: 'error', error: result.error }, now);
      outcomes.push({
        scheduleId: schedule.id,
        workflowId: schedule.workflowId,
        action: 'error',
        error: result.error,
      });
    }
  }

  return outcomes;
}
