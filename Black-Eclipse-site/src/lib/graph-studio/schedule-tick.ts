// ── Schedule tick ────────────────────────────────────────────────────────────
// Fires every workflow schedule whose time has come. Called by the boot timer
// (60 s) and by the operator tick route, so unattended runs work while the app
// is up without any external scheduler.
//
// Idempotency: each due fire is CLAIMED with a compare-and-set on its exact
// `nextRunAt` before a run starts. Two overlapping ticks (or two server
// processes) may both see the row, but only the winner fires.
//
// Missed fires (the app was closed) never storm: a fire more than GRACE_MS late
// is either SKIPPED (just advance to the next occurrence) or COALESCED (run once
// now) per the schedule's policy.
//
// A fire records `started` immediately. Once the runtime reports a terminal
// state, the next tick reconciles `lastStatus` from the run, so "last status" is
// never permanently stuck at `started`.
//
// Server-only.

import { HARNESS_PY_URL } from '@/lib/harness/python-runtime';
import { runtimeCallbackToken } from '@/lib/harness/runtime-auth';
import {
  claimScheduleFire,
  dueSchedules,
  getSchedule,
  pauseSchedule,
  pendingScheduleRuns,
  recordScheduleFire,
  recordScheduleOutcome,
  recordScheduleSkip,
} from './schedule-store';
import { getWorkflow } from './server-store';
import { startPersistedRun } from './run-server';

const GRACE_MS = 120_000;
const TERMINAL = new Set(['succeeded', 'failed', 'cancelled']);

export interface TickOutcome {
  scheduleId: string;
  workflowId: string;
  action: 'started' | 'skipped-missed' | 'error';
  runId?: string;
  error?: string;
}

// Overlap guard: one tick at a time in this process. The DB CAS still protects
// against a second process.
let ticking = false;

async function runtimeRunStatus(runId: string): Promise<string | null> {
  try {
    const token = runtimeCallbackToken();
    const res = await fetch(`${HARNESS_PY_URL}/graphs/runs/${encodeURIComponent(runId)}`, {
      headers: token ? { 'X-Harness-Operator': token } : {},
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) return null;
    const data = (await res.json().catch(() => ({}))) as {
      run?: { status?: string };
    };
    return data.run?.status ?? null;
  } catch {
    return null;
  }
}

/** Reconcile fires whose run has since finished. Best-effort, bounded. */
async function reconcileOutcomes(): Promise<void> {
  let pending;
  try {
    pending = await pendingScheduleRuns();
  } catch {
    return;
  }
  for (const schedule of pending) {
    if (!schedule.lastRunId) continue;
    const status = await runtimeRunStatus(schedule.lastRunId);
    if (status && TERMINAL.has(status)) {
      try {
        await recordScheduleOutcome(schedule.id, status);
      } catch {
        // A status write must never stop a tick.
      }
    }
  }
}

export async function runDueSchedules(now = new Date()): Promise<TickOutcome[]> {
  if (ticking) return [];
  ticking = true;
  try {
    await reconcileOutcomes();
    const due = await dueSchedules(now);
    const outcomes: TickOutcome[] = [];

    for (const schedule of due) {
      const scheduledFor = schedule.nextRunAt ? new Date(schedule.nextRunAt) : null;
      if (!scheduledFor) continue;

      // Integrity: a schedule linked to a trigger node must not fire after that
      // node is deleted from the workflow. Pause it (with a visible reason)
      // instead of running the graph from a trigger that no longer exists.
      if (schedule.nodeId) {
        let workflow;
        try {
          workflow = await getWorkflow(schedule.workflowId);
        } catch {
          // A transient read failure must not pause a healthy schedule; leave
          // nextRunAt untouched so the next tick retries.
          outcomes.push({
            scheduleId: schedule.id,
            workflowId: schedule.workflowId,
            action: 'error',
            error: 'Workflow could not be read; will retry next tick.',
          });
          continue;
        }
        const triggerExists = workflow?.ir.nodes.some(
          (node) => node.id === schedule.nodeId && node.type === 'trigger.schedule',
        );
        if (!workflow || !triggerExists) {
          const error = 'The linked trigger.schedule node was removed; schedule paused.';
          await pauseSchedule(schedule.id, error);
          outcomes.push({
            scheduleId: schedule.id,
            workflowId: schedule.workflowId,
            action: 'error',
            error,
          });
          continue;
        }
      }

      // Claim first: only the winner may run or record this occurrence.
      const claimed = await claimScheduleFire(schedule.id, scheduledFor, now);
      if (!claimed) continue;

      const late = now.getTime() - scheduledFor.getTime() > GRACE_MS;
      if (late && schedule.catchUp === 'skip') {
        await recordScheduleSkip(schedule.id);
        outcomes.push({ scheduleId: schedule.id, workflowId: schedule.workflowId, action: 'skipped-missed' });
        continue;
      }

      try {
        const result = await startPersistedRun({
          workflowId: schedule.workflowId,
          version: schedule.version,
          testRun: true,
        });
        if (result.ok) {
          const runId = (result.run as { id?: string } | undefined)?.id;
          await recordScheduleFire(schedule.id, { runId, status: 'started' }, now);
          outcomes.push({ scheduleId: schedule.id, workflowId: schedule.workflowId, action: 'started', runId });
        } else {
          await recordScheduleFire(schedule.id, { status: 'error', error: result.error }, now);
          outcomes.push({
            scheduleId: schedule.id,
            workflowId: schedule.workflowId,
            action: 'error',
            error: result.error,
          });
        }
      } catch (err) {
        // The claim already advanced the clock; surface the failure and keep
        // the other due schedules running.
        const message = err instanceof Error ? err.message : 'schedule fire failed';
        await recordScheduleFire(schedule.id, { status: 'error', error: message }, now).catch(() => null);
        outcomes.push({
          scheduleId: schedule.id,
          workflowId: schedule.workflowId,
          action: 'error',
          error: message,
        });
      }
    }

    return outcomes;
  } finally {
    ticking = false;
  }
}

/** Fire one schedule immediately (the "Run now" action), ignoring its clock. */
export async function runScheduleNow(scheduleId: string): Promise<TickOutcome> {
  const schedule = await getSchedule(scheduleId);
  if (!schedule) {
    return { scheduleId, workflowId: '', action: 'error', error: 'Schedule not found' };
  }
  const result = await startPersistedRun({
    workflowId: schedule.workflowId,
    version: schedule.version,
    testRun: true,
  });
  if (!result.ok) {
    await recordScheduleFire(schedule.id, { status: 'error', error: result.error });
    return { scheduleId, workflowId: schedule.workflowId, action: 'error', error: result.error };
  }
  const runId = (result.run as { id?: string } | undefined)?.id;
  await recordScheduleFire(schedule.id, { runId, status: 'started' });
  return { scheduleId, workflowId: schedule.workflowId, action: 'started', runId };
}
