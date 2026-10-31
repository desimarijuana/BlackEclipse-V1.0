// ── Workflow schedules — persistence + the due-work query ────────────────────
// Server-only. A schedule stores a cron expression + IANA timezone and a
// PRECOMPUTED `nextRunAt`, so the tick is one indexed query. The last outcome is
// kept so a failing schedule is visible instead of silently retrying.
//
// Missed-fire policy: when the app was closed across fire times, the tick sees
// `nextRunAt` in the past. `catchUp: 'coalesce'` runs once now; `'skip'` just
// advances to the next future occurrence. Either way it never runs N times to
// "catch up" — a schedule must not storm on boot.

import { prisma } from '@/lib/db';
import { isValidCron, isValidTimezone, nextRunAt, parseCron } from './cron';

export interface ScheduleRecord {
  id: string;
  workflowId: string;
  /** The trigger.schedule node this schedule belongs to, when there is one. */
  nodeId: string | null;
  name: string;
  cron: string;
  timezone: string;
  enabled: boolean;
  catchUp: 'skip' | 'coalesce';
  version: number | null;
  lastRunAt: string | null;
  lastRunId: string | null;
  lastStatus: string | null;
  lastError: string | null;
  nextRunAt: string | null;
  createdAt: string;
  updatedAt: string;
}

type Row = {
  id: string; workflowId: string; nodeId: string | null; name: string; cron: string; timezone: string;
  enabled: boolean; catchUp: string; version: number | null;
  lastRunAt: Date | null; lastRunId: string | null; lastStatus: string | null;
  lastError: string | null; nextRunAt: Date | null; createdAt: Date; updatedAt: Date;
};

function toRecord(row: Row): ScheduleRecord {
  return {
    id: row.id,
    workflowId: row.workflowId,
    nodeId: row.nodeId,
    name: row.name,
    cron: row.cron,
    timezone: row.timezone,
    enabled: row.enabled,
    catchUp: row.catchUp === 'coalesce' ? 'coalesce' : 'skip',
    version: row.version,
    lastRunAt: row.lastRunAt?.toISOString() ?? null,
    lastRunId: row.lastRunId,
    lastStatus: row.lastStatus,
    lastError: row.lastError,
    nextRunAt: row.nextRunAt?.toISOString() ?? null,
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
  };
}

export function computeNextRun(cron: string, timezone: string, from = new Date()): Date | null {
  return nextRunAt(cron, timezone, from);
}

export async function getSchedule(id: string): Promise<ScheduleRecord | null> {
  const row = await prisma.workflowSchedule.findUnique({ where: { id } });
  return row ? toRecord(row as Row) : null;
}

export async function listSchedules(workflowId?: string): Promise<ScheduleRecord[]> {
  const rows = await prisma.workflowSchedule.findMany({
    where: workflowId ? { workflowId } : {},
    orderBy: { createdAt: 'asc' },
    take: 200,
  });
  return rows.map((r) => toRecord(r as Row));
}

export async function createSchedule(input: {
  workflowId: string;
  nodeId?: string | null;
  name: string;
  cron: string;
  timezone?: string;
  catchUp?: 'skip' | 'coalesce';
  version?: number | null;
  enabled?: boolean;
}): Promise<ScheduleRecord> {
  if (!isValidCron(input.cron)) throw new Error(`Invalid cron expression: ${input.cron}`);
  const timezone = input.timezone ?? 'UTC';
  if (!isValidTimezone(timezone)) throw new Error(`Unknown timezone: ${timezone}`);
  const next = computeNextRun(input.cron, timezone);
  if (!next) throw new Error('That expression never matches — use one that fires within 40 days.');
  const row = await prisma.workflowSchedule.create({
    data: {
      workflowId: input.workflowId,
      nodeId: input.nodeId ?? null,
      name: input.name,
      cron: input.cron.trim(),
      timezone,
      catchUp: input.catchUp ?? 'skip',
      version: input.version ?? null,
      enabled: input.enabled ?? true,
      nextRunAt: next,
    },
  });
  return toRecord(row as Row);
}

export async function updateSchedule(
  id: string,
  patch: Partial<Pick<ScheduleRecord, 'nodeId' | 'name' | 'cron' | 'timezone' | 'enabled' | 'catchUp' | 'version'>>,
): Promise<ScheduleRecord | null> {
  const existing = await prisma.workflowSchedule.findUnique({ where: { id } });
  if (!existing) return null;
  const cron = patch.cron?.trim() ?? existing.cron;
  const timezone = patch.timezone ?? existing.timezone;
  if (patch.cron) {
    if (!isValidCron(cron)) throw new Error(`Invalid cron expression: ${cron}`);
    parseCron(cron); // surfaces field-level errors early
  }
  if (!isValidTimezone(timezone)) throw new Error(`Unknown timezone: ${timezone}`);
  const enabled = patch.enabled ?? existing.enabled;
  const next = enabled ? computeNextRun(cron, timezone) : null;
  if (enabled && !next) throw new Error('That expression never matches — use one that fires within 40 days.');
  const row = await prisma.workflowSchedule.update({
    where: { id },
    data: {
      nodeId: patch.nodeId === undefined ? existing.nodeId : patch.nodeId,
      name: patch.name ?? existing.name,
      cron,
      timezone,
      enabled,
      catchUp: patch.catchUp ?? existing.catchUp,
      version: patch.version === undefined ? existing.version : patch.version,
      // Changing when a schedule fires recomputes the next occurrence.
      ...(patch.cron || patch.timezone || patch.enabled !== undefined ? { nextRunAt: next } : {}),
    },
  });
  return toRecord(row as Row);
}

export async function deleteSchedule(id: string): Promise<boolean> {
  try {
    await prisma.workflowSchedule.delete({ where: { id } });
    return true;
  } catch {
    return false;
  }
}

/** Schedules whose next fire time has arrived. */
export async function dueSchedules(now = new Date()): Promise<ScheduleRecord[]> {
  const rows = await prisma.workflowSchedule.findMany({
    where: { enabled: true, nextRunAt: { lte: now } },
    orderBy: { nextRunAt: 'asc' },
    take: 50,
  });
  return rows.map((r) => toRecord(r as Row));
}

/**
 * Atomically claim ONE due fire and advance its `nextRunAt`.
 *
 * The compare-and-set on the exact `nextRunAt` is the idempotency boundary:
 * two overlapping ticks (or two server processes) may both see the same due
 * row, but only the one whose UPDATE matches still-fires. The loser must not
 * start a run.
 *
 * `now` is the tick time. Advancing from `now` (not from the scheduled
 * instant) skips every missed occurrence, so a long-closed app never storms.
 */
export async function claimScheduleFire(
  id: string,
  scheduledFor: Date,
  now = new Date(),
): Promise<boolean> {
  const existing = await prisma.workflowSchedule.findUnique({ where: { id } });
  if (!existing || !existing.enabled) return false;
  if (existing.nextRunAt?.getTime() !== scheduledFor.getTime()) return false;
  const next = computeNextRun(existing.cron, existing.timezone, now);
  const result = await prisma.workflowSchedule.updateMany({
    where: { id, enabled: true, nextRunAt: scheduledFor },
    data: { nextRunAt: next },
  });
  return result.count === 1;
}

/** Record the outcome of a claimed fire. `nextRunAt` was already advanced. */
export async function recordScheduleFire(
  id: string,
  outcome: { runId?: string | null; status: string; error?: string | null },
  firedAt = new Date(),
): Promise<ScheduleRecord | null> {
  const row = await prisma.workflowSchedule.update({
    where: { id },
    data: {
      lastRunAt: firedAt,
      lastRunId: outcome.runId ?? null,
      lastStatus: outcome.status,
      lastError: outcome.error ?? null,
    },
  });
  return toRecord(row as Row);
}

/**
 * Pause a schedule that can no longer fire safely (e.g. its trigger node was
 * deleted). Unlike a user pause, this records the reason so the card shows it.
 */
export async function pauseSchedule(id: string, reason: string): Promise<void> {
  await prisma.workflowSchedule.update({
    where: { id },
    data: {
      enabled: false,
      nextRunAt: null,
      lastStatus: 'error',
      lastError: reason,
    },
  });
}

/** A missed fire that was deliberately skipped: record it, keep last run intact. */
export async function recordScheduleSkip(id: string, status = 'skipped-missed'): Promise<void> {
  await prisma.workflowSchedule.update({
    where: { id },
    data: { lastStatus: status, lastError: null },
  });
}

/** Update only the last outcome (used when a started run reaches a terminal state). */
export async function recordScheduleOutcome(
  id: string,
  status: string,
  error: string | null = null,
): Promise<void> {
  await prisma.workflowSchedule.update({
    where: { id },
    data: { lastStatus: status, lastError: error },
  });
}

/** Schedules whose recorded run was left at `started` long enough to reconcile. */
export async function pendingScheduleRuns(
  olderThanMs = 30_000,
  limit = 20,
  now = new Date(),
): Promise<ScheduleRecord[]> {
  const rows = await prisma.workflowSchedule.findMany({
    where: {
      lastStatus: 'started',
      lastRunId: { not: null },
      lastRunAt: { lte: new Date(now.getTime() - olderThanMs) },
    },
    orderBy: { lastRunAt: 'asc' },
    take: limit,
  });
  return rows.map((r) => toRecord(r as Row));
}
